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
printf 'python314.zip\n.\nLib/site-packages\nimport site\n' \
  > "${PAYLOAD}/runtime/python314._pth"

echo "[5/7] Copiando el código de voz_dnd..."
# Se excluye el propio workspace de construcción (_build, wheels): si no,
# el payload se copiaría a sí mismo y el instalador se hincharía ~100 MB.
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='logs' \
  --exclude='tests' --exclude='.venv' \
  --exclude='_build' --exclude='wheels' \
  "${AQUI}/../" "${PAYLOAD}/app/"
rm -f "${PAYLOAD}/app/iniciar_voz_dnd.bat"

echo "[6/7] Preparando icono y lanzador de depuración..."
cp "${AQUI}/DMVoiceChanger.ico" "${PAYLOAD}/DMVoiceChanger.ico"
cat > "${PAYLOAD}/DMVoiceChanger-Depuracion.bat" <<'BAT'
@echo off
REM DMVoiceChanger - modo depuracion (muestra consola de errores)
cd /d "%~dp0app"
"%~dp0runtime\python.exe" main.py
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
