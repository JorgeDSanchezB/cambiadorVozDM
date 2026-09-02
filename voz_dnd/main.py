"""Punto de entrada — Cambiador de Voz en Tiempo Real para DM de D&D.

Ejecución (Windows 10/11, Python 3.10+):
    pip install -r requirements.txt
    python main.py

Arquitectura: Fases 1-5 del diseño (ver README.md).
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.gui.main_window import VentanaPrincipal
from app.rutas import RUTA_LOGS


def _configurar_logging() -> None:
    RUTA_LOGS.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    archivo = RotatingFileHandler(
        RUTA_LOGS / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    archivo.setFormatter(formato)

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(archivo)
    raiz.addHandler(consola)


def main() -> int:
    _configurar_logging()
    logging.info("=== Arranque del Cambiador de Voz D&D ===")

    app = QApplication(sys.argv)
    app.setApplicationName("Cambiador de Voz D&D")
    app.setOrganizationName("MesaRedonda")

    def _excepcion_global(tipo, valor, traza) -> None:
        logging.critical("Excepción no capturada", exc_info=(tipo, valor, traza))
        QMessageBox.critical(
            None, "Error inesperado",
            f"Ocurrió un error:\n{valor}\n\nRevisa logs/app.log para más detalle.")

    sys.excepthook = _excepcion_global

    ventana = VentanaPrincipal()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
