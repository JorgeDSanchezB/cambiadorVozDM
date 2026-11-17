#!/usr/bin/env bash
# ============================================================
#  DMVoiceChanger Web — construir el instalador de Windows
#  (Linux) a partir de la app web (web/, Next.js standalone).
#
#  Estrategia: NO hay Electron. El instalador lleva:
#    - node.exe (Windows) portable
#    - la app Next.js compilada en modo standalone (server.js)
#    - la plantilla de la base SQLite (Prisma, engines linux+windows)
#    - lanzadores VBS (arranque silencioso + navegador, parada)
#  Al instalar: %LOCALAPPDATA%\Programs\DMVoiceChangerWeb; el
#  servidor escucha SOLO en 127.0.0.1:3987 y la app se abre en
#  el navegador por defecto. Sin admin, sin Python, sin claves.
#
#  Uso:  ./construir_instalador_web.sh
#  Requisitos: bun, python3, curl, makensis (NSISDIR=/home/z/nsis/NSIS)
# ============================================================
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ_REPO="$(cd "${AQUI}/.." && pwd)"
FUENTE="${RAIZ_REPO}/web"
TRABAJO="${AQUI}/_build"
APP_SRC="${TRABAJO}/app-src"
PAYLOAD="${TRABAJO}/payload"
NODE_VER="22.14.0"
ELECTRON_VER="33.4.11"
PUERTO="3987"
NSISDIR="${NSISDIR:-/home/z/nsis/NSIS}"
ICO="${RAIZ_REPO}/voz_dnd/packaging-windows/DMVoiceChanger.ico"

mkdir -p "${TRABAJO}"
rm -rf "${PAYLOAD}" "${APP_SRC}" "${TRABAJO}/plantilla" "${TRABAJO}/smoke-home"
mkdir -p "${PAYLOAD}/runtime" "${PAYLOAD}/app" "${TRABAJO}/plantilla" "${TRABAJO}/smoke-home"

echo "[1/8] Copiando la app web (web/) a la zona de build..."
rsync -a --exclude 'node_modules' --exclude '.next' --exclude 'server.log' \
  "${FUENTE}/" "${APP_SRC}/"
# Next 16/Turbopack infiere la raíz del workspace por los lockfiles y, con el
# bun.lock del repo padre, anida la salida standalone (server.js desaparece
# de la raíz). Se fija la raíz explícita: la propia carpeta de la app.
python3 - "${APP_SRC}/next.config.ts" <<'PY'
import sys
from pathlib import Path
ruta = Path(sys.argv[1])
assert ruta.exists(), f"no se encontró {ruta}"
src = ruta.read_text(encoding="utf-8")
if "turbopack" not in src:
    src = src.replace(
        "const nextConfig: NextConfig = {",
        "const nextConfig: NextConfig = {\n"
        "  // Raíz explícita (build offline del instalador): evita que\n"
        "  // Turbopack infiera el repo padre por los lockfiles.\n"
        "  turbopack: { root: process.cwd() },",
        1,
    )
    ruta.write_text(src, encoding="utf-8")
    print("next.config.ts → turbopack.root fijado")
PY

echo "[2/8] Instalando dependencias y generando el cliente Prisma (linux+windows)..."
cd "${APP_SRC}"
bun install
bun prisma generate

echo "[3/8] Creando la plantilla de la base de datos (SQLite)..."
DATABASE_URL="file:${TRABAJO}/plantilla/plantilla.db" \
  bun prisma db push --accept-data-loss
test -s "${TRABAJO}/plantilla/plantilla.db" || { echo "FALTA plantilla.db"; exit 1; }

echo "[4/8] Compilando Next.js (standalone)..."
bun run build
test -f "${APP_SRC}/.next/standalone/server.js" || { echo "FALTA server.js (build)"; exit 1; }
test -d "${APP_SRC}/.next/standalone/.next/static" || { echo "FALTA .next/static"; exit 1; }
test -d "${APP_SRC}/.next/standalone/public" || { echo "FALTA public/"; exit 1; }
# Engines de Prisma: la app debe llevar el de Windows (y el nativo para el smoke test)
find "${APP_SRC}/.next/standalone" -name 'query_engine-windows.dll.node' | grep -q . \
  || { echo "FALTA el engine de Prisma para Windows"; exit 1; }
find "${APP_SRC}/.next/standalone" -name 'libquery_engine-*' | grep -q . \
  || { echo "FALTA el engine nativo de Prisma"; exit 1; }
echo "    Engines Prisma presentes (windows + nativo)."

echo "[5/8] Descargando Node.js ${NODE_VER} y Electron ${ELECTRON_VER} (win-x64)..."
cd "${TRABAJO}"
if [ ! -f node-win.zip ]; then
  curl -fsSL -o node-win.zip \
    "https://nodejs.org/dist/v${NODE_VER}/node-v${NODE_VER}-win-x64.zip"
