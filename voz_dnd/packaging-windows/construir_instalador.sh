#!/usr/bin/env bash
# ============================================================
#  DMVoiceChanger — construir el instalador de Windows (Linux)
#  Produce download/DMVoiceChanger.exe: instalador NSIS por
#  usuario que NO pide permisos de administrador y NO necesita
#  Python instalado (lleva runtime embebido + site-packages
#  preinstalados con wheels win_amd64 para cp314).
#
#  Uso:  ./construir_instalador.sh
#  Requisitos: python3 + pip, curl, makensis para Linux
#    (NSISDIR=/ruta/a/NSIS — ver README.md de esta carpeta)
# ============================================================
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
TRABAJO="${AQUI}/_build"
PAYLOAD="${TRABAJO}/payload"
RAIZ_REPO="$(cd "${AQUI}/../.." && pwd)"
PYTHON_VER="3.14.10"

mkdir -p "${TRABAJO}" "${PAYLOAD}/runtime/Lib/site-packages" "${PAYLOAD}/app" wheels
# Payload limpio en cada build: rsync sin --delete conservaría restos de
# builds anteriores (p. ej. wheels sueltos en site-packages).
rm -rf "${PAYLOAD}"
cd "${TRABAJO}"

echo "[1/7] Descargando Python ${PYTHON_VER} embebido (amd64)..."
curl -sL -o python314-embed.zip \
  "https://www.python.org/ftp/python/${PYTHON_VER}/python-${PYTHON_VER}-embed-amd64.zip"

echo "[2/7] Descargando wheels win_amd64 (PyQt6, sounddevice, numpy, scipy, pydub, edge-tts, soundfile, pip)..."
# pip se incluye porque el Python embebido NO lo trae: sin él, el botón
# «Instalar vía ONNX (CPU)» de Ajustes (python -m pip install rmvpe-onnx
# onnxruntime) no podría funcionar en la app instalada.
pip download --platform win_amd64 --python-version 3.14 --only-binary=:all: \
  -d wheels \
  "PyQt6>=6.6,<7" "sounddevice>=0.4.6" "numpy>=1.24" "scipy>=1.10" \
  "pydub>=0.25.1" "edge-tts>=6.1" "soundfile>=0.12" "pip>=24"

echo "[3/7] Descomprimiendo runtime + wheels..."
python3 -m zipfile -e python314-embed.zip "${PAYLOAD}/runtime/"
for w in wheels/*.whl; do
  python3 -m zipfile -e "$w" "${PAYLOAD}/runtime/Lib/site-packages/"
done
# Algunos wheels upstream dejan entradas *.whl fantasma (p. ej. scipy 1.18.1
# lleva un .whl de 0 bytes dentro); sobran en site-packages.
rm -f "${PAYLOAD}/runtime/Lib/site-packages/"*.whl

echo "[4/7] Configurando python314._pth..."
# El ._pth activa el MODO AISLADO del Python embebido: la carpeta del
# script NO se añade a sys.path. Sin la línea ..\app, el `import app` de
# main.py falla con ModuleNotFoundError y pythonw muere en silencio
# («nada pasa» al hacer doble clic). La ruta relativa se resuelve contra
# la carpeta del ._pth (runtime\) → INSTDIR\app.
cat > "${PAYLOAD}/runtime/python314._pth" <<'PTH'
python314.zip
.
..\app
Lib/site-packages
import site
PTH

echo "[5/7] Copiando el código de voz_dnd..."
# Se excluye el propio workspace de construcción (_build, wheels): si no,
# el payload se copiaría a sí mismo y el instalador se hincharía ~100 MB.
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='logs' \
  --exclude='tests' --exclude='.venv' \
  --exclude='_build' --exclude='wheels' \
  "${AQUI}/../" "${PAYLOAD}/app/"
rm -f "${PAYLOAD}/app/iniciar_voz_dnd.bat"

echo "[6/7] Preparando lanzador con registro de fallos, icono y depuración..."
# Lanzador robusto: pythonw no tiene consola; si algo falla ANTES de que
# main.py configure su app.log, el usuario solo ve «nada pasa». Este
# lanzador registra cualquier fallo (incluidos crashes duros vía
# faulthandler) en app\logs\arranque.log y ejecuta main.py igual que
# `python main.py` desde la carpeta app.
cat > "${PAYLOAD}/runtime/lanzar_app.py" <<'PY'
"""Arranque robusto de DMVoiceChanger - nunca muere en silencio."""
import faulthandler
import os
import sys
import traceback
from datetime import datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
APP = os.path.normpath(os.path.join(RAIZ, "..", "app"))
os.chdir(APP)
sys.path.insert(0, APP)  # cinturon y tirantes ademas de ..\app en el ._pth

RUTA_LOG = os.path.join(APP, "logs", "arranque.log")
os.makedirs(os.path.dirname(RUTA_LOG), exist_ok=True)

_log = open(RUTA_LOG, "a", encoding="utf-8")
_log.write(
    f"\n=== {datetime.now().isoformat(timespec='seconds')} · "
    f"Python {sys.version.split()[0]} · {sys.executable}\n"
)
_log.flush()
faulthandler.enable(_log)

try:
    import runpy

    runpy.run_path(os.path.join(APP, "main.py"), run_name="__main__")
    _log.write("ejecucion terminada\n")
except SystemExit as salida:
    _log.write(f"salida limpia (SystemExit {salida.code})\n")
except BaseException:
    _log.write(traceback.format_exc() + "\n")
    _log.flush()
    raise
PY
cp "${AQUI}/DMVoiceChanger.ico" "${PAYLOAD}/DMVoiceChanger.ico"
cat > "${PAYLOAD}/DMVoiceChanger-Depuracion.bat" <<'BAT'
@echo off
REM DMVoiceChanger - modo depuracion: consola visible + registro de fallos
cd /d "%~dp0app"
"%~dp0runtime\python.exe" "%~dp0runtime\lanzar_app.py"
echo.
echo Codigo de salida: %ERRORLEVEL%
pause
BAT

echo "[7/7] Compilando instalador NSIS..."
cp "${AQUI}/instalador.nsi" "${TRABAJO}/"
cp "${AQUI}/DMVoiceChanger.ico" "${TRABAJO}/"
cd "${TRABAJO}"
export NSISDIR="${NSISDIR:-/home/z/nsis/NSIS}"
makensis instalador.nsi

mkdir -p "${RAIZ_REPO}/download"
mv "${TRABAJO}/DMVoiceChanger.exe" "${RAIZ_REPO}/download/DMVoiceChanger.exe"
echo "Listo: ${RAIZ_REPO}/download/DMVoiceChanger.exe"
