"""Módulo de IA opcional (clonación de voz con RVC) — multiplataforma.

Filosofía (Fase 4): el modo IA es un MÓDULO QUE NO ROMPE NADA y que DEBE
funcionar en cualquier PC, tenga NVIDIA (CUDA), AMD (DirectML/ROCm), Intel
(DirectML) o solo CPU.

* Se importa perezosamente: PyTorch/RVC solo se tocan si el usuario los usa.
* Se detecta el MEJOR backend disponible en tiempo de ejecución (CUDA →
  DirectML → ROCm → MPS → CPU), en vez de asumir CUDA como única opción.
* Si falta cualquier pieza (paquete, backend, GPU, modelo .pth), `error`
  lo explica y el ProcesadorIA degrada a su cadena DSP post SIN cortar el
  audio. El programa NUNCA deja de funcionar por culpa del hardware.

El conector real de RVC es una función de "adaptador" invocable (pasada en
`inicializar()`), mantenida aparte para que cada instalación pueda aportar
el suyo sin tocar la lógica del motor. Si no hay adaptador, se degrada.
"""
from __future__ import annotations

import importlib.util
import logging
import platform
from pathlib import Path

from app.domain.models import ParametrosIA

log = logging.getLogger(__name__)

# Latencia inherente estimada del pipeline RVC en tiempo real (muestras).
# La inferencia de HuBERT + generador trabaja por chunks grandes.
LATENCIA_IA_MUESTRAS = 8192

# Prioridad de backends de inferencia compatibles con PyTorch.
_BACKEND_PRIORIDAD = ("cuda", "directml", "rocm", "mps", "cpu")


def _detectar_backend() -> tuple[str | None, str]:
    """Detecta el mejor backend de PyTorch disponible en esta máquina.

    Devuelve (backend, descripción). Orden: CUDA / DirectML / ROCm / MPS /
    ONNX(acelerado) / ONNX(CPU) / CPU. No asume hardware: consulta cada
    opción en tiempo de ejecución, y no requiere PyTorch para que el modo
    ONNX sea detectable (así cualquier máquina con onnxruntime lo usa).
    """
    # 1) ONNX Runtime acelerado (DirectML / CUDA-onnx) — no exige PyTorch.
    try:
        if importlib.util.find_spec("onnxruntime") is not None:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "DmlExecutionProvider" in providers:
                return "onnx_dml", "ONNX · DirectML (AMD/Intel/NVIDIA)"
            if "CUDAExecutionProvider" in providers:
                return "onnx_cuda", "ONNX · CUDA (NVIDIA)"
    except Exception:  # noqa: BLE001
        pass

    # 2) PyTorch (CUDA / DirectML / ROCm / MPS) — solo si está instalado.
    try:
        import torch  # import diferido: solo si el usuario tiene IA instalada
    except ImportError:
        # Sin PyTorch: si hay ONNX Runtime por CPU, el modo IA sigue usable.
        if importlib.util.find_spec("onnxruntime") is not None:
            return "onnx_cpu", "ONNX · CPU (portátil)"
        return None, "PyTorch y onnxruntime no instalados (modo IA opcional)"

    # 2a) CUDA (NVIDIA)
    try:
        if torch.cuda.is_available():
            nombre = torch.cuda.get_device_name(0)
            return "cuda", f"CUDA · {nombre}"
    except Exception:  # noqa: BLE001
        pass

    # 2b) DirectML (AMD / Intel / NVIDIA vía DirectX 12, Windows)
    try:
        if importlib.util.find_spec("torch_directml") is not None:
            import torch_directml  # type: ignore
            if torch_directml.is_available():
                return "directml", f"DirectML · {torch_directml.device_name(0)}"
    except Exception:  # noqa: BLE001
        pass

    # 2c) ROCm (AMD, sobre todo Linux, también Windows en 7000/9000)
    try:
        if torch.version.hip and torch.cuda.is_available():
            nombre = torch.cuda.get_device_name(0)
            return "rocm", f"ROCm · {nombre}"
    except Exception:  # noqa: BLE001
        pass

    # 2d) MPS (Apple Silicon, macOS)
    try:
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "MPS · Apple Silicon (GPU)"
    except Exception:  # noqa: BLE001
        pass

    # 3) CPU puro (garantizado). Si hay ONNX Runtime por CPU, se reporta.
    if importlib.util.find_spec("onnxruntime") is not None:
        return "onnx_cpu", "ONNX · CPU (portátil)"
    return "cpu", "CPU"

def _estrategia_adapter(backend: str) -> str:
    """Da una pista de qué backend requiere el motor RVC usado."""
    if backend in ("cuda", "onnx_cuda"):
        return "torch/ONNX con CUDA (NVIDIA)"
    if backend in ("directml", "onnx_dml"):
        return "torch-directml / ONNX DirectML (AMD/Intel/NVIDIA vía DirectX 12)"
    if backend == "rocm":
        return "torch ROCm (AMD)"
    if backend == "mps":
        return "torch con MPS (Apple Silicon)"
    if backend == "onnx_cpu":
        return "onnxruntime por CPU (portátil, funciona en cualquier Python)"
    return "torch CPU"


