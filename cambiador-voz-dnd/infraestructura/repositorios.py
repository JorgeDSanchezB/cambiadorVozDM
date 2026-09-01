"""Repositorios JSON: única capa que toca los archivos de configuración."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

CONFIG_POR_DEFECTO: dict[str, Any] = {
    "version": 1,
    "audio": {
        "sample_rate": 48000,
        "buffer_size": 256,
        "dispositivo_entrada": None,
        "dispositivo_salida": None,
        "canales_salida": 2,
    },
    "grabacion": {
        "carpeta_destino": "./grabaciones",
        "formato": "mp3",
        "bitrate_kbps": 192,
        "patron_nombre": "voz_{fecha}_{hora}",
    },
    "atajos": {},
    "motor": {
        "modo": "DSP",
        "permitir_ia": True,
        "ruta_plugin_rvc": "./modelos/plugin_rvc.py",
    },
    "ui": {"vista_botones": True, "columnas_botones": 4},
}


class RepoConfig:
    """Carga `config.json` fusionándolo con los valores por defecto
    (profundo) para que un config antiguo/incompleto nunca rompa la app."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def cargar(self) -> dict[str, Any]:
        config = copy.deepcopy(CONFIG_POR_DEFECTO)
        if self.ruta.exists():
            try:
                datos = json.loads(self.ruta.read_text(encoding="utf-8"))
                self._fusionar(config, datos)
            except (json.JSONDecodeError, OSError):
                # config corrupto → se usan los valores por defecto.
                pass
        # Sanidad del buffer (tolerancia a valores absurdos).
        buffer = int(config["audio"].get("buffer_size", 256))
        config["audio"]["buffer_size"] = buffer if buffer in (128, 256, 512, 1024) else 256
        return config

    def guardar(self, config: dict[str, Any]) -> None:
        self.ruta.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _fusionar(base: dict[str, Any], extra: dict[str, Any]) -> None:
        for clave, valor in (extra or {}).items():
            if clave in base and isinstance(base[clave], dict) and isinstance(valor, dict):
                RepoConfig._fusionar(base[clave], valor)
            else:
                base[clave] = valor


class RepoCatalogo:
    """Lee `data/parametros.json`: rangos compartidos por Fábrica y Editor."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)

    def cargar(self) -> dict[str, dict]:
        if not self.ruta.exists():
            raise FileNotFoundError(f"Catálogo de parámetros no encontrado: {self.ruta}")
        datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        parametros = datos.get("parametros", {})
        # Orden estable para el Editor
        return dict(sorted(parametros.items()))
