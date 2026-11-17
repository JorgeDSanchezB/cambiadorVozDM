# AGENTS.md

## Project landscape (read this before editing)

This repo is a **deployment-sandbox template + the real app**, not a single coherent tree:

- **Root (Next.js scaffold)** — Next 16 / shadcn / Prisma(SQLite) + `.zscripts/` deploy pipeline (standalone Next + Caddy + Python runtime bundling, targets `/home/z/my-project`). Mostly unused template infra; `src/app/page.tsx` is a placeholder and `prisma/schema.prisma` is the default User/Post. Don't assume you need to touch this for app work.
- **`voz_dnd/` — the real, actively-developed project**: real-time D&D voice changer (Python, PyQt6, sounddevice, numpy/scipy). All recent/future work lives here.
- **`cambiador-voz-dnd/`** — an OLDER sibling of `voz_dnd` with a different package layout (`dominio/`, `aplicacion/`, `infraestructura/`). Both are tracked in git. **Edit `voz_dnd/`, not `cambiador-voz-dnd/`** unless the task explicitly says otherwise.
- **`web/` (solo rama `feat/web-app`)** — versión web de la app (Next.js 16 + React + Web Audio/AudioWorklet), espejo funcional de `voz_dnd` que vive únicamente en esa rama. Ver "Sincronización entre ramas" más abajo.

## voz_dnd: running & verifying

- Python venv already exists: `voz_dnd\.venv`. Run everything through it:
  `voz_dnd\.venv\Scripts\python.exe` (on Windows). Do not use a system `python`.
