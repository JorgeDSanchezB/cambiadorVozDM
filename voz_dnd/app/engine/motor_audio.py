"""MotorAudio: puente con sounddevice (Fase 3).

Decisión de arquitectura: se usa UN ÚNICO `sd.Stream` full-duplex (entrada
y salida en el mismo callback) en lugar de InputStream + OutputStream:
misma palabra de reloj, cero deriva entre micrófono y monitor, y la latencia
mínima posible. El flujo Micrófono → DSP → Altavoz ocurre dentro del
callback de PortAudio.

Contrato del callback (invariante RT):
  * sin locks, sin I/O, sin Qt, sin JSON, sin asignaciones grandes;
  * el cambio de voz es un intercambio de REFERENCIA (atómico bajo GIL);
  * cualquier excepción se captura: nunca se propaga hacia PortAudio;
    se registra y la salida se silencia un bloque (fail-safe).

La GUI NO recibe señales desde el hilo de audio: consulta por polling
(`nivel_db`, `extraer_errores`) con un QTimer de 33 ms — 30 FPS sobrados
para el medidor y cero riesgo de cruce de hilos.
"""
from __future__ import annotations

import logging
from collections import deque

import numpy as np

from app.config import ConfigApp
from app.domain.efectos import rms_a_db
from app.engine.gestor_grabacion import GestorGrabacion
from app.engine.procesador import ProcesadorBase, ProcesadorBypass

log = logging.getLogger(__name__)

# Overhead medio estimado de driver/OS (WASAPI/MME en Windows 10/11)
OVERHEAD_DRIVER_MS = 8.0


