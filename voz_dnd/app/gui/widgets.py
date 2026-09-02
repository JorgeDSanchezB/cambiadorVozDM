"""Widgets reutilizables de la GUI."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class BannerAlerta(QFrame):
    """Banner de avisos (tolerancia a fallos visible, Fase 5.5).

    Niveles: info (ámbar) y error (rojo). Los mensajes de info se auto-
    ocultan a los 8 s; los errores permanecen hasta que el usuario los cierre.
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("banner")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        self._icono = QLabel("⚠")
        self._texto = QLabel("")
        self._texto.setWordWrap(True)
        self._texto.setStyleSheet("color:#f3e9c8;")
        boton = QPushButton("✕")
        boton.setFixedSize(24, 24)
        boton.setStyleSheet(
            "QPushButton{background:transparent;color:#f3e9c8;border:none;font-weight:700;}"
            "QPushButton:hover{color:#ffffff;}")
        boton.clicked.connect(self.ocultar)
        layout.addWidget(self._icono)
        layout.addWidget(self._texto, 1)
        layout.addWidget(boton)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.ocultar)

    # ------------------------------------------------------------------ #
    def mostrar_info(self, mensaje: str) -> None:
        self._aplicar_estilo("#5a4a1f", "#d8b13c")
        self._texto.setText(mensaje)
        self.setVisible(True)
        self._timer.start(8000)

    def mostrar_error(self, mensaje: str) -> None:
        self._aplicar_estilo("#5f1f1f", "#c2453a")
        self._texto.setText(mensaje)
        self.setVisible(True)
        self._timer.stop()

    def mostrar_avisos(self, mensajes: list[str]) -> None:
        if not mensajes:
            return
        self.mostrar_info(" · ".join(mensajes[:5])
                          + ("…" if len(mensajes) > 5 else ""))

    def ocultar(self) -> None:
        self.setVisible(False)
        self._timer.stop()

    # ------------------------------------------------------------------ #
    def _aplicar_estilo(self, fondo: str, borde: str) -> None:
        self.setStyleSheet(
            f"QFrame#banner{{background:{fondo};border:1px solid {borde};"
            f"border-radius:6px;}}")
        self._icono.setStyleSheet(f"color:{borde};font-size:16px;font-weight:700;")
