# AGENTS.md

## Project landscape (read this before editing)

This repo is a **deployment-sandbox template + the real app**, not a single coherent tree:

- **Root (Next.js scaffold)** — Next 16 / shadcn / Prisma(SQLite) + `.zscripts/` deploy pipeline (standalone Next + Caddy + Python runtime bundling, targets `/home/z/my-project`). Mostly unused template infra; `src/app/page.tsx` is a placeholder and `prisma/schema.prisma` is the default User/Post. Don't assume you need to touch this for app work.
- **`voz_dnd/` — the real, actively-developed project**: real-time D&D voice changer (Python, PyQt6, sounddevice, numpy/scipy). All recent/future work lives here.
- **`cambiador-voz-dnd/`** — an OLDER sibling of `voz_dnd` with a different package layout (`dominio/`, `aplicacion/`, `infraestructura/`). Both are tracked in git. **Edit `voz_dnd/`, not `cambiador-voz-dnd/`** unless the task explicitly says otherwise.

## voz_dnd: running & verifying

- Python venv already exists: `voz_dnd\.venv`. Run everything through it:
  `voz_dnd\.venv\Scripts\python.exe` (on Windows). Do not use a system `python`.
- Entry point: `voz_dnd\main.py` (PyQt6 GUI). Launch via `voz_dnd\iniciar_voz_dnd.bat` on Windows.
- **There is no test suite / CI / linter config** for this app. "Verification" = `python -m py_compile <files>` plus hand-written headless smoke tests (import the engine, feed synthetic `(frames,1)` float32 arrays, assert it doesn't raise).
- Paths are resolved relative to the package via `app/rutas.py` (single source of truth): voice/config data lives in `voz_dnd\data\` (`voces/*.json`, `config.json`, `parametros.json`), logs in `voz_dnd\logs\app.log`.

## voz_dnd: architecture & hard-won gotchas

Layers: `app/domain/` (pure, no I/O/Qt), `app/engine/` (audio + orchestration), `app/gui/` (PyQt6).

- **Real-time audio contract (`motor_audio.py`)**: the `sd.Stream` callback must stay lock-free and never raise. Effects expect `(frames, 1)` float32 arrays; passing 1-D breaks them. Normalize with `reshape(-1, 1)` before/after.
- **`_par_dispositivos()`** must resolve `None`/invalid device ids to real ones (`_sd.default.device`) and validate channel counts — `None` ids used to crash with `Error querying device -1`.
- **IA mode is multi-engine and must degrade gracefully** (`modulo_ia.py` + `rvc_adapter.py`): PyTorch RVC → ONNX RVC → plain DSP. The path where no engine/model is ready must still process audio (bypass/DSP) and **never drop/crash the stream**. If the user's machine has no IA model or engine, `esta_listo()==False` is the expected, correct state.
- Each installation can inject its own `adapter=` into `ModuloIA` (priority over built-in engines) — keep that seam working.

## Python 3.14 constraint (critical)

The venv is **Python 3.14**. The `rvc` package, `numba`, and `tts-with-rvc-onnx` are **not compatible** with 3.14. Only `rmvpe-onnx` + `onnxruntime` work on this machine (CPU path). Do NOT `pip install torch` expecting RVC to work — the CPU torch wheel won't run RVC and was already uninstalled here. Any RVC work on this box is via the ONNX (CPU) path only.

## Git rule (MANDATORY)

**NUNCA** hagas `git add`, `git commit`, `git push` ni subas cambios a ningún
repositorio **sin autorización explícita del usuario**. Aunque se te pida en
medio de una tarea, detente y espera confirmación explícita antes de tocar el
historial o el remoto.

## Style conventions

- Codebase is Spanish-language (identifiers, comments, docs, log messages, JSON values). Follow suit.
- Data-driven: slider ranges come from `data/parametros.json`; one voice = one JSON file in `data/voces/` with a guaranteed `neutral` voice. Add/extend voices via JSON, not code.
- Tolerant to corrupt/missing JSON (config, voices, params): degrade with a banner/avisos, never block startup.
- No comments unless they carry real value; avoid adding emojis to files.