- Entry point: `voz_dnd\main.py` (PyQt6 GUI). Launch via `voz_dnd\iniciar_voz_dnd.bat` on Windows.
- **There is no test suite / CI / linter config** for this app. "Verification" = `python -m py_compile <files>` plus hand-written headless smoke tests (import the engine, feed synthetic `(frames,1)` float32 arrays, assert it doesn't raise).
- Paths are resolved relative to the package via `app/rutas.py` (single source of truth): voice/config data lives in `voz_dnd\data\` (`voces/*.json`, `config.json`, `parametros.json`), logs in `voz_dnd\logs\app.log`. Reading-text-feature WAVs go to `data\lectura\` (not versioned).
- **TTS dependency (`edge-tts`)**: the "📖 Leer" tab (Fase 6) reads a text file with the selected voice. It needs `edge-tts` (online neural TTS, Microsoft) + `soundfile`; both are in `requirements.txt`. It **requires internet at runtime**. If `edge-tts` is missing it raises a clear error; far from network use the feature just errors, it doesn't crash the app. The WAV output folder is user-selectable in the tab and defaults to `data/lectura/` (gitignored); never report "lee/reproduce" without checking `MotorAudio.audio_activo` (a dead stream from a bad device would otherwise show a false success).

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

## Sincronización entre ramas: escritorio ↔ web (OBLIGATORIA)

El proyecto vive en DOS ramas espejo que deben mantener paridad funcional:

- **`main`** → aplicación de escritorio (`voz_dnd/`, Python + PyQt6).
- **`feat/web-app`** → versión web (`web/`, Next.js 16 + React + Web Audio),
  que además contiene TODO lo de `main` (`voz_dnd/`, `docs/`, README) en las
  mismas rutas.

**Regla del espejo**: todo cambio funcional (nueva voz, nuevo parámetro DSP,
corrección de un efecto, límites de config, decisiones y docs) debe
reflejarse **igual en ambas ramas**. En concreto:

1. Los archivos compartidos existen con la MISMA ruta en las dos ramas →
   aplica el mismo commit (cherry-pick) o rehazlo de forma equivalente;
   nunca dejes un cambio funcional en una sola rama.
2. La cadena DSP tiene DOS implementaciones matemáticamente equivalentes:
   - Escritorio: `voz_dnd/app/domain/efectos.py`
   - Web: `web/public/worklets/cambiador-voz.js` (AudioWorklet)
   Un cambio en una exige el espejo inmediato en la otra (mismo orden de
   cadena, mismas constantes de diseño y mismas fórmulas).
3. El catálogo de voces de la web se GENERA, no se copia a mano:
   `python3 web/scripts/sincronizar_voces.py` lee
   `voz_dnd/data/voces/*.json` y produce `web/src/data/voces.json` (y
   `web/src/data/parametros.json` desde `voz_dnd/data/parametros.json`).
   Tras cambiar una voz en cualquiera de las dos ramas: cherry-pick a la
   otra y re-ejecutar el script en la rama web.
4. Verificación antes de dar por cerrado un cambio:
   - Escritorio: `cd voz_dnd && python -m unittest discover -s tests`
   - Web: `cd web && bun install && bun run lint` (+ `bun run dev` y prueba
     en navegador; el entorno de despliegue real es el sandbox que sirve
     esta misma app).
5. Si un cambio solo aplica a una plataforma (p. ej., GUI), dilo en el
   mensaje del commit para que el árbitro sepa que no requiere espejo.

## Style conventions

- Codebase is Spanish-language (identifiers, comments, docs, log messages, JSON values). Follow suit.
- Data-driven: slider ranges come from `data/parametros.json`; one voice = one JSON file in `data/voces/` with a guaranteed `neutral` voice. Add/extend voices via JSON, not code.
- Tolerant to corrupt/missing JSON (config, voices, params): degrade with a banner/avisos, never block startup.
- No comments unless they carry real value; avoid adding emojis to files.

## Gestor de motores IA (Ajustes escritorio) — estilo Model Manager

Idea de VoiceStudio (implementación propia): el grupo «🧠 Modo avanzado
(IA)» de la pestaña Ajustes muestra el ESTADO REAL de cada pieza del modo
IA vía `estado_motores()` (modulo_ia.py): PyTorch, onnxruntime,
rmvpe-onnx, tts-with-rvc — y la conclusión honesta: si no hay vía RVC
completa, el modo IA DEGRADA A DSP y el audio nunca se corta.

- Botón «⬇️ Instalar vía ONNX (CPU)» instala `rmvpe-onnx + onnxruntime`
  con el MISMO Python de la app (sys.executable) en un HILO DE FONDO
  (threading.Thread daemon, igual que el resto de la GUI) y avisa por
  señal Qt (`senal_ia_instalado`, queued desde hilo no-GUI). NUNCA
  bloquear la GUI con subprocess.run en el hilo principal.
- Tras instalar con éxito: `importlib.invalidate_caches()` + relectura de
  estado (sin reiniciar la app). Si pip falla, se muestra la cola de su
  salida y la app sigue en DSP.
- Solo visible si NO hay vía RVC completa. Instalar paquetes no toca la
  cadena DSP ni la config; no volver a hacerlo bloqueante ni con QThread
  propio (mantener el patrón threading.Thread del proyecto).

## Clonación de voz (escritorio) — fundación experimental del dataset

Idea del voice cloning de VoiceStudio, FUNDACIÓN HONESTA (petición
explícita del usuario): el ENTRENAMIENTO RVC NO existe todavía (GPU +
cadena aparte). Lo que ya vive en la app:

- `app/engine/dataset.py` (solo stdlib): datasets en
  `data/clonacion/<sujeto>/` (NO versionada, como lectura/). Cada sujeto
  tiene `accesos.json` con CONSENTIMIENTO OBLIGATORIO registrado con
  fecha (sin él, ErrorDataset), muestras WAV copiadas al dataset
  (rechazo UNO A UNO de no-WAV/corruptos/< 2 s) y umbral objetivo de
  180 s de voz limpia (suelo honesto de RVC, no el ideal de 10 min).
- GUI: grupo «🧬 Clonación de voz (preparación experimental)» en Ajustes
  (sujeto + consentimiento + añadir WAVs en hilo de fondo + resumen del
  dataset). El texto SIEMPRE dice que prepara datos, no que clone.
- Tests: `tests/test_dataset.py` (headless, 9 casos). El futuro
  entrenamiento debe CONSUMIR estos datasets, no inventar otro formato.

## Packs de voces (escritorio) — compartir el elenco

Idea de los Model Packs de VoiceStudio (petición explícita del usuario):
grupo «🎒 Packs de voces» en Ajustes. `app/engine/packs.py` (solo stdlib):

- **Exportar**: ZIP con `pack.json` de manifiesto + `voces/*.json`
  (excluye SIEMPRE la Neutral: es la voz de seguridad integrada).
- **Importar conservador**: ids REGENERADOS (uuid4, jamás pisa las voces
  del que importa), omitir la Neutral, omitir nombres duplicados con
  aviso, ZIP roto o sin manifiesto → ErrorPack honesto. Tras importar,
  `senal_pack_importado` → main_window `_recargar_voces` (mismo camino
  que la recarga manual).
- **Formatos NO compatibles**: el pack del escritorio es ZIP; el de la
  web es JSON (tarjeta «Pack de voces» en Ajustes web, con la misma
  política conservadora). La UI lo dice en ambas plataformas. No unificar
  formatos sin petición explícita del usuario.
- Tests: `tests/test_packs.py` (6 casos headless con gestores reales).

## DECISIÓN DE PRODUCTO (2026-11-17): el escritorio ES la web

El usuario descartó la app PyQt (`voz_dnd/`) como entregable tras verla
junto a la web («la disparidad es ridícula»): nunca alcanzó la paridad y
la web es la versión completa y la mejor. A partir de ahora:

- **El instalador oficial de Windows se construye desde `web/`**:
  `packaging-web/` → `download/DMVoiceChangerWeb.exe` (Node portable +
  Next standalone + plantilla Prisma + lanzadores VBS; se abre en el
  navegador en 127.0.0.1:3987). Ver su README para el diseño completo.
- `voz_dnd/` queda como LEGADO: ya no recibe funciones nuevas. Su
  instalador (`voz_dnd/packaging-windows/`) se mantiene solo por si se
  pide expresamente.
- **Forja heurística** (`web/src/lib/forja-heuristica.ts`): red de
  seguridad de la forja por descripción cuando el LLM no responde (caída
  o app instalada fuera del sandbox). Palabras clave → parámetros
  SIEMPRE acotados al catálogo; el cliente avisa con un toast
  «Propuesta heurística (sin IA)». No borrarla: es la que hace que la
  forja funcione en el .exe instalado.
- Exe JAMÁS a git (`.gitignore`: `/download/*.exe` de ambos instaladores).
