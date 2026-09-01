"""MotorAudio: flujo Micrófono → DSP → Altavoz con sounddevice.

Diseño de concurrencia (clave para la latencia):
  * UN solo stream dúplex con UN callback: PortAudio entrega la entrada y
    espera la salida en la misma llamada → mínima latencia y sin deriva.
  * El callback corre en el hilo de alta prioridad de PortAudio. Dentro de él
    SOLO hay operaciones numpy (ya vectorizadas por los efectos) y asignaciones
    de atributos, que son atómicas bajo el GIL de Python.
  * Cambio de voz = reemplazo de UNA referencia (`self._cadena`) → sin locks,
    sin bloqueos, cambio instantáneo en mitad de una sesión.
  * La GUI NUNCA es tocada desde el callback: la comunicación inversa se hace
    con una cola de eventos (`queue.SimpleQueue`) que la GUI drena con QTimer.
"""
from __future__ import annotations

import queue
from typing import Any

import numpy as np

from dominio.entidades import IVoiceProfile, PerfilDSP, PerfilIA
from dominio.fabrica_cadena import FabricaCadena
from dominio.efectos import IEfectoDSP

TAMANIOS_BUFFER_VALIDOS = (128, 256, 512, 1024)
OVERHEAD_DRIVER_MS = 8.0  # estimación fija de overhead WASAPI/MME para la UI


