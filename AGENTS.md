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
- Paths are resolved relative to the package via `app/rutas.py` (single source of truth): voice/config data lives in `voz_dnd\data\` (`voces/*.json`, `config.json`, `parametros.json`), logs in `voz_dnd\logs\app.log`. Reading-text-feature WAVs go to `data\lectura\` (not versioned).
- **TTS dependency (`edge-tts`)**: the "📖 Leer" tab (Fase 6) reads a text file with the selected voice. It needs `edge-tts` (online neural TTS, Microsoft) + `soundfile`; both are in `requirements.txt`. It **requires internet at runtime**. If `edge-tts` is missing it raises a clear error; far from network use the feature just errors, it doesn't crash the app.

## voz_dnd: architecture & hard-won gotchas

Layers: `app/domain/` (pure, no I/O/Qt), `app/engine/` (audio + orchestration), `app/gui/` (PyQt6).

- **Real-time audio contract (`motor_audio.py`)**: the `sd.Stream` callback must stay lock-free and never raise. Effects expect `(frames, 1)` float32 arrays; passing 1-D breaks them. Normalize with `reshape(-1, 1)` before/after.
- **Device ids are stale-prone**: `config.json` stores `dispositivo_entrada`/`dispositivo_salida`; an out-of-date id (e.g. a device that no longer exists) makes PortAudio fail to open the stream (`Illegal combination of I/O devices [-9993]`, or `Error querying device -1` for `None`/invalid). `_par_dispositivos()` must resolve `None`/invalid ids to system defaults and validate channel counts. Keep these values `null` (system default) unless the user explicitly picks a device.
- **Startup has a built-in audio fallback**: `MotorAudio.iniciar()` tries the configured devices first; if that raises, it retries with the system defaults and sets `usando_dispositivos_default`. It only raises if even the defaults fail (truly no audio device). `main_window.py` shows an info banner (not an error) in the fallback case — keep this seam working when touching startup.
- **IA mode is multi-engine and must degrade gracefully** (`modulo_ia.py` + `rvc_adapter.py`): PyTorch RVC → ONNX RVC → plain DSP. The path where no engine/model is ready must still process audio (bypass/DSP) and **never drop/crash the stream**. If the user's machine has no IA model or engine, `esta_listo()==False` is the expected, correct state.
- Each installation can inject its own `adapter=` into `ModuloIA` (priority over built-in engines) — keep that seam working.
- **Offline replay seam (`motor_audio.py` + `lector_texto.py`)**: the "📖 Leer" tab renders text→speech fully offline, then plays it through the SAME single full-duplex stream. `MotorAudio.reproducir(datos)` swaps a `(N,1)` float32 buffer into the callback (served instead of the mic until exhausted, returning to mic+DSP after). This keeps "one stream / no device contention"; don't add a second `sd.Stream` for playback. `lector_texto.py` is pure-engine (no Qt) and runs on a worker thread — never call it from the audio or GUI thread.

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
