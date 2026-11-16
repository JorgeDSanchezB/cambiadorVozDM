# packaging-windows — instalador DMVoiceChanger.exe

Carpeta con todo lo necesario para construir el **instalador de Windows** de la
app de escritorio (`voz_dnd/`) desde Linux, sin Windows y sin permisos de
administrador en el equipo destino.

## Qué produce

`download/DMVoiceChanger.exe` — instalador NSIS (v1.1.1, ~101 MB) con:

- **Runtime Python 3.14 embebido** (no toca el Python del sistema, no hay
  venv).
- **site-packages preinstalados**: PyQt6, sounddevice, numpy, scipy, pydub,
  edge-tts, soundfile y **pip** (wheels `win_amd64` para CPython 3.14
  extraídos de sus wheels — mismos binarios que instalaría pip).
  pip va incluido porque el Python embebido no lo trae y sin él no funciona
  ni el botón «⬇️ Instalar vía ONNX (CPU)» de Ajustes ni la instalación
  manual documentada abajo.
- **El código completo de `voz_dnd/`** (`main.py`, `app/`, `data/`), que en
  v1.1.0 incluye: **gestor de motores IA en Ajustes** (estado real de
  onnxruntime/rmvpe-onnx/torch e instalación de la vía ONNX en un hilo de
  fondo), **packs de voces** (export/import ZIP para compartir el elenco) y
  la **fundación de clonación de voz** (dataset con consentimiento
  obligatorio).
- Instalación **por usuario** en `%LOCALAPPDATA%\Programs\DMVoiceChanger`
  (sin UAC), accesos directos en Menú de inicio + Escritorio y un
  `DMVoiceChanger-Depuracion.bat` para ver la consola de errores.
- **Desinstalador** real, registrado en «Aplicaciones instaladas» (HKCU).

## Arreglo de arranque (v1.1.1): «doble clic y nada pasa»

El `python314._pth` del runtime embebido activa el **modo aislado** de
Python: la carpeta del script NO se añade a `sys.path`. Con el atajo
original (`pythonw.exe main.py`) el `import app` de `main.py` moría con
`ModuleNotFoundError` y pythonw no muestra consola → el usuario solo ve
«nada pasa». Tres capas de protección:

1. El `._pth` incluye `..\app` (relativa al propio `._pth` → `INSTDIR\app`).
2. Los atajos y la página final ejecutan `runtime\lanzar_app.py`: un
   lanzador que hace chdir a `app\`, fuerza `sys.path`, ejecuta
   `main.py` vía `runpy` y registra CUALQUIER fallo (traceback y crashes
   duros vía faulthandler) en `app\logs\arranque.log`.
3. `DMVoiceChanger-Depuracion.bat` lanza el mismo lanzador con consola
   (`python.exe`) y muestra el código de salida.

Verificado en Linux con una réplica de la estructura instalada: import OK,
salida limpia registrada y traceback completo en `arranque.log` cuando el
fallo es de import.

## Notas honestas

- El **modo IA (RVC) NO va incluido**: por diseño la app degrada a DSP sin
  él (nunca corta el audio). Quien lo quiera puede instalarlo DESDE la app
  (Ajustes → «⬇️ Instalar vía ONNX (CPU)», instala `rmvpe-onnx` +
  `onnxruntime` con el pip incluido) o a mano en `<instalación>\runtime`
  con: `python.exe -m pip install rmvpe-onnx onnxruntime` (ambas vías
  necesitan internet; descarga los modelos la primera vez). Mantener así
  evita ~200 MB de modelos en el instalador.
- La pestaña «Leer» del escritorio usa `edge-tts` → **necesita internet**
  en tiempo de ejecución (igual que en desarrollo).
- El audio de lectura guarda WAV en `app\lectura` dentro de la carpeta de
  instalación (instalación por usuario = escritura permitida).

## Cómo construir (desde Linux)

1. makensis para Linux. Sin privilegios de root, la vía más simple es el
   paquete de conda-forge (binario Linux con stubs/Plugins incluidos):

   ```sh
   curl -L -o nsis.tar.bz2 \
     "https://conda.anaconda.org/conda-forge/linux-64/nsis-3.08-he0ac6c6_0.tar.bz2"
   mkdir -p ~/nsis && tar xjf nsis.tar.bz2 -C ~/nsis
   # ~/nsis/NSIS es el árbol NSIS completo (Stubs, Plugins, Include, MUI2)
   ```

2. Construir todo de una vez:

   ```sh
   cd voz_dnd/packaging-windows
   export NSISDIR="$HOME/nsis/NSIS"
   PATH="$HOME/nsis/bin:$PATH" ./construir_instalador.sh
   ```

   El script hace: descarga del Python embeddable → `pip download` de wheels
   win_amd64 (cp314) → extracción a `Lib/site-packages` → copia del código →
   `makensis instalador.nsi` → deja el .exe en `download/DMVoiceChanger.exe`.

## Estructura instalada

```
%LOCALAPPDATA%\Programs\DMVoiceChanger\
├── DMVoiceChanger.ico
├── DMVoiceChanger-Depuracion.bat      (consola visible para depurar)
├── uninstall.exe
├── runtime\                            (Python 3.14 embebido + site-packages)
└── app\                                (voz_dnd: main.py, app/, data/)
```

El lanzamiento es `runtime\pythonw.exe main.py` con directorio de trabajo
`app\` — las rutas canónicas de `app/rutas.py` siguen resolviendo igual que
en desarrollo (`BASE_DIR = app\`, `data` junto al código, `logs` y `lectura`
se crean al vuelo).

## Verificación pendiente del usuario (Windows real)

Compilado y validado estructuralmente en Linux (PE32 + NSIS válidos, CRC
correcto, lista de archivos del instalador revisada). Falta la prueba final
en una máquina Windows: instalar, iniciar, probar micrófono y la pestaña
«Leer». Si algo falla, abrir `DMVoiceChanger-Depuracion.bat` y reportar la
consola.