fi
if [ ! -d node-win ]; then
  python3 -m zipfile -e node-win.zip node-win/
fi
cp "node-win/node-v${NODE_VER}-win-x64/node.exe" "${PAYLOAD}/runtime/node.exe"
if [ ! -f node-linux.tar.xz ]; then
  curl -fsSL -o node-linux.tar.xz \
    "https://nodejs.org/dist/v${NODE_VER}/node-v${NODE_VER}-linux-x64.tar.xz"
fi
if [ ! -d node-linux ]; then
  mkdir -p node-linux && tar -xJf node-linux.tar.xz -C node-linux --strip-components=1
fi
test -x node-linux/bin/node
if [ ! -f electron-win.zip ]; then
  curl -fsSL -o electron-win.zip \
    "https://github.com/electron/electron/releases/download/v${ELECTRON_VER}/electron-v${ELECTRON_VER}-win32-x64.zip"
fi
if [ ! -d electron-win ]; then
  python3 -m zipfile -e electron-win.zip electron-win/
fi
test -f "electron-win/electron.exe" \
  || { echo "FALTA electron.exe en el zip de Electron"; exit 1; }

echo "[6/8] Ensamblando el payload del instalador..."
# -L (desreferenciar): el standalone trae symlinks de bun (p. ej.
# .next/node_modules/@prisma/client-<hash> -> node_modules/@prisma/client);
# makensis los sigue y empaqueta su arbol como archivos reales, asi que el
# payload debe ser 100% archivos reales para que el conteo de verificacion
# cuadre y porque Windows no tiene symlinks.
rsync -aL "${APP_SRC}/.next/standalone/" "${PAYLOAD}/app/"
cp "${TRABAJO}/plantilla/plantilla.db" "${PAYLOAD}/app/plantilla.db"
cp "${ICO}" "${PAYLOAD}/DMVoiceChanger.ico"
# Shell Electron: dist completo renombrado como ejecutable del producto
rsync -a --delete "electron-win/" "${PAYLOAD}/electron/"
mv "${PAYLOAD}/electron/electron.exe" "${PAYLOAD}/electron/DMVoiceChangerWeb.exe"

# ---- arranque.cjs: fija entorno (puerto, DB por usuario) y lanza server.js.
# Lo lanza la shell Electron; SIN scripts .vbs (Kaspersky/Defender los
# eliminan al extraerlos). Registra errores en error.log para diagnostico. ----
cat > "${PAYLOAD}/app/arranque.cjs" <<CJS
// DMVoiceChanger Web - arranque del servidor local (lo lanza la shell Electron).
// La base de datos vive FUERA de la instalacion (sobrevive a updates):
// %LOCALAPPDATA%\DMVoiceWeb\voces.db (se copia de la plantilla al primer uso).
const fs = require('fs');
const os = require('os');
const path = require('path');

const AQUI = __dirname;
const base = process.env.LOCALAPPDATA || process.env.USERPROFILE || os.homedir();
const datos = path.join(base, 'DMVoiceWeb');
fs.mkdirSync(datos, { recursive: true });

function registrarError(e) {
  try {
    fs.appendFileSync(path.join(datos, 'error.log'),
      new Date().toISOString() + '  ' + ((e && e.stack) ? e.stack : String(e)) + '\n');
  } catch (_) {}
}
process.on('uncaughtException', registrarError);

const db = path.join(datos, 'voces.db');
if (!fs.existsSync(db) && fs.existsSync(path.join(AQUI, 'plantilla.db'))) {
  fs.copyFileSync(path.join(AQUI, 'plantilla.db'), db);
}

process.env.NODE_ENV = 'production';
process.env.PORT = process.env.DMVOICEWEB_PORT || '${PUERTO}';
process.env.HOSTNAME = '127.0.0.1';   // SOLO local: nunca expuesto a la red
process.env.DATABASE_URL = 'file:' + db.replace(/\\\\/g, '/');

process.chdir(AQUI);
try {
  require('./server.js');
} catch (e) {
  registrarError(e);
  process.exitCode = 1;
  throw e;
}
CJS

# ---- detener: cierra SOLO los procesos de DMVoiceChangerWeb (node + shell) ----
cat > "${PAYLOAD}/detener.ps1" <<'PS1'
# Detiene el servidor local de DMVoiceChanger Web (y solo el suyo)
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like '*DMVoiceChangerWeb*arranque.cjs*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-Process -Name 'DMVoiceChangerWeb' -ErrorAction SilentlyContinue |
  Stop-Process -Force
Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show('Servidor de DMVoiceChanger Web detenido.', 'DMVoiceChanger Web', 'OK', 'Information') | Out-Null
PS1

