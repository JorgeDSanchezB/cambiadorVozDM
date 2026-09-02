@echo off
REM ============================================================
REM  Cambiador de Voz D&D - inicio rapido (Windows 10/11)
REM  Crea el entorno virtual, instala dependencias y arranca.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] Creando entorno virtual...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    echo [2/3] Instalando dependencias...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo [3/3] Iniciando Cambiador de Voz D&D...
python main.py
pause
