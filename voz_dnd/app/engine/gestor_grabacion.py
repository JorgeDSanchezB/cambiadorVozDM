"""GestorGrabacion (Fase 3): tap post-DSP → MP3 con pydub (fallback WAV).

El `tap()` se llama desde el callback de audio (RT-safe: solo un append
atómico y una copia pequeña). La EXPORTACIÓN es bloqueante (concatenar,
convertir, escribir) y por eso se ejecuta SIEMPRE en un hilo de trabajo
desde la GUI, nunca en el hilo de Qt ni en el de audio.

MP3 requiere ffmpeg en el PATH (o su ruta en config.json → motor.ffmpeg_ruta).
Si no está disponible, se exporta WAV automáticamente y se devuelve un aviso
para mostrar en la UI (la sesión del DM jamás se pierde).

Invariante de tolerancia a fallos: el audio capturado SOLO se descarta
cuando una exportación ha tenido éxito. Ante cualquier fallo (ruta de
ffmpeg configurada inexistente, error del conversor, carpeta sin
permisos…) se degrada MP3→WAV→WAV-en-temporal, y si todo falla el audio
queda en memoria para poder reintentar. Nunca se pierde por un fallo de
exportación.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
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
        de degradación (p. ej. ffmpeg ausente → WAV). Si devuelve ruta=None
        el audio capturado sigue en memoria y se puede reintentar.
        """
        self._activo = False
        time.sleep(0.1)  # drena el último tap del hilo de audio (máx. 1 bloque)
        try:
            return self._exportar()
        except Exception as exc:  # noqa: BLE001 — última barrera, nunca lanza
            log.exception("Fallo exportando la grabación")
            return None, (f"No se pudo exportar: {exc}. El audio capturado "
                          f"se conserva en memoria; usa «Reintentar "
                          f"exportación» cuando hayas corregido la causa.")

    # ------------------------------ exportación -------------------------- #
    def _hay_ffmpeg(self) -> tuple[bool, str | None]:
        """Comprueba ffmpeg REALMENTE utilizable. Devuelve (hay, aviso).

        La ruta configurada se valida: si no existe se ignora (con aviso) y
        se cae al ffmpeg del PATH. Antes se asignaba a pydub sin validar y,
        si además había ffmpeg en el PATH, la comprobación daba True pero
        pydub usaba la ruta mala y la exportación moría con FileNotFoundError
        perdiendo toda la grabación.
        """
        try:
            from pydub import AudioSegment
        except Exception:  # noqa: BLE001 — pydub/audioop ausente
            return False, None

        aviso: str | None = None
        converter = "ffmpeg"          # valor por defecto de pydub (vía PATH)
        if self._ffmpeg_ruta:
            if Path(self._ffmpeg_ruta).exists():
                converter = self._ffmpeg_ruta
            else:
                aviso = (f"La ruta de ffmpeg configurada no existe "
                         f"({self._ffmpeg_ruta}); se ignora y se usa la "
                         f"del PATH.")
                log.warning(aviso)
        # Sanea el estado de clase de pydub (una ruta mala asignada en una
        # llamada anterior persistiría en AudioSegment.converter).
        AudioSegment.converter = converter
        if converter != "ffmpeg":
            return True, aviso
        return shutil.which("ffmpeg") is not None, aviso

    def _exportar(self) -> tuple[Path | None, str | None]:
        """Exporta con degradación en cascada: MP3 → WAV → WAV en temporal.

        El audio capturado (`_bloques`) solo se descarta si alguna vía tiene
        éxito; si todas fallan se conserva en memoria para reintentar (la
        GUI ofrece «Reintentar exportación» en la ventana de grabación).
        """
        if not self._bloques:
            return None, "No se capturó audio para grabar."

        audio = np.concatenate(self._bloques)[:, 0]
        audio = np.clip(audio.astype(np.float64), -1.0, 1.0)
        pcm = (audio * 32767.0).astype(np.int16)

        # La carpeta o el patrón de nombre pueden fallar (permisos, ruta
        # ocupada por un fichero, patrón roto en config): degradación
        # directa al WAV en temporal, igual que el resto de la cascada.
        try:
            carpeta = self._resolver_carpeta()
            ruta_base = carpeta / self._nombre_archivo()
        except Exception as exc:  # noqa: BLE001 — destino no utilizable
            log.exception("Carpeta de grabación no utilizable")
            return self._rescatar_en_temporal(
                pcm, [f"No se pudo usar la carpeta de grabación ({exc})."])

        hay_ffmpeg, aviso_ffmpeg = self._hay_ffmpeg()
        avisos: list[str] = ([aviso_ffmpeg] if aviso_ffmpeg else [])

        ruta: Path | None = None
        if self._cfg.formato.lower() == "mp3" and hay_ffmpeg:
            try:
                ruta = self._exportar_mp3(pcm, ruta_base)
            except Exception as exc:  # noqa: BLE001 — el MP3 nunca cuesta la sesión
                log.exception("Exportación MP3 falló; se intenta WAV")
                avisos.append(f"La exportación MP3 falló ({exc}); "
                               f"se guardó WAV como alternativa.")

        if ruta is None:  # WAV directo, o fallback tras fallo/ausencia de MP3
            try:
                ruta = self._exportar_wav(pcm, ruta_base)
                if (ruta is not None and self._cfg.formato.lower() == "mp3"
                        and not any("MP3" in a for a in avisos)):
                    avisos.append("MP3 no disponible (falta ffmpeg): se exportó "
                                  "WAV. Instala ffmpeg o indica su ruta en "
                                  "Ajustes.")
            except Exception as exc:  # noqa: BLE001
                log.exception("Exportación WAV falló en %s", carpeta)
                avisos.append(f"No se pudo escribir en {carpeta} ({exc}).")
                return self._rescatar_en_temporal(pcm, avisos)

        if ruta is not None:
            self._bloques.clear()
            self._frames_acumulados = 0
            log.info("Grabación exportada: %s", ruta)
        return ruta, (" ".join(avisos) if avisos else None)

    def _rescatar_en_temporal(self, pcm: np.ndarray,
                              avisos: list[str]) -> tuple[Path | None, str | None]:
        """Último recurso de la cascada: WAV en el temporal del sistema.

        Si ni siquiera eso es posible, el audio queda en memoria (los
        bloques NO se descartan) y el aviso indica cómo reintentarlo.
        """
        ruta = self._temporal_wav(pcm)
        if ruta is not None:
            avisos.append(f"La sesión se guardó en {ruta} para no perderla.")
            self._bloques.clear()
            self._frames_acumulados = 0
            log.info("Grabación rescatada en temporal: %s", ruta)
            return ruta, " ".join(avisos)
        return None, (" ".join(avisos) + " El audio capturado se conserva "
                      "en memoria; usa «Reintentar exportación» en la "
                      "ventana de grabación cuando hayas corregido la causa.")

    def _exportar_mp3(self, pcm: np.ndarray, ruta_base: Path) -> Path:
        from pydub import AudioSegment  # import diferido
        segmento = AudioSegment(
            pcm.tobytes(), frame_rate=self._sr, sample_width=2, channels=1)
        ruta = ruta_base.with_suffix(".mp3")
        # ffmpeg acepta "192k"; la forma "192kbps" falla en versiones
        # recientes de libmp3lame (probado con ffmpeg 7.x).
        try:
            segmento.export(str(ruta), format="mp3",
                            bitrate=f"{self._cfg.bitrate_kbps}k")
        except Exception:
            # No deja un MP3 a medias junto al WAV de rescate (confusión
            # garantizada: dos archivos con el mismo nombre y base distinta).
            ruta.unlink(missing_ok=True)
            raise
        return ruta

    def _exportar_wav(self, pcm: np.ndarray, ruta_base: Path) -> Path:
        ruta = ruta_base.with_suffix(".wav")
        with wave.open(str(ruta), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._sr)
            w.writeframes(pcm.tobytes())
        return ruta

    def _temporal_wav(self, pcm: np.ndarray) -> Path | None:
        """WAV en el directorio temporal del sistema (último recurso).

        Usa un nombre PROPIO (no el patrón configurable): la vía de rescate
        no puede depender de la misma configuración que pudo causar el fallo.
        """
        try:
            ruta = (Path(tempfile.gettempdir())
                    / f"voz_dnd_rescate_{datetime.now():%Y%m%d_%H%M%S}.wav")
            with wave.open(str(ruta), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self._sr)
                w.writeframes(pcm.tobytes())
            return ruta
        except Exception:  # noqa: BLE001
            log.exception("Ni siquiera el WAV temporal pudo escribirse")
            return None

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

