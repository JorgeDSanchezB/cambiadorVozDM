"""Widgets reutilizables: medidor de nivel, banners de alerta y botones de voz."""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QPushButton, QWidget


class MedidorNivel(QWidget):
    """Barra de volumen en tiempo real (~30 FPS, verde→ámbar→rojo).

    Lee un float GIL-atómico del motor (`motor.nivel`, 0..1) con un QTimer
    interno: el hilo de audio NUNCA dibuja en la GUI.
    """

    def __init__(self, motor, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._motor = motor
        self._nivel = 0.0
        self._pico = 0.0
        self.setMinimumSize(140, 18)
        self.setToolTip("Nivel de salida")

        self._temporizador = QTimer(self)
        self._temporizador.setInterval(33)
        self._temporizador.timeout.connect(self._refrescar)
        self._temporizador.start()

    def _refrescar(self) -> None:
        objetivo = float(getattr(self._motor, "nivel", 0.0))
        # Suavizado (attack rápido, release lento) para lectura agradable.
        self._nivel = objetivo if objetivo > self._nivel else self._nivel * 0.85 + objetivo * 0.15
        self._pico = max(self._pico * 0.97, self._nivel)
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        recta = QRectF(0, 0, self.width(), self.height())

        pintor.setPen(QPen(QColor("#d1d5db"), 1))
        pintor.drawRoundedRect(recta.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

        franja = recta.adjusted(3, 3, -3, -3)
        nivel = float(np.clip(self._nivel, 0.0, 1.0))
        ancho = franja.width() * nivel
        # Tres tramos de color según la zona alcanzada.
        zonas = [(0.0, 0.6, "#22c55e"), (0.6, 0.85, "#eab308"), (0.85, 1.0, "#ef4444")]
        for inicio, fin, color in zonas:
            desde = max(inicio, 0.0)
            hasta = min(fin, nivel)
            if hasta <= desde:
                continue
            tramo = QRectF(
                franja.x() + franja.width() * desde,
                franja.y(),
                franja.width() * (hasta - desde),
                franja.height(),
            )
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(QColor(color))
            pintor.drawRect(tramo)

        # Marca de pico
        if self._pico > 0.01:
            x = franja.x() + franja.width() * min(self._pico, 1.0)
            pintor.setPen(QPen(QColor("#111827"), 2))
            pintor.drawLine(int(x), int(franja.y()), int(x), int(franja.bottom()))


class BannerAlerta(QWidget):
    """Banner de estado/apoyo visual: ámbar=aviso, rojo=error, verde=ok."""

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setText("")
        self.setStyleSheet(self._estilo("#fbbf24", "#78350f"))
        self.setWordWrap(True)
        self.hide()
        self._ocultar = QTimer(self)
        self._ocultar.setSingleShot(True)
        self._ocultar.timeout.connect(self.hide)

    @staticmethod
    def _estilo(fondo: str, texto: str) -> str:
        return (
            f"background: {fondo}; color: {texto};"
            "border-radius: 6px; padding: 6px 10px; font-weight: 600;"
        )

    def mostrar(self, mensaje: str, tipo: str = "aviso", segundos: int = 10) -> None:
        estilos = {
            "aviso": self._estilo("#fbbf24", "#78350f"),
            "error": self._estilo("#fca5a5", "#7f1d1d"),
            "ok": self._estilo("#86efac", "#14532d"),
        }
        self.setStyleSheet(estilos.get(tipo, estilos["aviso"]))
        self.setText(mensaje)
        self.show()
        self._ocultar.start(max(3, segundos) * 1000)


class BotonVoz(QPushButton):
    """Botón grande de voz (mínimo 96 px de alto, accesible y táctil)."""

    def __init__(self, texto: str, color: str, atajo: str | None, padre=None) -> None:
        super().__init__(texto, padre)
        self.setMinimumSize(150, 96)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {color};
                color: white;
                border: 2px solid rgba(0,0,0,0.25);
                border-radius: 12px;
                font-size: 15px;
                font-weight: 700;
                padding: 8px;
            }}
            QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.8); }}
            QPushButton:pressed {{ background: {color}; }}
            """
        )
        if atajo:
            self.setText(f"{texto}\n[{atajo}]")

    def marcar_activa(self, activa: bool) -> None:
        borde = "3px solid #facc15" if activa else "2px solid rgba(0,0,0,0.25)"
        hoja = self.styleSheet().replace(
            "border: 3px solid #facc15;", "border: 2px solid rgba(0,0,0,0.25);"
        ).replace("border: 2px solid rgba(0,0,0,0.25);", f"border: {borde};")
        self.setStyleSheet(hoja)