# ---- shell Electron + LEEME ----
mkdir -p "${PAYLOAD}/shell"
cp "${AQUI}/electron/main.js" "${AQUI}/electron/package.json" "${PAYLOAD}/shell/"
cp "${AQUI}/electron/cargando.html" "${AQUI}/electron/error.html" "${PAYLOAD}/shell/"
cat > "${PAYLOAD}/LEEME.txt" <<'LEEME'
DMVoiceChanger Web — La Forja de Voces
======================================

Este programa es la app web completa convertida en aplicacion de escritorio:
la ventana que abre es SUYA (Electron), sin navegador, sin pestañas, sin
barra de direcciones.

Que hay aqui:
  - electron\DMVoiceChangerWeb.exe   La shell de escritorio (la que abre el atajo)
  - runtime\node.exe                 Node.js portable (no instala nada en el sistema)
  - app\                             La aplicacion compilada (servidor local)
  - DMVoiceWeb-Depuracion.bat        Consola visible del servidor (para ver errores)
  - detener.ps1                      Cierra el servidor si quedara colgado

El servidor escucha SOLO en http://127.0.0.1:3987 — nunca queda expuesto a
la red. Al cerrar la ventana, el servidor se apaga.

Si la ventana muestra "La forja no encendio":
  1) Ejecuta DMVoiceWeb-Depuracion.bat y lee el error (pegalo si pides ayuda).
  2) Mira si hay detalle en %LOCALAPPDATA%\DMVoiceWeb\error.log
  3) Si tu antivirus elimina archivos de esta carpeta, revisa su cuarentena
     y anade una exclusion para ella.

Tus voces y favoritos viven en %LOCALAPPDATA%\DMVoiceWeb\voces.db
(sobreviven a desinstalar/actualizar) y en el almacenamiento de la propia
aplicacion.
LEEME

# ---- depuracion: consola visible con pausa (para pegar errores) ----
cat > "${PAYLOAD}/DMVoiceWeb-Depuracion.bat" <<'BAT'
@echo off
REM DMVoiceChanger Web - modo depuracion: consola visible
title DMVoiceChanger Web - Depuracion
cd /d "%~dp0app"
echo Arrancando el servidor en http://127.0.0.1:3987 ...
echo (Cierra esta ventana o pulsa Ctrl+C para detenerlo)
echo.
"%~dp0runtime\node.exe" "%~dp0app\arranque.cjs"
echo.
echo Servidor detenido. Codigo de salida: %ERRORLEVEL%
pause
BAT

echo "    Verificando archivos clave del payload..."
test -f "${PAYLOAD}/runtime/node.exe"       || { echo "FALTA runtime\\node.exe"; exit 1; }
test -f "${PAYLOAD}/app/server.js"          || { echo "FALTA app\\server.js"; exit 1; }
test -f "${PAYLOAD}/app/arranque.cjs"       || { echo "FALTA app\\arranque.cjs"; exit 1; }
test -f "${PAYLOAD}/app/plantilla.db"       || { echo "FALTA app\\plantilla.db"; exit 1; }
test -f "${PAYLOAD}/electron/DMVoiceChangerWeb.exe"   || { echo "FALTA electron\\DMVoiceChangerWeb.exe"; exit 1; }
test -f "${PAYLOAD}/electron/resources/default_app.asar" || { echo "FALTA electron resources"; exit 1; }
test -f "${PAYLOAD}/shell/main.js"                    || { echo "FALTA shell\\main.js"; exit 1; }
test -f "${PAYLOAD}/shell/package.json"               || { echo "FALTA shell\\package.json"; exit 1; }
test -f "${PAYLOAD}/shell/cargando.html"              || { echo "FALTA shell\\cargando.html"; exit 1; }
test -f "${PAYLOAD}/shell/error.html"                 || { echo "FALTA shell\\error.html"; exit 1; }
test -f "${PAYLOAD}/LEEME.txt"                        || { echo "FALTA LEEME.txt"; exit 1; }
test -f "${PAYLOAD}/detener.ps1"            || { echo "FALTA detener.ps1"; exit 1; }
test -f "${PAYLOAD}/DMVoiceWeb-Depuracion.bat" || { echo "FALTA DMVoiceWeb-Depuracion.bat"; exit 1; }
head -c 2 "${PAYLOAD}/runtime/node.exe" | grep -q "MZ" || { echo "node.exe no es un PE valido"; exit 1; }
head -c 2 "${PAYLOAD}/electron/DMVoiceChangerWeb.exe" | grep -q "MZ" || { echo "DMVoiceChangerWeb.exe (electron) no es un PE valido"; exit 1; }
echo "    Payload OK."

