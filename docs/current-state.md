# Estado actual — `voz_dnd`

> Snapshot del proyecto para que un agente entre sin releerlo todo. Actualiza
> este archivo cuando cambie el estado real.

## Ejecutar y verificar (Windows, venv de Python 3.14)

- Python del proyecto: `voz_dnd\.venv\Scripts\python.exe` (usar siempre este).
- Arranque: `voz_dnd\iniciar_voz_dnd.bat` (o `python main.py` dentro de
  `voz_dnd\`).
- **Suite de tests del motor (headless)**: `cd voz_dnd && python -m unittest
  discover -s tests -v` — unittest de la librería estándar, sin
  dependencias nuevas; no requiere micrófono ni GUI. Cubre dominio
  (modelos, catálogo), motor (voces, grabación, lectura TTS con stub,
  config, callback RT) y tripwires anti-duplicación de constantes.
- **No hay CI / linter.** "Verificación" = suite anterior + `python -m
  py_compile <archivos>` + smoke manual de la GUI en el PC Windows.

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

## Correcciones de la auditoría V6 (rama `chore/quality-improvements`)

Bugs reproducidos con test y corregidos (ver `docs/decisions/` 004-006):

- **Grabación perdida por ruta de ffmpeg inválida**: `_hay_ffmpeg()` asignaba
  la ruta configurada a pydub sin validar; con ffmpeg en el PATH la exportación
  MP3 moría y los bloques ya limpiados se perdían. Ahora: cascada
  MP3 → WAV → WAV-temporal y los bloques solo se descartan tras un éxito.
- **Lectura de textos largos superpuestos**: `sintetizar()` SUMABA los
  fragmentos desde la muestra 0; ahora se concatenan.
- **Renombrar una voz revertía solo**: el JSON viejo sobrevivía con el mismo
  id y el orden alfabético decidía al recargar. Ahora `guardar()` limpia
  residuos del mismo id, las colisiones de slug desambiguan (`-2`, `-3`) y
  los ids duplicados en disco se resuelven por archivo canónico con aviso.
- **Cambio de ajustes de audio con grabación en curso —o audio pendiente de
  exportar— descartaría el audio**: `aplicar_config_audio()` lo rechaza con
  error claro en ambos casos; el cambio de carpeta/calidad/ffmpeg SÍ llega
  al grabador vivo (`actualizar_config`) para rescatar sesiones pendientes.
- Constantes duplicadas (sample rates, overhead de driver) unificadas en su
  fuente única con tripwire de test; tema inválido en config.json ahora avisa.
- **Reintento de exportación**: si toda la cascada falla, el audio queda en
  memoria y la ventana de grabación ofrece «Reintentar exportación».

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

## Versión web (rama `feat/web-app`)

- **`web/`** contiene la versión React/Next.js 16 (solo en esa rama): mismo
  catálogo (generado con `web/scripts/sincronizar_voces.py`), mismo mapa de
  atajos F1–F12/Shift, editor con sliders desde `parametros.json`, lectura
  TTS por `/api/tts` (z-ai-web-dev-sdk) con respaldo `speechSynthesis`,
  grabación post-DSP (MediaRecorder) y persistencia en `localStorage`.
- **El DSP es un espejo 1:1** de `efectos.py` en
  `web/public/worklets/cambiador-voz.js` (AudioWorklet): misma cadena,
  constantes y fórmulas. La regla de espejo está en `AGENTS.md` (raíz) y el
  detalle en `docs/decisions/008-version-web-react.md` y `web/README.md`.
- Verificación web: `cd web && bun run lint` (+ `bun run dev` y prueba en
  navegador). El entorno de despliegue sirve exactamente este árbol en `/`.
- Diferencias honestas documentadas: grabación WebM/Opus en vez de MP3, RVC
  no disponible (IA Demo degrada a `dsp_post`), voces TTS del servidor en
  vez de edge-tts.