class MotorAudio:
    """Dueño del stream de audio y del estado en tiempo real."""

    def __init__(
        self,
        config: dict[str, Any],
        eventos: "queue.SimpleQueue[tuple[str, ...]]",
        grabador: Any,  # GestorGrabacion (inyección para evitar ciclo)
    ) -> None:
        import sounddevice as sd  # import perezoso: error claro si falta PortAudio

        self._sd = sd
        self.config = config
        audio = config["audio"]
        self.sr = int(audio.get("sample_rate", 48000))
        self.buffer_size = int(audio.get("buffer_size", 256))
        self.canales_salida = int(audio.get("canales_salida", 2))
        self.eventos = eventos
        self.grabador = grabador

        self.monitor = True          # escuchar la voz transformada en vivo
        self.nivel: float = 0.0      # RMS del último bloque (lo lee la GUI)
        self.voz_activa: IVoiceProfile | None = None

        self._cadena: list[IEfectoDSP] = []
        self._latencia_cadena = 0
        self._ia: Any | None = None  # ProcesadorIA (opcional)
        self.stream: Any | None = None
        self._dispositivos: tuple[int | None, int | None] = (None, None)

    # ------------------------------------------------------------------ #
    #  Gestión del stream
    # ------------------------------------------------------------------ #
    def resolver_dispositivos(self) -> tuple[int | None, int | None]:
        """Traduce los nombres de dispositivos de config.json a índices."""
        audio = self.config["audio"]
        nombre_in = audio.get("dispositivo_entrada")
        nombre_out = audio.get("dispositivo_salida")
        entrada = self._indice_por_nombre(nombre_in) if nombre_in else None
        salida = self._indice_por_nombre(nombre_out) if nombre_out else None
        self._dispositivos = (entrada, salida)
        return self._dispositivos

    def _indice_por_nombre(self, nombre: str) -> int | None:
        try:
            for indice, disp in enumerate(self._sd.query_devices()):
                if nombre and nombre.lower() in str(disp["name"]).lower():
                    return indice
        except Exception as exc:  # pragma: no cover - depende del driver
            self.eventos.put(("error_audio", f"No se pudo listar dispositivos: {exc}"))
        self.eventos.put(("aviso", f"Dispositivo '{nombre}' no encontrado; usando el predeterminado"))
        return None

    def iniciar(self) -> bool:
        """Abre el stream dúplex. Devuelve True si arrancó."""
        self.detener()
        entrada, salida = self.resolver_dispositivos()
        try:
            try:
                self.stream = self._sd.Stream(
                    samplerate=self.sr,
                    blocksize=self.buffer_size,
                    channels=(1, self.canales_salida),
                    dtype="float32",
                    device=(entrada, salida),
                    latency="low",
                    callback=self._callback,
                )
            except self._sd.PortAudioError:
                # Algunos dispositivos no aceptan salida estéreo → reintento mono.
                self.stream = self._sd.Stream(
                    samplerate=self.sr,
                    blocksize=self.buffer_size,
                    channels=1,
                    dtype="float32",
                    device=(entrada, salida),
                    latency="low",
                    callback=self._callback,
                )
            self.stream.start()
            self.eventos.put(("estado_audio", "activo"))
            return True
        except Exception as exc:
            self.stream = None
            self.eventos.put(("error_audio", f"No se pudo abrir el audio: {exc}"))
            return False

    def detener(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            self.eventos.put(("estado_audio", "detenido"))

    def cambiar_buffer(self, nuevo_tamanio: int) -> None:
        """Reinicia el stream con otro tamaño de bloque (Ajustes)."""
        if nuevo_tamanio not in TAMANIOS_BUFFER_VALIDOS:
            self.eventos.put(("aviso", f"Buffer {nuevo_tamanio} no válido"))
            return
        self.buffer_size = nuevo_tamanio
        self.config["audio"]["buffer_size"] = nuevo_tamanio
        if self.stream is not None:
            self.iniciar()
        self.eventos.put(("buffer_cambiado", str(nuevo_tamanio)))

    # ------------------------------------------------------------------ #
    #  Selección de voz (swap atómico de cadena)
    # ------------------------------------------------------------------ #
    def aplicar_voz(self, perfil: IVoiceProfile) -> None:
        """Construye la cadena desde el perfil y la activa al instante."""
        self.voz_activa = perfil
        self._ia = None

        if isinstance(perfil, PerfilDSP):
            cadena = FabricaCadena.construir(perfil.parametros_dsp, self.sr)
        else:  # PerfilIA
            permitir_ia = bool(self.config.get("motor", {}).get("permitir_ia", True))
            if permitir_ia:
                from aplicacion.procesador_ia import ProcesadorIA  # import perezoso

                ruta_plugin = self.config.get("motor", {}).get(
                    "ruta_plugin_rvc", "./modelos/plugin_rvc.py"
                )
                self._ia = ProcesadorIA(perfil, self.sr, self.eventos, ruta_plugin)
            else:
                self.eventos.put(("aviso", "Modo IA deshabilitado en Ajustes; usando DSP"))
            # La cadena DSP-post siempre existe (fallback inmediato si la IA falla).
            cadena = FabricaCadena.construir(perfil.dsp_post, self.sr)

        self._cadena = cadena
        self._latencia_cadena = FabricaCadena.latencia_total_muestras(cadena)
        for efecto in cadena:
            efecto.reset()
        modo = "IA" if (self._ia is not None and isinstance(perfil, PerfilIA)) else "DSP"
        self.eventos.put(("voz_activada", perfil.nombre, modo))

    def probar_cadena_temporal(self, parametros: Any) -> None:
        """Preview del Editor: aplica parámetros sin guardar nada."""
        cadena = FabricaCadena.construir(parametros, self.sr)
        self._cadena = cadena
        self._latencia_cadena = FabricaCadena.latencia_total_muestras(cadena)
        self.eventos.put(("preview", "cadena temporal activa"))

    def restaurar_voz_activa(self) -> None:
        if self.voz_activa is not None:
            self.aplicar_voz(self.voz_activa)

    # ------------------------------------------------------------------ #
    #  Callback de audio (hilo RT de PortAudio)
    # ------------------------------------------------------------------ #
    def _callback(self, indata: np.ndarray, outdata: np.ndarray,
                  frames: int, time_info: Any, status: Any) -> None:
        try:
            if status:
                self.eventos.put(("aviso_audio", str(status)))
            x = indata[:, 0].copy()

            y = self._procesar_bloque(x)

            if not self.monitor:
                y = np.zeros_like(y)
            canales = outdata.shape[1]
            for canal in range(canales):
                outdata[:, canal] = y

            # Medidor de nivel (float atómico para la GUI) y tap de grabación.
            rms = float(np.sqrt(np.mean(y * y))) if len(y) else 0.0
            self.nivel = min(1.0, rms * 4.0)  # escala perceptual para la barra
            self.grabador.tap(y)
        except Exception as exc:  # jamás propagar hacia PortAudio
            outdata[:] = 0
            self.eventos.put(("error_audio", f"Error en callback: {exc}"))

    def _procesar_bloque(self, x: np.ndarray) -> np.ndarray:
        y = x
        if self._ia is not None and getattr(self._ia, "activo", False):
            y = self._ia.procesar(y)
        for efecto in self._cadena:
            y = efecto.procesar(y, self.sr)
        return np.clip(y, -1.0, 1.0).astype(np.float32)

    # ------------------------------------------------------------------ #
    #  Métricas para la UI
    # ------------------------------------------------------------------ #
    def latencia_estimada_ms(self) -> float:
        base = 2.0 * (self.buffer_size / self.sr * 1000.0)  # entrada + salida
        cadena = self._latencia_cadena / self.sr * 1000.0
        return base + cadena + OVERHEAD_DRIVER_MS
