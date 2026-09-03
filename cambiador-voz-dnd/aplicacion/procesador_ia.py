"""ProcesadorIA: Modo Avanzado (clonación de voz RVC) como módulo OPCIONAL.

Arquitectura de plugin (la app no depende de torch para funcionar):
  * Busca `modelos/plugin_rvc.py` (ruta configurable en config.json →
    motor.ruta_plugin_rvc) exponiendo dos funciones:

        cargar(ruta_modelo: str, usar_gpu: bool) -> objeto_motor
        inferir(motor, chunk_float32_mono, pitch_semitonos, index_rate, sr)
            -> np.ndarray float32 mono (MISMO tamaño que el chunk)

  * La carga del modelo ocurre en un HILO BACKGROUND: la app arranca en < 2 s
    y mientras carga sigue usando la cadena DSP.
  * Detección automática de GPU vía torch (si está instalado).
  * Guardas de producción:
      - Si el plugin/modelo/GPU falta → `activo=False` y el motor sigue con
        DSP (fallback silencioso + aviso a la UI).
      - Si la inferencia es más lenta que el tiempo real de forma sostenida
        (solo posible en CPU), el procesador se desactiva solo para no
        acumular latencia infinita.
"""
from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

TAMANIO_CHUNK = 4096                      # muestras por inferencia (~85 ms @48k)
FACTOR_SEGURIDAD_RT = 0.8                 # inferencia debe tardar < 80 % del chunk
BLOQUES_TOLERANCIA_LENTITUD = 6


class ProcesadorIA:
    def __init__(self, perfil: Any, sr: int,
                 eventos: "queue.SimpleQueue[tuple[str, ...]]",  # type: ignore[name-defined]
                 ruta_plugin: str = "./modelos/plugin_rvc.py") -> None:
        self.perfil = perfil
        self.sr = int(sr)
        self.eventos = eventos
        self.ruta_plugin = Path(ruta_plugin)
        self.activo = False
        self._fn_inferir: Callable[..., Any] | None = None

        self._plugin: Any | None = None
        self._motor_modelo: Any | None = None
        self._lock = threading.Lock()
        self._entrada = np.zeros(0, dtype=np.float32)
        self._salida_pendiente = np.zeros(0, dtype=np.float32)
        self._veces_lento = 0

        self._hilo = threading.Thread(target=self._cargar_modelo, daemon=True)
        self._hilo.start()

    # ------------------------------------------------------------------ #
    #  Carga en segundo plano
    # ------------------------------------------------------------------ #
    def _cargar_modelo(self) -> None:
        try:
            import torch  # solo se importa aquí: la app base no lo requiere

            gpu_ok = torch.cuda.is_available()
            if self.perfil.parametros_ia.usar_gpu and not gpu_ok:
                self.eventos.put((
                    "ia_fallo",
                    "No se detectó GPU (torch.cuda no disponible); fallback a DSP",
                ))
                return
            self.eventos.put(("ia_gpu", "✔ GPU detectada" if gpu_ok else "IA en CPU"))
        except ImportError:
            self.eventos.put((
                "ia_fallo",
                "PyTorch no está instalado; el Modo IA queda desactivado",
            ))
            return

        plugin = self._importar_plugin()
        if plugin is None:
            return
        try:
            ruta_modelo = self._resolver_ruta_modelo()
            motor_modelo = plugin.cargar(
                str(ruta_modelo), bool(self.perfil.parametros_ia.usar_gpu)
            )
        except Exception as exc:
            self.eventos.put(("ia_fallo", f"No se pudo cargar el modelo RVC: {exc}"))
            return

        with self._lock:
            self._plugin = plugin
            self._motor_modelo = motor_modelo
            self.activo = True
        self.eventos.put((
            "ia_lista",
            f"Modelo cargado: {Path(ruta_modelo).name}",
        ))

    def _importar_plugin(self) -> Any | None:
        if not self.ruta_plugin.exists():
            self.eventos.put((
                "ia_fallo",
                f"Falta el plugin {self.ruta_plugin}. Ver modelos/LEEME.md",
            ))
            return None
        try:
            spec = importlib.util.spec_from_file_location("plugin_rvc", self.ruta_plugin)
            if spec is None or spec.loader is None:
                raise ImportError("spec nulo")
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            cargar: Callable[..., Any] = getattr(modulo, "cargar")
            inferir: Callable[..., Any] = getattr(modulo, "inferir")
            self._fn_inferir = inferir
            return modulo
        except Exception as exc:
            self.eventos.put(("ia_fallo", f"Plugin RVC inválido: {exc}"))
            return None

    def _resolver_ruta_modelo(self) -> Path:
        ruta = Path(self.perfil.parametros_ia.modelo_rvc)
        if not ruta.is_absolute():
            ruta = Path.cwd() / ruta
        if not ruta.exists():
            raise FileNotFoundError(f"Modelo no encontrado: {ruta}")
        return ruta

    # ------------------------------------------------------------------ #
    #  Procesamiento en streaming (mismo contrato que los efectos DSP)
    # ------------------------------------------------------------------ #
    def procesar(self, bloque: np.ndarray) -> np.ndarray:
        """Acumula hasta un chunk, infiere y devuelve audio alineado.

        Mientras el primer chunk se infiere, devuelve silencio (latencia
        inicial ≈ TAMANIO_CHUNK/sr, indicada en la UI como 'IA · alta').
        """
        n = len(bloque)
        salida = np.zeros(n, dtype=np.float32)
        if not self.activo:
            return bloque.astype(np.float32, copy=False)

        self._entrada = np.concatenate([self._entrada, bloque.astype(np.float32)])

        if len(self._entrada) >= TAMANIO_CHUNK:
            chunk = self._entrada[:TAMANIO_CHUNK]
            self._entrada = self._entrada[TAMANIO_CHUNK:]
            t0 = time.perf_counter()
            try:
                with self._lock:
                    resultado = self._fn_inferir(  # type: ignore[attr-defined]
                        self._motor_modelo,
                        chunk,
                        int(self.perfil.parametros_ia.pitch_rvc),
                        float(self.perfil.parametros_ia.index_rate),
                        self.sr,
                    )
            except Exception as exc:
                self._desactivar(f"Error de inferencia: {exc}")
                return salida
            duracion = time.perf_counter() - t0
            if not self._tiempo_real_suficiente(duracion):
                return salida
            if resultado is not None and len(resultado):
                self._salida_pendiente = np.concatenate(
                    [self._salida_pendiente,
                     np.asarray(resultado, dtype=np.float32).ravel()]
                )

        disponible = min(n, len(self._salida_pendiente))
        if disponible:
            salida[:disponible] = self._salida_pendiente[:disponible]
            self._salida_pendiente = self._salida_pendiente[disponible:]
        return salida

    def _tiempo_real_suficiente(self, duracion_inferencia: float) -> bool:
        """Guarda anti-latencia: la IA en CPU lenta se autodesactiva."""
        presupuesto = TAMANIO_CHUNK / self.sr * FACTOR_SEGURIDAD_RT
        if duracion_inferencia <= presupuesto:
            self._veces_lento = 0
            return True
        self._veces_lento += 1
        if self._veces_lento >= BLOQUES_TOLERANCIA_LENTITUD:
            self._desactivar(
                "La inferencia es más lenta que el tiempo real; fallback a DSP"
            )
            return False
        return True

    def _desactivar(self, motivo: str) -> None:
        self.activo = False
        self.eventos.put(("ia_fallo", motivo))
