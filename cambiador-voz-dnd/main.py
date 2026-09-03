"""Punto de entrada: python main.py

Opciones:
    python main.py                 → abre la aplicación
    python main.py --list-devices → lista los dispositivos de audio y sale
    python main.py --verificar    → autoverificación (DSP + entorno) sin GUI

Arquitectura de arranque (Fase 1):
    Infraestructura (repositorios JSON) → Aplicación (gestores + motor)
    → Infraestructura GUI (ventana PyQt6) → exec.
"""
from __future__ import annotations

import argparse
import logging
import queue
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

CARPETA_RAIZ = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
#  Logging (logs/app.log, rotativo; los errores nunca pasan desapercibidos)
# --------------------------------------------------------------------------- #
def configurar_logging() -> logging.Logger:
    carpeta_logs = CARPETA_RAIZ / "logs"
    carpeta_logs.mkdir(exist_ok=True)
    logger = logging.getLogger("voz_dnd")
    logger.setLevel(logging.INFO)
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    archivo = RotatingFileHandler(
        carpeta_logs / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    archivo.setFormatter(formato)
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    logger.addHandler(archivo)
    logger.addHandler(consola)
    return logger


LOG = configurar_logging()


# --------------------------------------------------------------------------- #
#  Comandos sin GUI
# --------------------------------------------------------------------------- #
def listar_dispositivos() -> int:
    try:
        import sounddevice as sd

        print(sd.query_devices())
        print("\nDispositivos de ENTRADA (micrófonos):")
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"  [{i}] {d['name']}")
        print("\nDispositivos de SALIDA (altavoces/auriculares):")
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                print(f"  [{i}] {d['name']}")
        return 0
    except Exception as exc:
        print(f"Error accediendo a PortAudio/sounddevice: {exc}")
        return 1


def ejecutar_verificacion() -> int:
    import verificar_instalacion

    return verificar_instalacion.ejecutar(CARPETA_RAIZ, con_gui=False)


# --------------------------------------------------------------------------- #
#  Arranque de la aplicación
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Cambiador de voz en tiempo real para DM de D&D")
    parser.add_argument("--list-devices", action="store_true", help="lista dispositivos de audio")
    parser.add_argument("--verificar", action="store_true", help="autoverificación sin GUI")
    argumentos = parser.parse_args()

    if argumentos.list_devices:
        return listar_dispositivos()
    if argumentos.verificar:
        return ejecutar_verificacion()

    # --- Dependencias de GUI: errores claros si faltan --------------------- #
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        LOG.error("Falta PyQt6. Instala: pip install -r requirements.txt (%s)", exc)
        print("\n✖ Falta PyQt6. Ejecuta:  pip install -r requirements.txt")
        return 1
    try:
        import sounddevice as sd  # noqa: F401
    except ImportError as exc:
        LOG.error("Falta sounddevice/PortAudio: %s", exc)
        print("\n✖ Falta sounddevice. Ejecuta:  pip install -r requirements.txt")
        return 1

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from aplicacion.gestor_grabacion import GestorGrabacion, comprobar_ffmpeg
    from aplicacion.gestor_voces import GestorVoces
    from aplicacion.motor_audio import MotorAudio
    from infraestructura.gui.ventana_principal import VentanaPrincipal
    from infraestructura.repositorios import RepoCatalogo, RepoConfig

    # Alta-DPI: nitidez en Windows 10/11
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Cambiador de Voz D&D")

    # --- Infraestructura --------------------------------------------------- #
    repo_config = RepoConfig(CARPETA_RAIZ / "data" / "config.json")
    config = repo_config.cargar()
    try:
        catalogo = RepoCatalogo(CARPETA_RAIZ / "data" / "parametros.json").cargar()
    except FileNotFoundError as exc:
        LOG.critical("%s", exc)
        QMessageBox.critical(None, "Instalación rota", str(exc))
        return 1

    eventos: "queue.SimpleQueue[tuple[str, ...]]" = queue.SimpleQueue()

    # --- Aplicación --------------------------------------------------------- #
    grabador = GestorGrabacion(config, int(config["audio"]["sample_rate"]), eventos)
    motor = MotorAudio(config, eventos, grabador)
    gestor_voces = GestorVoces(
        CARPETA_RAIZ / "data" / "voces", catalogo, eventos
    )

    if not comprobar_ffmpeg():
        eventos.put((
            "aviso",
            "ffmpeg no está en el PATH: la grabación se exportará en WAV. "
            "Ver README (instalación).",
        ))

    # --- GUI ----------------------------------------------------------------- #
    try:
        ventana = VentanaPrincipal(motor, gestor_voces, config, repo_config, catalogo)
        ventana.show()
    except Exception as exc:
        LOG.exception("Error inicializando la GUI: %s", exc)
        QMessageBox.critical(None, "Error de GUI", f"No se pudo iniciar la interfaz:\n{exc}")
        return 1

    # Arrancar audio una vez visible la ventana (los avisos se ven).
    ventana.iniciar_audio()

    # --- Excepción global: log + diálogo, la app no muere en silencio ------- #
    def hook_excepciones(tipo, valor, traza):
        LOG.critical("Excepción no controlada", exc_info=(tipo, valor, traza))
        QMessageBox.critical(
            None, "Error inesperado", f"{tipo.__name__}: {valor}\n\nRevisa logs/app.log"
        )

    sys.excepthook = hook_excepciones

    LOG.info("Aplicación iniciada (buffer=%s, sr=%s)",
             config["audio"]["buffer_size"], config["audio"]["sample_rate"])
    codigo = app.exec()
    motor.detener()
    LOG.info("Aplicación cerrada (código %s)", codigo)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
