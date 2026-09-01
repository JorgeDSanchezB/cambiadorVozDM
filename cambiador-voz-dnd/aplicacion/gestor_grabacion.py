"""GestorGrabacion: tap post-DSP + exportación MP3 con pydub.

Flujo: el callback de audio entrega los bloques YA procesados (lo que oye la
mesa). Al detener, un HILO WORKER concatena, convierte a int16 y exporta:
    * MP3 (vía pydub) si ffmpeg está disponible.
    * WAV (vía scipy) como fallback automático si ffmpeg falta.
La UI se entera por eventos; nunca se bloquea.
"""
from __future__ import annotations

import queue
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

FFMPEG_DISPONIBLE: bool | None = None  # None = aún no comprobado


def comprobar_ffmpeg() -> bool:
    """True si pydub/ffmpeg pueden exportar MP3."""
    global FFMPEG_DISPONIBLE
    if FFMPEG_DISPONIBLE is None:
        try:
            from pydub import AudioSegment  # noqa: F401

            FFMPEG_DISPONIBLE = bool(
                shutil.which("ffmpeg") or AudioSegment.converter
            )
        except Exception:
            FFMPEG_DISPONIBLE = bool(shutil.which("ffmpeg"))
    return FFMPEG_DISPONIBLE


class GestorGrabacion:
    def __init__(self, config: dict[str, Any], sr: int,
                 eventos: "queue.SimpleQueue[tuple[str, ...]]") -> None:
        self.config = config["grabacion"]
        self.sr = int(sr)
        self.eventos = eventos
        self.grabando = False
        self.inicio_ts: float | None = None
        self._bloques: list[np.ndarray] = []
        self._exportando = False

    # ------------------------------------------------------------------ #
    #  Control desde la UI
    # ------------------------------------------------------------------ #
    def iniciar(self) -> None:
        self._bloques = []
        self.inicio_ts = time.time()
        self.grabando = True

    def detener(self) -> None:
        """Cierra la captura y lanza la exportación en segundo plano."""
        if not self.grabando:
            return
        self.grabando = False
        bloques = self._bloques
        self._bloques = []
        self._exportando = True
        hilo = threading.Thread(target=self._exportar, args=(bloques,), daemon=True)
        hilo.start()

    def segundos_transcurridos(self) -> int:
        if self.inicio_ts is None or not self.grabando:
            return 0
        return int(time.time() - self.inicio_ts)

    # ------------------------------------------------------------------ #
    #  Tap (llamado desde el callback de audio; operación GIL-atómica)
    # ------------------------------------------------------------------ #
    def tap(self, bloque: np.ndarray) -> None:
        if self.grabando:
            self._bloques.append(bloque)

    # ------------------------------------------------------------------ #
    #  Exportación (hilo worker)
    # ------------------------------------------------------------------ #
    def _exportar(self, bloques: list[np.ndarray]) -> None:
        try:
            datos = (np.concatenate(bloques) if bloques
                     else np.zeros(self.sr, dtype=np.float32))
            datos = np.clip(datos.astype(np.float32), -1.0, 1.0)
            carpeta = self._carpeta_destino()
            nombre = self._nombre_archivo()
            ruta_mp3 = carpeta / f"{nombre}.mp3"
            ruta_wav = carpeta / f"{nombre}.wav"

            if comprobar_ffmpeg():
                try:
                    self._exportar_mp3(datos, ruta_mp3)
                    self.eventos.put(("grabacion_lista", str(ruta_mp3), ""))
                    return
                except Exception as exc:
                    aviso = f"MP3 falló ({exc}); se exportó WAV"
            else:
                aviso = "ffmpeg no encontrado: se exportó WAV. Instálalo para MP3."
            self._exportar_wav(datos, ruta_wav)
            self.eventos.put(("grabacion_lista", str(ruta_wav), aviso))
        except Exception as exc:
            self.eventos.put(("error_grabacion", str(exc)))
        finally:
            self._exportando = False

    def _exportar_mp3(self, datos: np.ndarray, ruta: Path) -> None:
        from pydub import AudioSegment

        pcm = (datos * 32767.0).astype(np.int16)
        segmento = AudioSegment(
            pcm.tobytes(), frame_rate=self.sr, sample_width=2, channels=1
        )
        bitrate = int(self.config.get("bitrate_kbps", 192))
        segmento.export(str(ruta), format="mp3", bitrate=f"{bitrate}k")

    def _exportar_wav(self, datos: np.ndarray, ruta: Path) -> None:
        from scipy.io import wavfile

        pcm = (datos * 32767.0).astype(np.int16)
        wavfile.write(str(ruta), rate=self.sr, data=pcm)

    # ------------------------------------------------------------------ #
    #  Rutas y nombres
    # ------------------------------------------------------------------ #
    def _carpeta_destino(self) -> Path:
        carpeta = Path(self.config.get("carpeta_destino", "./grabaciones"))
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    def _nombre_archivo(self) -> str:
        patron = self.config.get("patron_nombre", "voz_{fecha}_{hora}")
        ahora = datetime.now()
        return patron.format(
            fecha=ahora.strftime("%Y%m%d"),
            hora=ahora.strftime("%H%M%S"),
        )
