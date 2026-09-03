# 003 — Modo IA multimotor con degradación con gracia

- **Fecha**: trabajo sobre `voz_dnd/` (ver `docs/current-state.md`)
- **Estado**: aceptado (evolución del diseño original que asumía RVC/CUDA)

## Contexto

El modo IA (clonación de voz con RVC) debe funcionar en cualquier PC (AMD,
Intel, NVIDIA, Apple Silicon, CPU) sin exigir CUDA ni una versión concreta de
Python, y **degradar con gracia** cuando no hay motor/modelo disponible.

## Decisión

- **Multimotor con auto-detección en tiempo de ejecución** (`rvc_adapter.py`),
  probando en orden: PyTorch RVC → ONNX RVC → ninguno (degrade a DSP).
- `ModuloIA` no conoce las APIs de los motores: espera un objeto con `.listo`
  y `.procesar()`. `_detectar_backend()` reporta el mejor backend real
  (onnx_dml / onnx_cuda / cuda / directml / rocm / mps / onnx_cpu / cpu).
- Cada instalación puede **inyectar su propio `adapter=`** a `ModuloIA` con
  prioridad sobre los motores embebidos.
- Sin motor/modelo listo, `esta_listo() == False` es un **estado correcto**: el
  audio sigue sonando por la cadena DSP (`ProcesadorIA.degradado`) sin caerse.

## Contexto adicional (Python 3.14)

En la máquina actual el venv es **Python 3.14**: `rvc`, `numba` y
`tts-with-rvc-onnx` no son compatibles; solo `rmvpe-onnx` + `onnxruntime`
(CPU). Se desinstaló el `torch` CPU (el wheel CPU no corre RVC). Todo RVC en
este equipo va por ONNX (CPU).

## Consecuencias

- El modo IA es detectable y reporta el hardware real en cualquier máquina.
- El pipeline ONNX mínimo (`_PipelineOnnxMinimo`) carga RMVPE y procesa sin
  romper, pero la **conversión RVC completa** (clonar voz) queda como punto de
  conexión pendiente en `convertir()` y en `_construir_converter_pytorch()`.
- Nunca se exige un motor; el sistema siempre entrega audio.
