# CLAUDE.md

Guía para trabajar en este repositorio. Combina con `AGENTS.md` y `docs/`.

## Panorama del proyecto

Este repo es una **plantilla de despliegue + la app real**, no un árbol
coherente:

- **Raíz (scaffold Next.js)** — Next 16 / shadcn / Prisma(SQLite) + pipeline
  `.zscripts/` (standalone Next + Caddy + bundling Python, target
  `/home/z/my-project`). Infra de plantilla mayormente sin usar; no la toques
  para trabajo de la app.
- **`voz_dnd/` — el proyecto real y activo**: cambiador de voz en tiempo real
  para DM de D&D (Python, PyQt6, sounddevice, numpy/scipy). Todo el trabajo
  reciente vive aquí.
- **`cambiador-voz-dnd/`** — hermano MÁS ANTIGUO de `voz_dnd` con otro layout
  (`dominio/`, `aplicacion/`, `infraestructura/`). Ambos en git. **Edita
  `voz_dnd/`, no `cambiador-voz-dnd/`** salvo que la tarea diga lo contrario.

## Git rule (MANDATORY)

**NUNCA** hagas `git add`, `git commit`, `git push` ni subas cambios a ningún
repositorio **sin autorización explícita del usuario**. Aunque se te pida en
medio de una tarea, detente y espera confirmación explícita antes de tocar el
historial o el remoto.

## voz_dnd: ejecutar y verificar (Windows, venv Python 3.14)

- Python del proyecto: `voz_dnd\.venv\Scripts\python.exe` (usar siempre este,
  no el `python` del sistema).
- Punto de entrada: `voz_dnd\main.py` (GUI PyQt6). Lanzar con
  `voz_dnd\iniciar_voz_dnd.bat` en Windows.
- **No hay suite de tests / CI / linter** para esta app. "Verificar" =
  `python -m py_compile <archivos>` + smoke tests headless (importar el motor,
  alimentar arrays sintéticos `(frames, 1)` float32, comprobar que no lanza).
- Rutas resueltas por `app/rutas.py` (única fuente de verdad): datos en
  `voz_dnd\data\` (`voces/*.json`, `config.json`, `parametros.json`), logs en
  `voz_dnd\logs\app.log`.

## voz_dnd: arquitectura y gotchas

Capas: `app/domain/` (puro, sin I/O ni Qt), `app/engine/` (audio + orquestación),
`app/gui/` (PyQt6).

- **Contrato de audio en tiempo real (`motor_audio.py`)**: el callback de
  `sd.Stream` debe ser sin locks y nunca lanzar. Los efectos esperan arrays
  `(frames, 1)` float32; un array 1-D los rompe. Normaliza con
  `reshape(-1, 1)` antes/después.
- **`_par_dispositivos()`** debe resolver ids `None`/inválidos a uno real
  (`_sd.default.device`) y validar canales — los ids `None` rompían con
  `Error querying device -1`.
- **Modo IA multimotor y degradación con gracia** (`modulo_ia.py` +
  `rvc_adapter.py`): PyTorch RVC → ONNX RVC → DSP. El camino donde no hay
  motor/modelo listo debe seguir procesando audio (bypass/DSP) y **nunca
  soltar/romper el stream**. Si la máquina no tiene modelo o motor,
  `esta_listo() == False` es el estado correcto y esperado.
- Cada instalación puede inyectar su propio `adapter=` en `ModuloIA` (prioridad
  sobre los motores embebidos) — mantén ese seam.

## Restricción crítica: Python 3.14

El venv es **Python 3.14**. `rvc`, `numba` y `tts-with-rvc-onnx` **no son
compatibles** con 3.14. Solo `rmvpe-onnx` + `onnxruntime` funcionan en esta
máquina (CPU). NO `pip install torch` esperando que RVC funcione — el wheel CPU
de torch no corre RVC y ya se desinstaló aquí. Todo RVC en este equipo va por la
vía ONNX (CPU).

## Documentación

- `docs/architecture.md` — cómo funciona el sistema (capas, contrato RT, datos).
- `docs/current-state.md` — snapshot: qué está hecho y qué falta.
- `docs/decisions/` — ADRs de decisiones de diseño reales.

## Convenciones de estilo

- Código en **español** (identificadores, comentarios, docs, logs, JSON).
- Data-driven: rangos de sliders desde `data/parametros.json`; una voz = un JSON
  en `data/voces/` con `neutral` garantizada. Añade voces vía JSON, no código.
- Tolerante a JSON corrupto/ausente (config, voces, parámetros): degradar con
  banner/avisos, nunca bloquear el arranque.
- Sin comentarios salvo que aporten valor real; evita emojis en archivos.
