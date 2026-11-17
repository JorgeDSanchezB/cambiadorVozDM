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

echo "[5/8] Descargando Node.js ${NODE_VER} (win-x64 para el exe, linux-x64 para el smoke test)..."
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

echo "[6/8] Ensamblando el payload del instalador..."
rsync -a "${APP_SRC}/.next/standalone/" "${PAYLOAD}/app/"
cp "${TRABAJO}/plantilla/plantilla.db" "${PAYLOAD}/app/plantilla.db"
cp "${ICO}" "${PAYLOAD}/DMVoiceChanger.ico"

# ---- arranque.cjs: fija entorno (puerto, DB por usuario) y lanza server.js ----
cat > "${PAYLOAD}/app/arranque.cjs" <<CJS
// DMVoiceChanger Web - arranque del servidor local.
// La base de datos vive FUERA de la instalacion (sobrevive a updates):
// %LOCALAPPDATA%\\DMVoiceWeb\\voces.db (se copia de la plantilla al primer uso).
const fs = require('fs');
const os = require('os');
const path = require('path');

const AQUI = __dirname;
const base = process.env.LOCALAPPDATA || process.env.USERPROFILE || os.homedir();
const datos = path.join(base, 'DMVoiceWeb');
fs.mkdirSync(datos, { recursive: true });

const db = path.join(datos, 'voces.db');
if (!fs.existsSync(db) && fs.existsSync(path.join(AQUI, 'plantilla.db'))) {
  fs.copyFileSync(path.join(AQUI, 'plantilla.db'), db);
}

process.env.NODE_ENV = 'production';
process.env.PORT = process.env.DMVOICEWEB_PORT || '${PUERTO}';
process.env.HOSTNAME = '127.0.0.1';   // SOLO local: nunca expuesto a la red
process.env.DATABASE_URL = 'file:' + db.replace(/\\\\/g, '/');

process.chdir(AQUI);
require('./server.js');
CJS

# ---- arrancar.vbs: sin consola. Levanta node oculto (si no está ya) y abre el navegador ----
cat > "${PAYLOAD}/arrancar.vbs" <<'VBS'
' DMVoiceChanger Web - arranque silencioso del servidor local + navegador
Option Explicit
Dim sh, raiz, intentos
Set sh = CreateObject("WScript.Shell")
raiz = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)

Function Listo()
  On Error Resume Next
  Dim http
  Set http = CreateObject("MSXML2.XMLHTTP")
  http.Open "GET", "http://127.0.0.1:3987/", False
  http.Send ""
  Listo = (http.Status = 200)
End Function

If Not Listo() Then
  sh.Run """" & raiz & "\runtime\node.exe"" """ & raiz & "\app\arranque.cjs""", 0, False
  intentos = 0
  Do While Not Listo() And intentos < 120
    WScript.Sleep 250
    intentos = intentos + 1
  Loop
End If
sh.Run "http://127.0.0.1:3987/"
VBS

# ---- detener: cierra SOLO el node de DMVoiceChangerWeb (por línea de comando) ----
cat > "${PAYLOAD}/detener.ps1" <<'PS1'
# Detiene el servidor local de DMVoiceChanger Web (y solo el suyo)
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like '*DMVoiceChangerWeb*arranque.cjs*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
PS1
cat > "${PAYLOAD}/detener.vbs" <<'VBS'
' DMVoiceChanger Web - detencion del servidor (oculto) con confirmacion
Option Explicit
Dim sh, raiz
Set sh = CreateObject("WScript.Shell")
raiz = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File """ & raiz & "\detener.ps1""", 0, True
MsgBox "Servidor de DMVoiceChanger Web detenido.", 64, "DMVoiceChanger Web"
VBS

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
test -f "${PAYLOAD}/arrancar.vbs"           || { echo "FALTA arrancar.vbs"; exit 1; }
test -f "${PAYLOAD}/detener.vbs"            || { echo "FALTA detener.vbs"; exit 1; }
test -f "${PAYLOAD}/detener.ps1"            || { echo "FALTA detener.ps1"; exit 1; }
test -f "${PAYLOAD}/DMVoiceWeb-Depuracion.bat" || { echo "FALTA DMVoiceWeb-Depuracion.bat"; exit 1; }
head -c 2 "${PAYLOAD}/runtime/node.exe" | grep -q "MZ" || { echo "node.exe no es un PE valido"; exit 1; }
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

echo "[8/8] Compilando el instalador NSIS..."
cp "${AQUI}/instalador-web.nsi" "${TRABAJO}/"
cp "${ICO}" "${TRABAJO}/"
cd "${TRABAJO}"
export NSISDIR="${NSISDIR:-/home/z/nsis/NSIS}"
PATH="/home/z/nsis/bin:${PATH}" makensis instalador-web.nsi

mkdir -p "${RAIZ_REPO}/download"
mv "${TRABAJO}/DMVoiceChangerWeb.exe" "${RAIZ_REPO}/download/DMVoiceChangerWeb.exe"
echo "Listo: ${RAIZ_REPO}/download/DMVoiceChangerWeb.exe"
