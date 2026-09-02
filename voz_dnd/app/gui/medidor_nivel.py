"""Medidor de nivel de volumen en tiempo real (widget pintado a mano).

La GUI lo refresca a ~30 FPS leyendo `motor.nivel_db` (valor escrito por el
callback de audio): verde → ámbar → rojo, con marca de pico que decae.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

PISO_DB = -60.0
CAIDA_PICO_DB = 0.6  # caída del pico por refresco (≈ 18 dB/s a 30 FPS)


class MedidorNivel(QWidget):
    def __init__(self):
        super().__init__()
        self._nivel_db = PISO_DB
        self._pico_db = PISO_DB
        self.setMinimumSize(140, 18)
        self.setMaximumHeight(22)

    def set_nivel(self, db: float) -> None:
        self._nivel_db = max(PISO_DB, min(0.0, float(db)))
        self._pico_db = max(self._pico_db - CAIDA_PICO_DB, self._nivel_db)
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho, alto = self.width(), self.height()

        # Fondo del canal
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor("#24272e"))
        pintor.drawRoundedRect(0, 0, ancho, alto, 6, 6)

        # Barra de nivel
        fraccion = (self._nivel_db - PISO_DB) / (-PISO_DB)
        if fraccion > 0.001:
            gradiente = QLinearGradient(0, 0, ancho, 0)
            gradiente.setColorAt(0.00, QColor("#3f8f4f"))
            gradiente.setColorAt(0.75, QColor("#d8b13c"))
            gradiente.setColorAt(1.00, QColor("#c2453a"))
            pintor.setBrush(gradiente)
            pintor.drawRoundedRect(2, 2, int((ancho - 4) * fraccion), alto - 4, 4, 4)

        # Marca de pico
        if self._pico_db > PISO_DB:
            x = 2 + int((ancho - 4) * (self._pico_db - PISO_DB) / (-PISO_DB))
            pintor.setBrush(QColor("#e8e3d5"))
            pintor.drawRect(min(x, ancho - 4), 2, 2, alto - 4)
