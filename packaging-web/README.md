# packaging-web — instalador DMVoiceChangerWeb.exe

Toolkit para construir el **instalador de Windows de la app WEB** (La Forja de
Voces, `web/`) desde Linux. Decisión de producto (2026-11-17): la app de
escritorio PyQt (`voz_dnd/`) queda **descartada** como entregable — el
instalador oficial se construye **a partir de la web**, que es la versión
completa (17 voces, editor, forja, favoritos, cola de escenas, packs, atajos,
grabación) y la de mejor aspecto.

## Qué produce

`download/DMVoiceChangerWeb.exe` — instalador NSIS (v1.0.0, ~54 MB comprimido,
~257 MB instalado) con:

- **Node.js 22.14 portable** (`runtime\node.exe`) — no instala nada en el sistema.
- **La app web compilada en modo standalone** (Next.js 16, `server.js` +
  `.next` + dependencias trazadas), con los **engines de Prisma para Windows**.
- **Plantilla SQLite** (`app\plantilla.db`): en el primer arranque se copia a
  `%LOCALAPPDATA%\DMVoiceWeb\voces.db` (fuera de la instalación → sobrevive a
  actualizaciones y desinstalaciones).
- Lanzadores: `arrancar.vbs` (servidor oculto + abre el navegador),
  `detener.vbs`/`detener.ps1` (cierra SOLO nuestro node, por línea de comando),
  `DMVoiceWeb-Depuracion.bat` (consola visible con pausa).
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
├── arrancar.vbs / detener.vbs / detener.ps1
├── DMVoiceWeb-Depuracion.bat
├── uninstall.exe
├── runtime\node.exe          (Node 22.14 portable)
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

## Verificación pendiente del usuario (Windows real)

Smoke-testeado en Linux (servidor real, endpoints reales, DB real). Falta la
prueba en Windows: instalar, doble clic al atajo (abre el navegador), probar
micrófono y la pestaña Leer. Si algo falla: «Modo depuración» del menú inicio
→ consola visible con el error y pausa → pegar la salida.
