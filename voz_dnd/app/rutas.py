"""Rutas canónicas de la aplicación (única fuente de verdad)."""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CARPETA_VOCES = DATA_DIR / "voces"
RUTA_CONFIG = DATA_DIR / "config.json"
RUTA_PARAMETROS = DATA_DIR / "parametros.json"
RUTA_LOGS = BASE_DIR / "logs"
# Datasets de clonación (fundación experimental del modo IA RVC):
# muestras WAV del sujeto + su registro de consentimiento. NO versionada
# (es material de la máquina del DM, igual que lectura/).
CARPETA_CLONACION = DATA_DIR / "clonacion"