class ModuloIA:
    def __init__(self, params: ParametrosIA, sr: int,
                 adapter=None):
        self._params = params
        self._sr = sr
        self._adapter = adapter  # invocable parametrizable (p. ej. inyectado por una distro)
        self._listo = False
        self.error: str | None = None
        self.backend: str | None = None
        self._modelo = None

    # ------------------------------------------------------------------ #
    def esta_listo(self) -> bool:
        return self._listo

    @property
    def latencia_muestras(self) -> int:
        return LATENCIA_IA_MUESTRAS if self._listo else 0

    # ------------------------------------------------------------------ #
    @staticmethod
    def estado_gpu() -> tuple[bool, str]:
        """(hay_aceleracion, descripción) — para Ajustes y la pestaña Voces.

        "Aceleración" = algo mejor que CPU (CUDA/DirectML/ROCm/MPS).
        Muestra la info real del hardware de cada máquina.
        """
        backend, detalle = _detectar_backend()
        if backend is None:
            return False, detalle
        if backend in ("cpu", "onnx_cpu"):
            return False, f"Sin aceleración GPU · {detalle}"
        return True, detalle

    # ------------------------------------------------------------------ #
    def inicializar(self) -> None:
        """Carga del modelo. LLAMAR SOLO DESDE UN HILO EN SEGUNDO PLANO."""
        backend, detalle = _detectar_backend()
        self.backend = backend
        log.info("Modo IA: backend=%s (%s) · Python %s · %s",
                 backend, detalle, platform.python_version(), platform.system())

        if backend is None:
            self.error = (f"{detalle}. Instala PyTorch (y el adaptador RVC de tu "
                          "plataforma) para habilitar el modo IA. Mientras tanto "
                          "se usa la cadena DSP.")
            return

        if self._params.usar_gpu and backend == "cpu":
            # Sin aceleración GPU, el modo IA aún puede correr por CPU (ONNX).
            self.error = (f"No se detectó aceleración GPU en este equipo "
                          f"({detalle}). Se intentará igualmente por CPU "
                          f"(puede ser lento).")
            log.warning("Modo IA sin GPU; se intenta por CPU.")

        if not self._params.modelo_rvc:
            self.error = "Voz IA sin modelo asignado (parametros_ia.modelo_rvc)."
            return
        if not Path(self._params.modelo_rvc).exists():
            self.error = f"Modelo RVC no encontrado: {self._params.modelo_rvc}"
            return

        try:
            # ================= PUNTO DE INTEGRACIÓN RVC ==================
            # 1) Si hay un adaptador inyectado (p. ej. un motor local/DLL para
            #    esta distro), se usa con prioridad, sin tocar nada más.
            if self._adapter is not None:
                self._modelo = self._adapter(self._params, self._sr)
                if self._modelo is not None and getattr(self._modelo, "listo", True):
                    self._listo = True
                    return
                self.error = (f"Adaptador RVC no logró cargar el modelo "
                              f"({self._params.modelo_rvc}). Se degrada a DSP.")
                return

            # 2) Sin adaptador externo: se delega en el adaptador multimotor del
            #    proyecto, que detecta y usa en orden PyTorch RVC → ONNX RVC,
            #    o devuelve None (degrade a DSP) si esta máquina no tiene motor.
            from app.engine.rvc_adapter import construir_modelo  # type: ignore
            self._modelo = construir_modelo(self._params, self._sr)
            if self._modelo is None or not getattr(self._modelo, "listo", False):
                self.error = (f"No hay motor RVC disponible en este equipo "
                              f"({detalle}). Instala uno (ver README § Modo IA) "
                              f"o conecta un adaptador. Se usa la cadena DSP.")
                log.warning("Modo IA sin motor: %s", self.error)
                return
            self._listo = True
            log.info("Modo IA activado con motor: %s",
                     getattr(self._modelo, "motor", "desconocido"))
            # ===============================================================
        except ImportError as exc:
            self.error = (f"No se pudo importar el adaptador RVC "
                          f"(app/engine/rvc_adapter.py): {exc}. Se usa la cadena "
                          f"DSP.")
            log.warning(self.error)
        except Exception as exc:  # noqa: BLE001 — cualquier fallo degrada
            self.error = f"Fallo al iniciar el motor IA: {exc}"
            log.exception(self.error)

    # ------------------------------------------------------------------ #
    def procesar(self, bloque, sr: int):
        """Inferencia en tiempo real. Solo se llama si `esta_listo()`."""
        if not self._listo or self._modelo is None:
            raise RuntimeError("ModuloIA no está listo.")
        return self._modelo.procesar(bloque, sr)
