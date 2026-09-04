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
import threading
from pathlib import Path

import numpy as np
import librosa
from scipy import signal
import onnxruntime as ort

from app.domain.models import ParametrosIA

log = logging.getLogger(__name__)

# La inferencia del pipeline RVC (ContentVec + RMVPE + Synthesizer) procesa
# por ventanas de ~1 s de audio a la tasa de la app. Este valor se usa como
# pista documental; el búfer real toma `sr` muestras como ventana (= 1 s).
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
        self.error = ""


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
            self._engine = self._construir_engine_onnx(params, self._sr)
            if self._engine is None:
                return
            # El motor externo refleja la preparación real del pipeline interno.
            self.listo = bool(self._engine.listo)
            if self.listo:
                self._buffer.iniciar()
                log.info("Motor 2 listo: ONNX RVC (%s)", self._engine.motor)
            else:
                log.warning("Motor 2 (ONNX RVC) no listo: %s",
                            getattr(self._engine, "error", "sin detalle"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Motor 2 (ONNX RVC) no disponible: %s", exc)
            self.listo = False

    def detener(self) -> None:
        """Detiene el hilo de inferencia (p. ej. al cambiar de voz o cerrar)."""
        self._buffer.detener()

    def _construir_engine_onnx(self, params: ParametrosIA, sr: int):
        # --- Vía A: tts-with-rvc-onnx (pipeline completo, si está) ---
        if importlib.util.find_spec("tts_with_rvc_onnx") or importlib.util.find_spec("tts_with_rvc"):
            try:
                return _TtsWithRvc(params)
            except Exception as exc:  # noqa: BLE001
                log.warning("tts-with-rvc disponible pero falló: %s", exc)

        # --- Vía B: pipeline ONNX completo propio (ContentVec + RMVPE + Synth) ---
        if importlib.util.find_spec("rmvpe_onnx") is not None:
            try:
                return _PipelineOnnxRVC(params, sr)
            except Exception as exc:  # noqa: BLE001
                log.warning("Pipeline ONNX completo no disponible: %s", exc)

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


# ========================================================================
# Pipeline ONNX completo (ContentVec + RMVPE + Synthesizer)
# ========================================================================
# Implementa la conversión real de voz (clonación) en PURO onnxruntime, sin
# PyTorch — compatible con Python 3.14. Sigue la convención del RVC ONNX
# estándar (ContentVec → F0 → Synthesizer), igual que el envoltorio
# rvc-onnx de la comunidad.
#
# Piezas necesarias:
#   1. ContentVec (hubert) ONNX  — público (vec-256-layer-9 / vec-768-layer-12)
#   2. RMVPE (pitch) ONNX        — público (lo aporta rmvpe_onnx)
#   3. Synthesizer (voz) ONNX    — EL MODELO ENTRENADO DE TU PERSONAJE
#
# Sin un Synthesizer (modelo.ts / modelo.onnx del personaje), la clonación
# NO puede producir la voz nueva; solo se degrada con un mensaje claro y el
# audio sigue sonando por DSP (no se rompe).

# Frecuencias de muestreo del pipeline.
_SR_HUBERT = 16000   # ContentVec y RMVPE operan a 16 kHz
_WINDOW = 160        # 10 ms por frame a 16 kHz
_TGT_SR_DEFECTO = 40000  # salida del Síntesis v2 (se lee de metadatos si existe)

# Repos HF con los modelos públicos de ContentVec (hubert) en ONNX.
_HF_REPO_VEC = "NaruseMioShirakana/MoeSS-SUBModel"
_VEC_V1 = "vec-256-layer-9.onnx"
_VEC_V2 = "vec-768-layer-12.onnx"


def _providers_ondx() -> list[str]:
    """Devuelve los providers de onnxruntime mejores disponibles (sin PyTorch).

    Prioridad: DirectML (AMD/Intel/NVIDIA en Windows) → CUDA → CPU.
    """
    try:
        import onnxruntime as ort
        disponibles = ort.get_available_providers()
        preferidos = ["DmlExecutionProvider", "CUDAExecutionProvider",
                      "CPUExecutionProvider"]
        elegidos = [p for p in preferidos if p in disponibles]
        # onnxruntime exige que el proveedor "CPU" esté en la lista.
        if "CPUExecutionProvider" not in elegidos:
            elegidos.append("CPUExecutionProvider")
        return elegidos if elegidos else None
    except Exception:  # noqa: BLE001
        return ["CPUExecutionProvider"]


def _asegurar_contentvec(modelo_synth_path: Path | str,
                         vec_dim: int) -> str | None:
    """Descarga/resuelve el modelo ContentVec (hubert) ONNX que corresponde.

    `vec_dim` es la dimensión de características de ContentVec (256 → v1,
    768 → v2). Se descarga de HuggingFace a data/modelos/ la primera vez;
    si falta red o falla, devuelve None (el pipeline degrada).
    """
    from app.rutas import DATA_DIR
    nombre = _VEC_V2 if vec_dim >= 512 else _VEC_V1
    destino = DATA_DIR / "modelos" / nombre
    if destino.exists():
        return str(destino)
    try:
        from huggingface_hub import hf_hub_download
        destino.parent.mkdir(parents=True, exist_ok=True)
        log.info("Descargando ContentVec (%s) desde HuggingFace ...", nombre)
        ruta = hf_hub_download(repo_id=_HF_REPO_VEC, filename=nombre)
        import shutil
        shutil.copy(ruta, destino)
        log.info("ContentVec listo en %s", destino)
        return str(destino)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo obtener ContentVec (%s): %s", nombre, exc)
        return None


class _PipelineOnnxRVC(ModeloBase):
    """Conversión de voz RVC completa por ONNX (ContentVec + RMVPE + Synth).

    El synthesizer (modelo del personaje) es obligatorio; ContentVec y RMVPE
    se resuelven/descargan de HuggingFace la primera vez. Si falta cualquier
    pieza, `listo=False` y el modo IA degrada a DSP sin romper el audio.
    """

    def __init__(self, params: ParametrosIA, app_sr: int):
        super().__init__("RVC (ONNX · completo)")
        self._params = params
        self._app_sr = app_sr
        self._vec = None           # session ContentVec
        self._rmvpe = None         # predictor RMVPE
        self._synth = None         # session Synthesizer
        self._formato = None       # "narrow" | "full"
        self._vec_dim = 0          # dim de ContentVec (256 v1 | 768 v2)
        self._tgt_sr = _TGT_SR_DEFECTO
        self._f0_min, self._f0_max = 50.0, 1100.0
        self._protect = 0.33
        try:
            self._cargar_synthesizer(params)
            if self._synth is None:
                return
            self._cargar_rmvpe()
            self._cargar_contentvec()
            if self._vec is None or self._rmvpe is None:
                self.error = ("Falta una pieza ONNX (ContentVec o RMVPE). "
                              "Se degrada a DSP.")
                log.warning("%s", self.error)
                self.listo = False
                return
            self.listo = True
            log.info("Pipeline ONNX RVC listo (formato=%s, vec_dim=%d).",
                     self._formato, self._vec_dim)
        except Exception as exc:  # noqa: BLE001
            self.error = f"Fallo al iniciar pipeline ONNX RVC: {exc}"
            log.warning("%s", self.error)
            self.listo = False

    # ------------------------------------------------------------------ #
    # Carga de las 3 piezas
    # ------------------------------------------------------------------ #
    def _cargar_synthesizer(self, params: ParametrosIA) -> None:
        ruta = Path(params.modelo_rvc)
        if not str(params.modelo_rvc).strip() or not ruta.is_file():
            self.error = f"Synthesizer RVC no encontrado: {params.modelo_rvc}"
            log.warning("%s", self.error)
            return
        providers = _providers_ondx()
        sess = ort.InferenceSession(str(ruta), providers=providers)
        entradas = sess.get_inputs()
        nombres = [e.name for e in entradas]

        if len(entradas) >= 6 and "hubert" in nombres:
            # Formato "full": hubert/hubert_length/pitch/pitchf/ds/rnd.
            self._formato = "full"
            shp = entradas[nombres.index("hubert")].shape  # (1, 2*dim, T)
            if shp and len(shp) == 3 and shp[1] and shp[1] != "?":
                self._vec_dim = int(shp[1]) // 2          # 256 (v1) | 768 (v2)
            else:
                self._vec_dim = 768
            meta = sess.get_modelmeta().custom_metadata_map
            try:
                import json as _json
                cfg = _json.loads(meta.get("config", "[]"))
                if isinstance(cfg, (list, tuple)) and cfg and \
                        not isinstance(cfg[0], dict):
                    self._tgt_sr = int(cfg[-1])
            except Exception:  # noqa: BLE001
                pass
        elif len(entradas) >= 3 and "phone" in nombres:
            # Formato "narrow": phone/pitch/pitchf (vec integrado en el synth).
            self._formato = "narrow"
            shp = entradas[nombres.index("phone")].shape  # (1, seq, dim)
            if shp and len(shp) == 3 and shp[2] and shp[2] != "?":
                self._vec_dim = int(shp[2])               # 256 (v1) | 768 (v2)
            else:
                self._vec_dim = 768
            self._tgt_sr = 0   # se deduce en el primer forward real
        else:
            self.error = (f"Synthesizer RVC con esquema inesperado "
                          f"({nombres}). Se degrada.")
            log.warning("%s", self.error)
            return

        self._synth = sess
        log.info("Synthesizer ONNX: formato=%s vec_dim=%d tgt_sr=%s",
                 self._formato, self._vec_dim, self._tgt_sr or "por-deducir")

    def _cargar_rmvpe(self) -> None:
        try:
            from rmvpe_onnx import RMVPE as _RMVPE, default_model_path, ensure_model
            ensure_model()
            self._rmvpe = _RMVPE(model_path=default_model_path(), device="cpu")
        except Exception as exc:  # noqa: BLE001
            log.warning("RMVPE no disponible: %s", exc)
            self._rmvpe = None

    def _cargar_contentvec(self) -> None:
        ruta_vec = _asegurar_contentvec(self._params.modelo_rvc, self._vec_dim)
        if ruta_vec is None:
            return
        self._vec = ort.InferenceSession(ruta_vec, providers=_providers_ondx())

    # ------------------------------------------------------------------ #
    # Preproceso / F0 / características
    # ------------------------------------------------------------------ #
    @staticmethod
    def _preprocesar(audio: np.ndarray) -> np.ndarray:
        """Normaliza amplitud, filtra paso-alto (48 Hz) y pad reflectante."""
        mx = np.abs(audio).max()
        if mx > 1:
            audio = audio / (mx / 0.95)
        bh, ah = signal.butter(5, 48, btype="high", fs=_SR_HUBERT)
        audio = signal.filtfilt(bh, ah, audio)
        return np.pad(audio, (_WINDOW // 2, _WINDOW // 2), mode="reflect")

    def _extract_f0_series(self, audio16k: np.ndarray, f0_up: int = 0) -> np.ndarray:
        """Estima la curva F0 (Hz) por RMVPE; frames no sonoros en 0."""
        _, freq, conf, _ = self._rmvpe.predict(audio16k, _SR_HUBERT)
        pitchf = freq.astype(np.float64)
        pitchf[conf < 0.03] = 0.0
        return pitchf * (2 ** (f0_up / 12))

    def _mel_bins(self, pitchf: np.ndarray) -> np.ndarray:
        """Cuantiza una curva F0 en Hz a bins de mel en [1, 255]."""
        f0_min_mel = 1127 * np.log(1 + self._f0_min / 700)
        f0_max_mel = 1127 * np.log(1 + self._f0_max / 700)
        f0_mel = 1127 * np.log(1 + np.clip(pitchf, 1e-6, None) / 700)
        mascara = f0_mel > 0
        f0_mel[mascara] = ((f0_mel[mascara] - f0_min_mel) * 254 /
                           (f0_max_mel - f0_min_mel)) + 1
        f0_mel[f0_mel <= 1] = 1
        f0_mel[f0_mel > 255] = 255
        return np.rint(f0_mel).astype(np.int64)

    def _feats_contentvec(self, audio16k: np.ndarray) -> np.ndarray:
        """Devuelve características ContentVec time-major (1, seq, dim)."""
        wav = audio16k.reshape(-1)
        entrada = wav[np.newaxis, np.newaxis, :].astype(np.float32)
        logits = self._vec.run(
            None, {self._vec.get_inputs()[0].name: entrada})[0]
        if logits.ndim == 2:
            return logits[np.newaxis, :, :].astype(np.float32)
        if logits.shape[-1] == self._vec_dim:
            return logits.astype(np.float32)
        return logits.transpose(0, 2, 1).astype(np.float32)

    def _sintetizar(self, mono16k: np.ndarray, audio_pad: np.ndarray):
        """Forward del synthesizer según el formato detectado."""
        audio16k = audio_pad.astype(np.float32)
        if self._formato == "narrow":
            return self._sintetizar_narrow(mono16k, audio16k)
        return self._sintetizar_full(audio16k)

    def _sintetizar_narrow(self, mono16k: np.ndarray, audio16k: np.ndarray):
        # Características (1, seq, dim); pitch a la misma resolución temporal.
        feats = self._feats_contentvec(audio16k)
        seq = feats.shape[1]
        vutt = self._extract_f0_series(audio16k, self._params.pitch_rvc)
        n = len(vutt)
        xq = np.linspace(0, n - 1, seq)
        pitchf = np.interp(xq, np.arange(n), vutt).astype(np.float32)
        pitch = self._mel_bins(pitchf)[np.newaxis, :].astype(np.int64)
        pitchf = pitchf[np.newaxis, :]
        phone = feats[:, :seq, :].astype(np.float32)
        fwd = self._synth.run(None, {
            self._synth.get_inputs()[0].name: phone,
            self._synth.get_inputs()[1].name: pitch,
            self._synth.get_inputs()[2].name: pitchf,
        })[0]
        audio_opt = np.squeeze(fwd).astype(np.float32)
        # deduce la tasa de salida a partir de la duración real de entrada
        dur = max(len(mono16k) / _SR_HUBERT, 1e-6)
        self._tgt_sr = int(round(len(audio_opt) / dur))
        return audio_opt.reshape(-1, 1)

    def _sintetizar_full(self, audio16k: np.ndarray):
        feats = self._feats_contentvec(audio16k)          # (1, seq, dim) @50fps
        seq = feats.shape[1]
        vutt = self._extract_f0_series(audio16k, self._params.pitch_rvc)
        p_len = len(vutt)                                 # frames @100fps (10 ms)
        # sobremuestrea ContentVec (50 fps) a la resolución del pitch (100 fps)
        feats_t = feats[0]                                # (seq, dim)
        if seq != p_len:
            xq = np.linspace(0, seq - 1, p_len)
            feats_t = np.stack(
                [np.interp(xq, np.arange(seq), feats_t[:, c])
                 for c in range(feats_t.shape[1])], axis=1)
        feats_hubert = np.repeat(feats_t, 2, axis=1)      # (p_len, 2*dim)
        feats_hubert = feats_hubert.T[np.newaxis].astype(np.float16)  # (1,2*dim,T)
        pitchf = vutt.astype(np.float16)
        pitch = self._mel_bins(vutt)
        # protege regiones no sonoras
        if self._protect < 0.5:
            ff = pitchf.copy()
            ff[pitchf > 0] = 1.0
            ff[pitchf < 1] = self._protect
            feats_hubert = feats_hubert * ff[..., None].astype(np.float16) + \
                feats_hubert * (1.0 - ff[..., None].astype(np.float16))
        sid = np.array([0], dtype=np.int64)
        rnd = np.random.randn(1, 192, p_len).astype(np.float16)
        p_link = np.array([p_len], dtype=np.int64)
        fwd = self._synth.run(None, {
            self._synth.get_inputs()[0].name: feats_hubert,
            self._synth.get_inputs()[1].name: p_link,
            self._synth.get_inputs()[2].name: pitch,
            self._synth.get_inputs()[3].name: pitchf,
            self._synth.get_inputs()[4].name: sid,
            self._synth.get_inputs()[5].name: rnd,
        })[0]
        return np.squeeze(fwd).astype(np.float32).reshape(-1, 1)

    # ------------------------------------------------------------------ #
    # Contrato con el resto de la app
    # ------------------------------------------------------------------ #
    def convertir(self, chunk, sr: int):
        """Convierte un bloque (n,1) float32 a la voz del personaje.

        Devuelve audio a la tasa de la app (sale del synth a `_tgt_sr` y se
        remuestrea al sr entrante para que la cadena DSP/playback siga bien).
        """
        if not self.listo:
            raise RuntimeError("Pipeline ONNX RVC no listo.")
        mono = chunk.reshape(-1).astype(np.float32)
        if sr != _SR_HUBERT:
            mono = librosa.resample(mono, orig_sr=sr, target_sr=_SR_HUBERT)
        audio_pad = self._preprocesar(mono)
        salida = self._sintetizar(mono, audio_pad)    # (N,1) @ _tgt_sr
        if salida.shape[0] == 0:
            return chunk.reshape(-1, 1).astype(np.float32)
        if self._tgt_sr and self._tgt_sr != sr:
            salida = librosa.resample(salida[:, 0], orig_sr=self._tgt_sr,
                                      target_sr=sr).reshape(-1, 1)
        return salida.astype(np.float32)


# ========================================================================
# utilidades compartidas
# ========================================================================
class _BufferAcumulador:
    """Motor de streaming RVC con inferencia en hilo dedicado.

    La conversión (ContentVec + RMVPE + Synthesizer, ≈0.2 s por ventana)
    es cara; ejecutarla en el hilo de audio provocaría glitches/trabazones.
    Aquí corre en un hilo worker en segundo plano:

      1. el hilo de audio solo empuja entrada a `cola_in` y toma salida de
         `cola_out` (operación rápida, sin bloqueo por la inferencia);
      2. el worker toma ventanas de ~1 s, las convierte (con gate de silencio
         y crossfade entre ventanas) y rellena `cola_out`.

    El callback siempre devuelve `len(bloque)` muestras (silencio mientras
    aún no hay salida lista), por lo que es seguro para tiempo real.
    """

    RATIO_SILENCIO = 0.004   # umbral RMS de entrada bajo el cual se emite silencio
    _FADE_SEG = 0.015        # crossfade de 15 ms entre ventanas

    def __init__(self, sr: int):
        self._ventana = max(1, sr)                     # 1 s a la tasa de la app
        self._fade = max(1, int(sr * self._FADE_SEG))  # muestras de crossfade
        self._cola_in = np.zeros((0, 1), dtype=np.float32)
        self._cola_out = np.zeros((0, 1), dtype=np.float32)
        self._convertir = None
        self._cerrar = False
        self._cond = threading.Condition()
        self._hilo: threading.Thread | None = None
        self._iniciado = False

    # ------------------------- ciclo de vida --------------------------- #
    def iniciar(self) -> None:
        """Arranca el hilo worker (idempotente)."""
        with self._cond:
            if self._iniciado:
                return
            self._iniciado = True
            self._cerrar = False
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def detener(self) -> None:
        """Detiene el hilo worker (idempotente)."""
        with self._cond:
            self._cerrar = True
            self._cond.notify_all()
        hilo = self._hilo
        if hilo is not None:
            hilo.join(timeout=0.5)
        with self._cond:
            self._hilo = None
            self._iniciado = False

    @staticmethod
    def _servir(cola: np.ndarray, n: int):
        """Extrae `n` muestras de la cola; rellena con silencio si faltan."""
        if cola.shape[0] >= n:
            return cola[:n], cola[n:]
        faltan = n - cola.shape[0]
        pad = np.zeros((faltan, cola.shape[1]), dtype=np.float32)
        salida = np.concatenate([cola, pad], axis=0)
        return salida, np.zeros((0, cola.shape[1]), dtype=np.float32)

    # ------------------------- hilo worker ----------------------------- #
    def _bucle(self) -> None:
        while True:
            with self._cond:
                while not self._cerrar and self._cola_in.shape[0] < self._ventana:
                    self._cond.wait(timeout=0.05)
                if self._cerrar:
                    return
                ventana = self._cola_in[:self._ventana]
                self._cola_in = self._cola_in[self._ventana:]

            salida = self._inferir(ventana)

            with self._cond:
                self._cola_out = self._crossfade(self._cola_out, salida)

    def _inferir(self, ventana: np.ndarray) -> np.ndarray:
        """Convierte una ventana; si es (casi) silencio devuelve silencio."""
        # Gate de silencio: evita el ruido/artefactos del synth en silencio.
        rms = float(np.sqrt(np.mean(ventana ** 2)))
        if rms < self.RATIO_SILENCIO:
            return np.zeros((self._ventana, 1), dtype=np.float32)
        try:
            salida = self._convertir(ventana).reshape(-1, 1)
            # asegura longitud balanceada (≈1 s) para no derivar el búfer
            if salida.shape[0] > self._ventana:
                salida = salida[:self._ventana]
            elif salida.shape[0] < self._ventana:
                salida = np.pad(salida, (0, self._ventana - salida.shape[0]))
            return salida.astype(np.float32)
        except Exception:  # noqa: BLE001 — el audio nunca debe morir
            log.exception("Error en la conversión RVC; se devuelve silencio.")
            return np.zeros((self._ventana, 1), dtype=np.float32)

    def _crossfade(self, cola: np.ndarray, salida: np.ndarray) -> np.ndarray:
        """Mezcla (fade de 15 ms) el final de lo servido con el inicio nuevo."""
        fade = min(self._fade, cola.shape[0], salida.shape[0])
        if fade <= 0:
            return np.concatenate([cola, salida], axis=0)
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, None]
        mezcla = cola[-fade:] * (1.0 - ramp) + salida[:fade] * ramp
        return np.concatenate([cola[:-fade], mezcla, salida[fade:]], axis=0)

    # ------------------------- interfaz del motor ---------------------- #
    def __call__(self, convertir, bloque: np.ndarray) -> np.ndarray:
        self._convertir = convertir
        n = bloque.shape[0]
        with self._cond:
            self._cola_in = np.concatenate([self._cola_in, bloque], axis=0)
            self._cond.notify_all()
            salida, self._cola_out = self._servir(self._cola_out, n)
        return salida.astype(np.float32)


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
