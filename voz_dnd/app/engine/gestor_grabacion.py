"""GestorGrabacion (Fase 3): tap post-DSP → MP3 con pydub (fallback WAV).

El `tap()` se llama desde el callback de audio (RT-safe: solo un append
atómico y una copia pequeña). La EXPORTACIÓN es bloqueante (concatenar,
convertir, escribir) y por eso se ejecuta SIEMPRE en un hilo de trabajo
desde la GUI, nunca en el hilo de Qt ni en el de audio.

MP3 requiere ffmpeg en el PATH (o su ruta en config.json → motor.ffmpeg_ruta).
Si no está disponible, se exporta WAV automáticamente y se devuelve un aviso
para mostrar en la UI (la sesión del DM jamás se pierde).
"""
from __future__ import annotations

import logging
import shutil
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from app.config import ConfigGrabacion

log = logging.getLogger(__name__)

# Límite de seguridad: 2 horas de sesión continua
MAX_SEGUNDOS = 7200
CARACTERES_INVALIDOS = '\\/:*?"<>|'


class GestorGrabacion:
    def __init__(self, cfg: ConfigGrabacion, sr: int, ffmpeg_ruta: str = ""):
        self._cfg = cfg
        self._sr = sr
        self._ffmpeg_ruta = ffmpeg_ruta
        self._activo = False
        self._bloques: list[np.ndarray] = []
        self._frames_acumulados = 0
        self._t0 = 0.0

    # ------------------------------ estado ------------------------------- #
    @property
    def activo(self) -> bool:
        return self._activo

    def duracion(self) -> float:
        """Duración exacta calculada por muestras acumuladas (no por reloj)."""
        return self._frames_acumulados / float(self._sr)

    # ------------------------------ tap RT ------------------------------- #
    def tap(self, bloque: np.ndarray) -> None:
        """LLAMADO DESDE EL CALLBACK DE AUDIO. Copia y acumula el bloque."""
        if not self._activo:
            return
        self._bloques.append(bloque.copy())
        self._frames_acumulados += bloque.shape[0]
        if self._frames_acumulados >= MAX_SEGUNDOS * self._sr:
            self._activo = False  # auto-stop (la GUI lo detecta por polling)

    # --------------------------- ciclo grabación ------------------------- #
    def iniciar(self) -> None:
        self._bloques.clear()
        self._frames_acumulados = 0
        self._t0 = time.time()
        self._activo = True

    def detener_y_exportar(self) -> tuple[Path | None, str | None]:
        """Detiene y exporta. BLOQUEANTE → llamar desde un hilo de trabajo.

        Devuelve (ruta, aviso): aviso es None si todo fue bien, o el mensaje
        de degradación (p. ej. ffmpeg ausente → WAV).
        """
        self._activo = False
        time.sleep(0.1)  # drena el último tap del hilo de audio (máx. 1 bloque)
        try:
            return self._exportar()
        except Exception as exc:  # noqa: BLE001
            log.exception("Fallo exportando la grabación")
            return None, f"No se pudo exportar: {exc}"

    # ------------------------------ exportación -------------------------- #
    def _exportar(self) -> tuple[Path | None, str | None]:
        if not self._bloques:
            return None, "No se capturó audio para grabar."

        audio = np.concatenate(self._bloques)[:, 0]
        self._bloques.clear()
        audio = np.clip(audio.astype(np.float64), -1.0, 1.0)
        pcm = (audio * 32767.0).astype(np.int16)

        carpeta = self._resolver_carpeta()
        ruta_base = carpeta / self._nombre_archivo()

        if self._cfg.formato.lower() == "mp3" and self._hay_ffmpeg():
            from pydub import AudioSegment  # import diferido
            segmento = AudioSegment(
                pcm.tobytes(), frame_rate=self._sr, sample_width=2, channels=1)
            ruta = ruta_base.with_suffix(".mp3")
            # ffmpeg acepta "192k"; la forma "192kbps" falla en versiones
            # recientes de libmp3lame (probado con ffmpeg 7.x).
            segmento.export(str(ruta), format="mp3",
                            bitrate=f"{self._cfg.bitrate_kbps}k")
            log.info("Grabación exportada a MP3: %s", ruta)
            return ruta, None

        # ---- Fallback tolerante: WAV sin dependencias externas ----
        ruta = ruta_base.with_suffix(".wav")
        with wave.open(str(ruta), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._sr)
            w.writeframes(pcm.tobytes())
        aviso = ("MP3 no disponible (falta ffmpeg): se exportó WAV. "
                 "Instala ffmpeg o indica su ruta en Ajustes.")
        log.warning(aviso)
        return ruta, aviso

    def _resolver_carpeta(self) -> Path:
        destino = self._cfg.carpeta_destino.strip()
        carpeta = (Path(destino).expanduser() if destino
                   else Path.home() / "Music" / "SesionesDnD")
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    def _nombre_archivo(self) -> str:
        ahora = datetime.now()
        nombre = self._cfg.patron_nombre.format(
            fecha=ahora.strftime("%Y-%m-%d"),
            hora=ahora.strftime("%H%M%S"),
        )
        return "".join(c if c not in CARACTERES_INVALIDOS else "_"
                       for c in nombre)

    def _hay_ffmpeg(self) -> bool:
        try:
            from pydub import AudioSegment
        except Exception:  # noqa: BLE001 — pydub/audioop ausente
            return False
        if self._ffmpeg_ruta:
            AudioSegment.converter = self._ffmpeg_ruta
        converter = AudioSegment.converter
        if converter and Path(converter).exists():
            return True
        return shutil.which("ffmpeg") is not None
