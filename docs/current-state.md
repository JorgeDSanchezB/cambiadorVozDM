# Estado actual — `voz_dnd`

> Snapshot del proyecto para que un agente entre sin releerlo todo. Actualiza
> este archivo cuando cambie el estado real.

## Ejecutar y verificar (Windows, venv de Python 3.14)

- Python del proyecto: `voz_dnd\.venv\Scripts\python.exe` (usar siempre este).
- Arranque: `voz_dnd\iniciar_voz_dnd.bat` (o `python main.py` dentro de
  `voz_dnd\`).
- **No hay suite de tests / CI / linter.** "Verificación" =
  `python -m py_compile <archivos>` + smoke tests headless (importar el motor,
  alimentar arrays sintéticos `(frames, 1)` float32, comprobar que no lanza).

## Qué está hecho y funcionando

- **Motor DSP completo** (modo base): PitchShifter, FormantShifter, Distorsión,
  RingMod, EQ 3 bandas, Reverb, Ganancia. Vectorizado y RT-safe.
- **Stream full-duplex** (`motor_audio.py`) con callback RT-safe.
- **Grabación** post-DSP a MP3 (pydub/ffmpeg) con fallback WAV.
- **20 voces** en `data/voces/` (incl. `neutral` garantizada): las 4 originales
  (neutral, goblin, dragon, tabernero) + 16 nuevas (orco, villano_*, bandido,
  bardo, viejito/a, dios_*, diosa, heroe, goku, chica_inocente, mujer_*).
- **Editor data-driven** desde `parametros.json` + preview 2 s + "guardar como
  nueva voz".
- **Atajos F1–F12 / Shift+F1–F6** configurables en `config.json`.
- **Botón pausar/reanudar micrófono** (barra superior; `pausar()`/`reanudar()`
  en `MotorAudio`).

## Bugs conocidos ya corregidos (referencia)

- `_par_dispositivos()` resolvía `None`/ids inválidos a `_sd.default.device`
  y validaba canales — antes fallaba con `Error querying device -1`.
- `_guardar()` de Ajustes no incluía `atajos` en `ConfigApp` — los atajos no
  persistían.
- `modulo_ia._detectar_backend()` cortaba la detección ANTES de ONNX si
  `import torch` fallaba (todo `except ImportError: return None`); ahora ONNX
  se detecta por separado y `esta_gpu()` reporta
  `onnx_cpu → "Sin aceleración GPU · ONNX · CPU (portátil)"`.

## Modo IA — estado e infraestructura

- Infraestructura **multimotor** lista (`modulo_ia.py` + `rvc_adapter.py`):
  PyTorch RVC → ONNX RVC → DSP, con adaptador inyectable (`adapter=`).
- **En este equipo (Python 3.14, AMD sin CUDA)**: `rmvpe-onnx` + `onnxruntime`
  instalados → el modo IA reporta *ONNX · CPU (portátil)* y el pipeline mínimo
  (`_PipelineOnnxMinimo`) carga RMVPE y procesa sin romper.
- **Pendiente / limitación conocida**: la **conversión RVC completa** (clonar
  la voz) aún no está conectada de verdad. El punto está marcado en
  `_PipelineOnnxMinimo.convertir()` (hoy devuelve el chunk sin convertir —
  base no destructiva) y falta conectar `_construir_converter_pytorch()` a la
  API del paquete RVC. Para clonar una voz se necesita un modelo entrenado
  (.pth→onnx) y terminar esa conexión.
- Sin modelo/motor: `esta_listo()==False` es el estado esperado; degrada a DSP
  sin cortar audio.

## Restricción crítica: Python 3.14

El venv es **Python 3.14**. `rvc`, `numba` y `tts-with-rvc-onnx` **no son
compatibles** con 3.14. Solo funcionan aquí `rmvpe-onnx` + `onnxruntime` (CPU).
No `pip install torch` esperando que RVC funcione — el wheel CPU no corre RVC
y ya se desinstaló. Todo RVC en esta máquina debe ir por la vía ONNX (CPU).

## Repo: dos apps python hermana

- `voz_dnd/` — **la app activa** (estructura `app/{domain,engine,gui}`).
- `cambiador-voz-dnd/` — hermano **más antiguo**, otro layout
  (`dominio/`/`aplicacion/`/`infraestructura/`). Ambos en git. **Editar
  `voz_dnd/`, no `cambiador-voz-dnd/`** salvo que la tarea diga lo contrario.

## Raíz del repo: plantilla de despliegue (mayormente no usada)

La raíz contiene un scaffold Next.js (shadcn/Prisma SQLite) + pipeline
`.zscripts/` (standalone Next + Caddy + bundling Python, target
`/home/z/my-project`) + `mini-services/`. Es infraestructura de plantilla;
el trabajo de app vive en `voz_dnd/`.
