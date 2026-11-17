# packaging-web — instalador DMVoiceChangerWeb.exe

Toolkit para construir el **instalador de Windows de la app WEB** (La Forja de
Voces, `web/`) desde Linux. Decisión de producto (2026-11-17): la app de
escritorio PyQt (`voz_dnd/`) queda **descartada** como entregable — el
instalador oficial se construye **a partir de la web**, que es la versión
completa (17 voces, editor, forja, favoritos, cola de escenas, packs, atajos,
grabación) y la de mejor aspecto.

## Qué produce

`download/DMVoiceChangerWeb-1.0.2.exe` — instalador NSIS (v1.0.2, ~140 MB
comprimido, ~500 MB instalado) con:

- **Shell Electron 33** (`electron\DMVoiceChangerWeb.exe`): ventana de
  aplicación PROPIA — sin navegador, sin pestañas, sin barra de direcciones,
  con icono propio, pantalla de carga y cierre que apaga el servidor.
- **Node.js 22.14 portable** (`runtime\node.exe`) — no instala nada en el sistema.
- **La app web compilada en modo standalone** (Next.js 16, `server.js` +
  `.next` + dependencias trazadas), con los **engines de Prisma para Windows**.
- **Plantilla SQLite** (`app\plantilla.db`): en el primer arranque se copia a
  `%LOCALAPPDATA%\DMVoiceWeb\voces.db` (fuera de la instalación → sobrevive a
  actualizaciones y desinstalaciones).
- Lanzadores SIN scripts `.vbs` (Kaspersky/Defender los eliminaban al
  extraerlos — causa de las dos primeras versiones «roto»): el atajo apunta
  al exe de Electron; `detener.ps1` (cierra SOLO nuestros procesos) y
  `DMVoiceWeb-Depuracion.bat` (consola visible con pausa) siguen ahí.
  El instalador AUTOCOMPRUEBA al terminar (node.exe, electron, shell, server.js)
  y avisa en vivo si el antivirus borró algo.
- Instalación **por usuario** (`%LOCALAPPDATA%\Programs\DMVoiceChangerWeb`),
  sin UAC, con desinstalador registrado.

## Cómo funciona (sin Electron)

1. El atajo ejecuta `arrancar.vbs` con **wscript** (cero parpadeo de consola).
2. El VBS comprueba si `http://127.0.0.1:3987` ya responde (MSXML2.XMLHTTP).
   Si no, lanza `runtime\node.exe app\arranque.cjs` **oculto**.
3. `arranque.cjs` fija el entorno (`PORT=3987`, `HOSTNAME=127.0.0.1` — solo
   local, nunca expuesto a la red —, `DATABASE_URL` al .db del usuario) y
   arranca el server standalone de Next.
4. El VBS espera al puerto (máx ~30 s) y abre `http://127.0.0.1:3987/` en el
   navegador por defecto. `127.0.0.1` es contexto seguro → el micrófono
   (getUserMedia) funciona igual que en la web.

El servidor queda residente (oculto): el siguiente arranque es instantáneo.
Para cerrarlo: «Detener servidor» del menú inicio, o cerrar la sesión.

## Degradación honesta fuera del sandbox

La app instalada es la MISMA web, pero los servicios internos del entorno de
desarrollo no existen en el PC del usuario:

- **Forja por descripción**: si el LLM no responde, la nueva **forja
  heurística** (`src/lib/forja-heuristica.ts`) propone la voz con reglas de
  oficio (palabras clave → parámetros acotados al catálogo). El cliente avisa
  con un toast «Propuesta heurística (sin IA)».
- **TTS del servidor** (z-ai): no disponible → se usa el **TTS del navegador**
  (motor «navegador» de la pestaña Leer, que ya existía).
- **FakeYou** (catálogo de voces de personajes): API pública de internet →
  **funciona igual** en el PC del usuario (con conexión).
- **Transcripción de notas** (ASR): requiere el servicio → error honesto.
- Las 17 voces DSP, editor, favoritos, cola de escenas, packs, atajos,
  grabación WAV y worklet de audio son **100 % locales** (funcionan sin red).

Los datos viven en dos sitios (igual que la web): la DB de favoritos/historial
en `%LOCALAPPDATA%\DMVoiceWeb\voces.db` y las voces/ajustes del usuario en el
**localStorage del navegador** (por navegador: si cambia de Chrome a Edge,
empieza con las 17 base).

## Cómo construir (desde Linux)

```sh
cd packaging-web
NSISDIR="$HOME/nsis/NSIS" bash construir_instalador_web.sh
```

Requisitos: `bun`, `python3`, `curl`, `rsync`, `makensis` (conda-forge:
ver README de `voz_dnd/packaging-windows/`). El script:

1. Copia `web/` a `_build/app-src` y fija `turbopack.root` (ver lecciones).
2. `bun install` + `prisma generate` (schema con `binaryTargets
   ["native","windows"]` → engines para el exe y para el smoke test).
