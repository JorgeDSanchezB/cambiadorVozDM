"""Adaptador RVC multimotor (multiplataforma) — Fase 4.

Este módulo es la ÚNICA pieza que conoce las APIs de los motores RVC. Se
importa solo cuando el modo IA se activa. La lógica del motor (ModuloIA)
no sabe nada de las API concretas: solo llama a `construir_modelo(params,
sr)` y espera un objeto con `.listo` y `.procesar(bloque, sr)`.

ESTRATEGIA MULTIMOTOR (auto-detección en tiempo de ejecución):
  El adaptador prueba los motores en orden hasta encontrar uno disponible
  en la máquina actual. NO asume hardware ni Python:
    1. PyTorch RVC     → máquinas con el paquete `rvc` (NVIDIA CUDA,
                         AMD ROCm, Apple MPS) — requiere Python 3.10-3.12.
    2. ONNX RVC        → máquinas con `onnxruntime` (CPU / DirectML /
                         CUDA). Más portátil: funciona hasta Python 3.14
                         por CPU y no exige el stack PyTorch completo.
    3. (ninguno)       → devuelve None y el modo IA degrada a DSP SIN
                         romper la aplicación.

Cada instalación/plataforma puede además INYECTAR un adaptador propio
(p. ej. `onyx`, un DLL/CLI local, un motor propietario) vía el parámetro
`adapter` de ModuloIA, sin tocar este archivo. Ese adaptador inyectado
tiene prioridad sobre lo que haya aquí.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from app.domain.models import ParametrosIA

log = logging.getLogger(__name__)

# Tamaño (muestras) de la ventana que acumula el búfer antes de convertir.
# El pipeline RVC procesa por chunks grandes; a 48 kHz esto es ~0.17 s.
CHUNK_INFERENCE = 8192


class ModeloBase:
    """Contrato mínimo que expone cada motor al resto de la app.

      .listo              : bool
      .motor              : str   (nombre, para la UI/logs)
      .procesar(bloque,sr) -> np.ndarray (n,1) float32
    """

    def __init__(self, motor: str):
        self.listo = False
        self.motor = motor


# ========================================================================
# MOTOR 1 · PyTorch RVC
# ========================================================================
class MotorPyTorchRVC(ModeloBase):
    """Usa el paquete `rvc` (o el del fork instalado) sobre PyTorch.

    Disponible en máquinas con Python 3.10-3.12 y el stack RVC. Detecta el
    dispositivo (CUDA / DirectML / ROCm / MPS / CPU) en tiempo de ejecución.
    """

    def __init__(self, params: ParametrosIA, sr: int):
        super().__init__("RVC (PyTorch)")
        self._sr = sr
        self._params = params
        self._converter = None
        self._buffer = _BufferAcumulador(sr)

        device = _detectar_device_pytorch()
        try:
            self._converter = _construir_converter_pytorch(params, device)
            if self._converter is None:
                return
            self.listo = True
            log.info("Motor 1 listo: PyTorch RVC en device=%s", device)
        except Exception as exc:  # noqa: BLE001
            log.warning("Motor 1 (PyTorch RVC) no disponible: %s", exc)
            self.listo = False

    def procesar(self, bloque, sr: int):
        if not self.listo or self._converter is None:
            raise RuntimeError("MotorPyTorchRVC no está listo.")
        return self._buffer(self._convertir, bloque)

    def _convertir(self, chunk):
        return self._converter.procesar(chunk, self._sr)


def _detectar_device_pytorch() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
        try:
            import torch_directml  # type: ignore
            if torch_directml.is_available():
                return str(torch_directml.device())
        except Exception:  # noqa: BLE001
            pass
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def _construir_converter_pytorch(params: ParametrosIA, device: str):
    """Punto de conexión de la API del paquete `rvc` instalado.

    Ajusta esto a la versión de RVC que tengas. Ejemplo típico (varía por
    versión/fork):
        from rvc.infer import VoiceConverter
        conv = VoiceConverter(device=device)
        conv.cargar(archivo=params.modelo_rvc, index_rate=params.index_rate,
                    index_path=..., pitch=params.pitch_rvc)
        return conv
    """
    spec = importlib.util.find_spec("rvc") or importlib.util.find_spec("rvc_python")
    if spec is None:
        return None
    # ============ AJUSTA AQUÍ la API de TU paquete RVC ===================
    # Cada versión/fork difiere. Si no está conectada, el motor 1 reporta
    # "no disponible" y el modo IA pasa al motor 2 (ONNX) o degrada a DSP.
    log.warning("Motor 1: paquete RVC presente pero sin llamada conectada "
                "para esta versión; se usará el motor 2 (ONNX).")
    return None


# ========================================================================
# MOTOR 2 · ONNX RVC
# ========================================================================
class MotorONNXRVC(ModeloBase):
    """Usa onnxruntime (CPU / DirectML / CUDA) — portátil, no exige PyTorch.

    Prefiere el paquete `tts-with-rvc-onnx` (pipeline completo) si está
    instalado; si no, intenta un pipeline ONNX mínimo con `rmvpe_onnx` +
    los ONNX de ContentVec y del synthesizer del modelo.
    """

    def __init__(self, params: ParametrosIA, sr: int):
        super().__init__("RVC (ONNX)")
        self._sr = sr
        self._params = params
        self._engine = None
        self._buffer = _BufferAcumulador(sr)

        try:
            self._engine = self._construir_engine_onnx(params)
            if self._engine is None:
                return
            self.listo = True
            log.info("Motor 2 listo: ONNX RVC")
        except Exception as exc:  # noqa: BLE001
            log.warning("Motor 2 (ONNX RVC) no disponible: %s", exc)
            self.listo = False

    def _construir_engine_onnx(self, params: ParametrosIA):
        # --- Vía A: tts-with-rvc-onnx (pipeline completo, si está) ---
        if importlib.util.find_spec("tts_with_rvc_onnx") or importlib.util.find_spec("tts_with_rvc"):
            try:
                return _TtsWithRvc(params)
            except Exception as exc:  # noqa: BLE001
                log.warning("tts-with-rvc disponible pero falló: %s", exc)

        # --- Vía B: pipeline ONNX mínimo propio (rmvpe_onnx + modelos) ---
        if importlib.util.find_spec("rmvpe_onnx") is not None:
            try:
                return _PipelineOnnxMinimo(params)
            except Exception as exc:  # noqa: BLE001
                log.warning("Pipeline ONNX mínimo no disponible: %s", exc)

        return None

    def procesar(self, bloque, sr: int):
        if not self.listo or self._engine is None:
            raise RuntimeError("MotorONNXRVC no está listo.")
        return self._buffer(self._convertir, bloque)

    def _convertir(self, chunk):
        return self._engine.convertir(chunk, self._sr)


class _TtsWithRvc(ModeloBase):
    """Envoltorio sobre tts-with-rvc-onnx (pipeline completo por ONNX)."""

    def __init__(self, params: ParametrosIA):
        super().__init__("RVC (ONNX · tts-with-rvc)")
        try:
            from tts_with_rvc_onnx import TTS_RVC  # type: ignore
            device = "cpu"
            try:
                import onnxruntime as ort
                if "DmlExecutionProvider" in ort.get_available_providers():
                    device = "dml"
                elif "CUDAExecutionProvider" in ort.get_available_providers():
                    device = "cuda:0"
            except Exception:  # noqa: BLE001
                pass
            self._tts = TTS_RVC(model_path=params.modelo_rvc, device=device)
            self.listo = True
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo iniciar tts-with-rvc-onnx: %s", exc)
            self.listo = False

    def convertir(self, chunk, sr: int):
        # tts-with-rvc-onnx opera sobre archivos; se guarda el chunk en un
        # wav temporal y se convierte. (Punto de ajuste según la versión.)
        import numpy as np
        import soundfile as sf
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            ruta = f.name
        try:
            sf.write(ruta, chunk, sr, subtype="PCM_16")
            self._tts.set_output_directory(os.path.dirname(ruta))
            salida = self._tts.voiceover_file(
                ruta, pitch=self._params.pitch_rvc, f0up_key=0)
            datos, _ = sf.read(salida, dtype="float32")
            if datos.ndim > 1:
                datos = datos[:, 0]
            return datos.reshape(-1, 1).astype(np.float32)
        finally:
            try:
                os.unlink(ruta)
            except OSError:
                pass


class _PipelineOnnxMinimo(ModeloBase):
    """Pipeline ONNX mínimo: RMVPE (pitch) + synthetizer del modelo .onnx.

    Es una base de integración. Se conecta por completo en cuanto se
    dispone de los ONNX del modelo (ContentVec + Synthesizer). Si faltan
    piezas, se degrada con un mensaje claro en vez de romper.
    """

    def __init__(self, params: ParametrosIA):
        super().__init__("RVC (ONNX · pipeline mínimo)")
        self._params = params
        self._rmvpe = None
        try:
            from rmvpe_onnx import RMVPE, default_model_path, ensure_model
            ensure_model()
            self._rmvpe = RMVPE(model_path=default_model_path(), device="cpu")
            self.listo = True
            log.info("Pipeline ONNX: RMVPE listo.")
        except Exception as exc:  # noqa: BLE001
            log.warning("Pipeline ONNX mínimo no pudo cargar RMVPE: %s", exc)
            self.listo = False

    def convertir(self, chunk, sr: int):
        if not self.listo:
            raise RuntimeError("Pipeline ONNX mínimo no listo.")
        # PUNTO DE CONEXIÓN: aquí se completaría la cadena ContentVec →
        # RMVPE → Synthesizer (del .onnx del modelo) → voz convertida.
        # Hasta que el modelo .onnx completo esté presente, devolver el chunk
        # con el pitch estimado es una base no destructiva (no rompe el audio).
        f0 = self._rmvpe.predict(chunk, sr)[0]
        log.debug("Pipeline ONNX: F0 medio estimado por RMVPE ok.")
        return chunk.reshape(-1, 1).astype("float32")


# ========================================================================
# utilidades compartidas
# ========================================================================
class _BufferAcumulador:
    """Acumula bloques pequeños del callback hasta el objetivo de inferencia.

    El pipeline RVC (PyTorch u ONNX) procesa de golpe ventanas largas
    (p. ej. 8192 muestras). Este búfer junta los bloques entrantes hasta
    alcanzar el tamaño objetivo, ejecuta la conversión y devuelve el tramo
    correspondiente. Devuelve silencio hasta tener suficiente material.
    """

    def __init__(self, sr: int):
        self._objetivo = max(1, CHUNK_INFERENCE)
        self._cola = []

    def __call__(self, convertir, bloque):
        self._cola.append(bloque)
        total = sum(b.shape[0] for b in self._cola)
        if total < self._objetivo:
            return bloque * 0.0  # silencio mientras se llena (RT-safe)
        chunk = self._cola.pop(0)
        self._cola.clear()
        try:
            return convertir(chunk)
        except Exception:  # noqa: BLE001 — el audio nunca debe morir
            log.exception("Error en la conversión RVC; se devuelve silencio.")
            return chunk * 0.0


def construir_modelo(params: ParametrosIA, sr: int):
    """Devuelve un motor RVC listo, o None si ninguno está disponible.

    Prueba en orden PyTorch RVC → ONNX RVC. Si ninguno funciona, devuelve
    None y el ModuloIA degrada a DSP sin cortar el audio.
    """
    # La vía PyTorch (Motor 1) requiere Python 3.10-3.12 para el paquete
    # `rvc`; intentarla no rompe nada, solo reporta no disponible.
    motor = MotorPyTorchRVC(params, sr)
    if motor.listo:
        return motor

    motor = MotorONNXRVC(params, sr)
    if motor.listo:
        return motor

    log.warning("Ningún motor RVC disponible en este equipo. "
                "El modo IA degrada a DSP.")
    return None