echo "[7/8] Smoke test: arrancar el servidor standalone en Linux..."
cd "${TRABAJO}"
LOCALAPPDATA="${TRABAJO}/smoke-home" node-linux/bin/node "${PAYLOAD}/app/arranque.cjs" \
  > smoke.log 2>&1 &
SMOKE_PID=$!
trap 'kill ${SMOKE_PID} 2>/dev/null || true' EXIT
ok=""
for i in $(seq 1 60); do
  codigo="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${PUERTO}/ || true)"
  if [ "${codigo}" = "200" ]; then ok="si"; break; fi
  sleep 1
done
if [ "${ok}" != "si" ]; then
  echo "El servidor NO arrancó; últimos logs:"; tail -20 smoke.log; exit 1
fi
html="$(curl -s http://127.0.0.1:${PUERTO}/)"
echo "${html}" | grep -qi "forja\|voces" || { echo "La portada no contiene el contenido esperado"; tail -5 smoke.log; exit 1; }
curl -s -o /dev/null -w "    GET /                    → %{http_code}\n" http://127.0.0.1:${PUERTO}/
curl -s -o /dev/null -w "    GET /worklets/…js        → %{http_code}\n" http://127.0.0.1:${PUERTO}/worklets/cambiador-voz.js
curl -s -o /dev/null -w "    POST /api/creador/…      → %{http_code}\n" \
  -X POST http://127.0.0.1:${PUERTO}/api/creador/describir \
  -H 'Content-Type: application/json' -d '{"descripcion":"hechicero oscuro con eco de cripta"}'
test -f "${TRABAJO}/smoke-home/DMVoiceWeb/voces.db" \
  || { echo "La DB de usuario no se creó"; exit 1; }
echo "    DB de usuario creada en LOCALAPPDATA simulado."
kill ${SMOKE_PID} 2>/dev/null || true
trap - EXIT

echo "[8/8] Compilando el instalador NSIS (y verificando su CONTENIDO real)..."
cp "${AQUI}/instalador-web.nsi" "${TRABAJO}/"
cp "${ICO}" "${TRABAJO}/"
cd "${TRABAJO}"
export NSISDIR="${NSISDIR:-/home/z/nsis/NSIS}"
# -V4 es OBLIGATORIO: el log lista 'File: "nombre" [compress] ...' por cada
# archivo que el instalador extraera (sin -V4 el log no los imprime y la
# verificacion de abajo no tiene nada que contar).
PATH="/home/z/nsis/bin:${PATH}" makensis -V4 instalador-web.nsi > makensis.log 2>&1 \
  || { tail -30 makensis.log; echo "makensis FALLO"; exit 1; }

# Leccion v1.0.1: se entrego un exe OBSOLETO sin arrancar.vbs (build de las
# 16:05 con scripts anteriores a la correccion de las 16:08). El log de
# makensis lista CADA archivo que el instalador extraera (formato
# 'File: "nombre" [compress] a/b bytes'), asi que se comprueba AQUI y no en
# el PC del usuario.
empaquetados="$(grep -c '^File: "' makensis.log || true)"
reales="$(find "${PAYLOAD}" -type f | wc -l)"
echo "    Archivos que extraera el instalador: ${empaquetados} / esperados: ${reales}"
[ "${empaquetados}" -eq "${reales}" ] \
  || { echo "MISMATCH de conteo (¿dotfiles perdidos por el globbing?)"; grep '^File: "' makensis.log | head -10; exit 1; }
for clave in LEEME.txt detener.ps1 DMVoiceWeb-Depuracion.bat node.exe \
             DMVoiceChangerWeb.exe main.js arranque.cjs server.js plantilla.db DMVoiceChanger.ico; do
  grep -qF "\"${clave}\"" makensis.log \
    || { echo "FALTA en el instalador: ${clave}"; exit 1; }
done
descensos="$(grep -c 'Descending to: "payload/app/.next/' makensis.log || true)"
[ "${descensos}" -ge 5 ] \
  || { echo "El instalador NO incluye .next (descensos: ${descensos})"; exit 1; }
echo "    Contenido verificado: los ${empaquetados} archivos llegan al .exe (.next: ${descensos} subcarpetas)."

mkdir -p "${RAIZ_REPO}/download"
rm -f "${RAIZ_REPO}/download/DMVoiceChangerWeb.exe"   # viejo sin version: fuera
mv "${TRABAJO}"'/DMVoiceChangerWeb-'*.exe "${RAIZ_REPO}/download/"
ls -la "${RAIZ_REPO}"'/download/DMVoiceChangerWeb-'*.exe
NOMBRE_EXE=$(cd "${RAIZ_REPO}/download" && ls DMVoiceChangerWeb-*.exe | head -1)
echo "Listo: ${RAIZ_REPO}/download/${NOMBRE_EXE}"