3. Crea la plantilla SQLite con `prisma db push`.
4. `bun run build` (Next standalone + static + public).
5. Descarga Node 22.14 win-x64 (para el exe) y linux-x64 (para el smoke test).
6. Ensambla el payload (`arranque.cjs`, VBS, PS1, bat de depuración, icono).
7. **Smoke test real en Linux**: arranca el standalone con el node de Linux,
   exige HTTP 200 en `/`, en el worklet y en `/api/creador/describir`, y
   verifica que la DB del usuario se crea en el LOCALAPPDATA simulado.
8. `makensis instalador-web.nsi` → `download/DMVoiceChangerWeb.exe`.

## Estructura instalada

```
%LOCALAPPDATA%\Programs\DMVoiceChangerWeb\
├── DMVoiceChanger.ico
├── LEEME.txt
├── detener.ps1 / DMVoiceWeb-Depuracion.bat
├── uninstall.exe
├── runtime\node.exe          (Node 22.14 portable, servidor)
├── electron\                 (shell de escritorio; DMVoiceChangerWeb.exe)
├── shell\                    (main.js + cargando/error, package.json)
└── app\                      (server.js + .next + node_modules + plantilla.db + arranque.cjs)
```

## Lecciones de este build (por si se repite)

- **Turbopack.root**: con el `bun.lock` del repo padre a la vista, Next 16
  infiere la raíz del workspace MAL y anida la salida standalone (el
  `server.js` desaparece de la raíz). El script fija `turbopack: { root:
  process.cwd() }` en la copia de build.
- **MUI_FINISHPAGE_RUN + RUN_FUNCTION**: definir SOLO `RUN_FUNCTION` deja la
  función sin referenciar (warning 6010 y no se ejecuta nada al terminar). Hay
  que definir AMBAS.
- **NSIS + PowerShell**: nunca incrustar PS con comillas anidadas en
  `ExecWait` — mejor instalar un `.ps1` y ejecutarlo con `-File`.
- **Prisma**: `binaryTargets = ["native", "windows"]` en el generator y
  verificar tras el build que `query_engine-windows.dll.node` está dentro del
  standalone (Next lo traza bien, pero se comprueba por si acaso).

## Cambios v1.0.2 (2026-11-17) — ELECTRON

- **Adiós al navegador**: shell Electron 33.4.11. Ventana propia (1280x820,
  fondo #1e150f sin flash blanco, icono del producto, sin barra de menús),
  una sola instancia (relanzar enfoca la ventana), enlaces externos se abren
  en el navegador del sistema, el resto de navegación queda dentro.
- **El antivirus ya no puede romper el arranque**: se ELIMINARON los `.vbs`
  (arrancar.vbs/detener.vbs) — Kaspersky los borraba al extraerlos y por eso
  v1.0.0 y v1.0.1 «no tenían arrancar.vbs» aunque el instalador los llevaba.
  Ahora el atajo → `electron\DMVoiceChangerWeb.exe` → spawn de
  `runtime\node.exe app\arranque.cjs` (servidor, DB, error.log) → ventana.
- **Ciclo de vida de app real**: cerrar la ventana apaga el servidor; si el
  servidor muere, la ventana muestra «La forja no encendió» con el camino de
  depuración (DMVoiceWeb-Depuracion.bat / %LOCALAPPDATA%\DMVoiceWeb\error.log).
- **Favicon local**: la web ya no depende del CDN para su icono
  (`web/src/app/favicon.ico` = icono del producto) — la ventana y la barra
  de tareas lucen el icono correcto incluso sin red.
- exe versionado (`DMVoiceChangerWeb-1.0.2.exe`) para que NUNCA se vuelva a
  instalar un instalador viejo por confusión de nombre.
- payload: `rsync -aL` (sin symlinks de bun), autocomprobación del instalador,
  verificación del contenido real por log de makensis (-V4, conteo exacto).

## Cambios v1.0.1 (2026-11-17)

- **v1.0.0 se entregó roto**: el exe publicado era de un build ANTERIOR a la
  corrección de los lanzadores (16:05 vs scripts de 16:08) — al abrir daba
  «No se encuentra el archivo de comandos …\arrancar.vbs». El build del exe
  debe ejecutarse SIEMPRE después de editar los scripts; ahora el propio
  script verifica el CONTENIDO real del instalador (log de makensis con -V4:
  conteo exacto de archivos empaquetados vs payload + claves obligatorias +
  subcarpetas de .next) y aborta si algo falta.
- **makensis -V4 obligatorio**: sin verbosidad 4 el log NO lista los
  `File: "…"` y la verificación no tiene nada que contar.
- **rsync -aL al armar el payload**: el standalone trae un symlink de bun
  (`.next/node_modules/@prisma/client-<hash>` → `node_modules/@prisma/client`);
  makensis lo sigue y empaqueta su árbol (60 archivos) como reales — el
  payload ahora se desreferencia para que el conteo cuadre y el árbol
  instalado sea 100 % archivos reales (Windows no tiene symlinks).

## Verificación pendiente del usuario (Windows real)

Smoke-testeado en Linux (servidor real, endpoints reales, DB real). Falta la
prueba en Windows: instalar, doble clic al atajo (abre el navegador), probar
micrófono y la pestaña Leer. Si algo falla: «Modo depuración» del menú inicio
→ consola visible con el error y pausa → pegar la salida.