class MotorAudio:
    def __init__(self, cfg: ConfigApp, procesador_inicial: ProcesadorBase | None = None):
        self._cfg = cfg
        self.sr = int(cfg.audio.sample_rate)
        self._procesador: ProcesadorBase = procesador_inicial or ProcesadorBypass()
        self._stream = None          # sd.Stream (import diferido de sounddevice)
        self._sd = None              # módulo sounddevice (cacheado)
        self.grabador = GestorGrabacion(
            cfg.grabacion, self.sr, ffmpeg_ruta=cfg.motor.ffmpeg_ruta)
        self.monitoreo: bool = True  # False → silencio local (sigue grabando)
        self._pausado: bool = False
        self._nivel_db: float = -90.0
        self._errores: deque[str] = deque(maxlen=30)
        # Reproducción de audio pre-procesado (lectura de texto): el callback
        # sirve este buffer (N,1) float32 en vez del micrófono mientras queda
        # audio. Se intercambia por referencia (seguro bajo el GIL).
        self._playback: np.ndarray | None = None
        self._playback_pos: int = 0

    # --------------------------- ciclo de vida --------------------------- #
    def iniciar(self) -> None:
        """Abre el stream full-duplex. Lanza excepción si no hay audio.

        Si la combinación de dispositivos guardada no se puede abrir (p. ej.
        un id obsoleto en config.json), reintenta con los dispositivos por
        defecto del sistema en vez de dejar la app sin audio.
        """
        import sounddevice as sd  # import diferido: permite diagnosticar sin PortAudio
        self._sd = sd
        self._usando_defaults = False
        dispositivo = self._par_dispositivos()
        log.info("Abriendo audio: sr=%s buffer=%s dispositivos=%s",
                 self.sr, self._cfg.audio.buffer_size, dispositivo)
        try:
            self._stream = self._abrir_stream(dispositivo)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("Fallo al abrir el audio con los dispositivos "
                        "guardados (%s): %s", dispositivo, exc)
            self._cerrar_stream()
            # Reintento con los dispositivos por defecto del sistema para que
            # un id obsoleto en config.json no deje la app sin audio.
            self._stream = self._abrir_stream(None)
            self._usando_defaults = True
            try:
                self._stream.start()
            except Exception:
                self._cerrar_stream()
                raise

    def _abrir_stream(self, dispositivo) -> None:
        import sounddevice as sd
        return sd.Stream(
            samplerate=self.sr,
            blocksize=int(self._cfg.audio.buffer_size),
            dtype="float32",
            channels=1,
            device=dispositivo,
            callback=self._callback,
        )

    @property
    def usando_dispositivos_default(self) -> bool:
        """True si el audio se abrió con los dispositivos del sistema porque
        los guardados en config.json no pudieron abrirse."""
        return getattr(self, "_usando_defaults", False)

    def _cerrar_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:  # noqa: BLE001
                log.exception("Error al cerrar el stream de audio")

    def detener(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                log.exception("Error al cerrar el stream de audio")
            finally:
                self._stream = None

    # --------------------------- pausa / reanudar ------------------------ #
    @property
    def pausado(self) -> bool:
        return self._pausado

    def pausar(self) -> None:
        if self._stream is not None and not self._pausado:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001
                log.exception("Error al pausar el stream")
            else:
                self._pausado = True
                self._nivel_db = -90.0

    def reanudar(self) -> None:
        if self._stream is not None and self._pausado:
            try:
                self._stream.start()
            except Exception:  # noqa: BLE001
                log.exception("Error al reanudar el stream")
            else:
                self._pausado = False

    def _par_dispositivos(self) -> tuple[int, int] | None:
        import sounddevice as _sd
        entrada = self._cfg.audio.dispositivo_entrada
        salida = self._cfg.audio.dispositivo_salida

        if entrada is None:
            entrada = int(_sd.default.device[0])
        if salida is None:
            salida = int(_sd.default.device[1])

        info_e = _sd.query_devices(entrada, "input")
        if info_e["max_input_channels"] < 1:
            log.warning("Dispositivo de entrada %d sin canales de entrada; "
                        "se usa el defecto del sistema", entrada)
            entrada = int(_sd.default.device[0])

        info_s = _sd.query_devices(salida, "output")
        if info_s["max_output_channels"] < 1:
            log.warning("Dispositivo de salida %d sin canales de salida; "
                        "se usa el defecto del sistema", salida)
            salida = int(_sd.default.device[1])

        return (entrada, salida)

    # --------------------------- voz activa ------------------------------ #
    @property
    def procesador_actual(self) -> ProcesadorBase:
        return self._procesador

    def cambiar_procesador(self, procesador: ProcesadorBase) -> None:
        """Cambio de voz: intercambio de referencia, seguro y sin bloqueo.

        Detiene los recursos de fondo del procesador saliente (p. ej. el hilo
        de inferencia del modo IA) antes de sustituirlo.
        """
        anterior = self._procesador
        self._procesador = procesador
        if anterior is not None and anterior is not procesador:
            cerrar = getattr(anterior, "cerrar", None)
            if callable(cerrar):
                try:
                    cerrar()
                except Exception:  # noqa: BLE001 — nunca debe cortar el cambio
                    log.exception("Error al cerrar el procesador de voz anterior")

    # --------------------- reproducción de audio (texto) ------------------ #
    def reproducir(self, datos: np.ndarray | None) -> None:
        """Pone un buffer (N,1) float32 para reproducirlo por el stream.

        Mientras quede audio, el callback lo sirve a la salida en lugar del
        micrófono (el audio ya viene procesado con la voz). `None` detiene.
        """
        if datos is None or datos.size == 0:
            self._playback = None
            self._playback_pos = 0
            return
        self._playback = datos.astype(np.float32).reshape(-1, 1)
        self._playback_pos = 0

    @property
    def reproduciendo(self) -> bool:
        buf = self._playback
        return buf is not None and self._playback_pos < buf.shape[0]

    def detener_reproduccion(self) -> None:
        self.reproducir(None)

    # --------------------------- configuración --------------------------- #
    def aplicar_config_audio(self, cfg: ConfigApp) -> None:
        """Cambia buffer/dispositivos en caliente: reinicia el stream."""
        estaba_activo = self._stream is not None
        if estaba_activo:
            self.detener()
        self._cfg = cfg
        self.sr = int(cfg.audio.sample_rate)
        self.grabador = GestorGrabacion(
            cfg.grabacion, self.sr, ffmpeg_ruta=cfg.motor.ffmpeg_ruta)
        if estaba_activo:
            self.iniciar()

    # --------------------------- telemetría GUI -------------------------- #
    @property
    def nivel_db(self) -> float:
        return self._nivel_db

    @property
    def latencia_estimada_ms(self) -> float:
        base = 2.0 * self._cfg.audio.buffer_size / self.sr * 1000.0
        dsp = self._procesador.latencia_muestras / self.sr * 1000.0
        return base + dsp + OVERHEAD_DRIVER_MS

    def extraer_errores(self) -> list[str]:
        if not self._errores:
            return []
        errores = list(self._errores)
        self._errores.clear()
        return errores

    # --------------------------- callback RT ----------------------------- #
    def _callback(self, indata, outdata, frames, tiempo, status) -> None:
        try:
            if status:
                self._errores.append(f"Driver de audio: {status}")

            # --- Reproducción de audio pre-procesado (lectura de texto) ---
            # Si hay un buffer en curso, se sirve a la salida en vez del
            # micrófono; al agotarse vuelve al flujo Micrófono → DSP → Salida.
            playback = self._playback
            if playback is not None:
                pos = self._playback_pos
                resto = playback.shape[0] - pos
                if resto > 0:
                    n = min(frames, resto)
                    salida = playback[pos: pos + n, 0]
                    pos += n
                    self._playback_pos = pos
                    if pos >= playback.shape[0]:
                        self._playback = None
                        self._playback_pos = 0
                    if salida.shape[0] < frames:
                        salida = np.pad(salida, (0, frames - salida.shape[0]))
                    if self.monitoreo:
                        outdata[:, 0] = salida
                    else:
                        outdata.fill(0.0)
                    self._nivel_db = rms_a_db(salida)
                    self.grabador.tap(salida.reshape(-1, 1).astype(np.float32))
                    return

            # Contrato de efectos: bloque (frames, 1) float32
            bloque = indata[:, :1].copy()
            procesador = self._procesador
            salida = (procesador.procesar(bloque, self.sr)
                      if procesador is not None else bloque)

            # Normaliza la salida a (frames,) para el buffer de PortAudio
            if salida.ndim == 2:
                salida = salida[:, 0]
            if salida.shape[0] != frames:
                # Defensa anti-desincronización (p. ej. efectos STFT)
                if salida.shape[0] > frames:
                    salida = salida[:frames]
                else:
                    salida = np.pad(salida, (0, frames - salida.shape[0]))

            if self.monitoreo:
                outdata[:, 0] = salida
            else:
                outdata.fill(0.0)

            self._nivel_db = rms_a_db(salida)
            self.grabador.tap(salida.reshape(-1, 1).astype(np.float32))

        except Exception as exc:  # noqa: BLE001 — nunca propagar a PortAudio
            self._errores.append(f"Error en el callback de audio: {exc}")
            outdata.fill(0.0)
