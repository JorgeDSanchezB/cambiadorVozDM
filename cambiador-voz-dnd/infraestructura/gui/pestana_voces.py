"""Pestaña 🎤 Voces: lista desplegable, botones grandes, REC y monitor."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PestanaVoces(QWidget):
    def __init__(self, motor, gestor_voces, medidor, padre=None) -> None:
        super().__init__(padre)
        self.motor = motor
        self.gestor_voces = gestor_voces
        self._botones: dict[str, list] = {}  # id → (botón, color)

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        # --- Selector desplegable + modo + latencia ------------------------ #
        fila_superior = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumHeight(40)
        self.combo.currentIndexChanged.connect(self._cambio_combo)
        fila_superior.addWidget(QLabel("Voz activa:"), 0)
        fila_superior.addWidget(self.combo, 1)
        self.etiqueta_modo = QLabel("Modo: —")
        self.etiqueta_modo.setStyleSheet("font-weight:700;")
        fila_superior.addWidget(self.etiqueta_modo)
        self.etiqueta_latencia = QLabel("Latencia: —")
        fila_superior.addWidget(self.etiqueta_latencia)
        raiz.addLayout(fila_superior)

        # --- Botones grandes ---------------------------------------------- #
        grupo_botones = QGroupBox("Voces rápidas")
        self.grid_botones = QGridLayout(grupo_botones)
        self.grid_botones.setSpacing(10)
        raiz.addWidget(grupo_botones, 1)

        # --- Grabación y monitor ------------------------------------------ #
        grupo_rec = QGroupBox("Grabación de la sesión")
        fila_rec = QHBoxLayout(grupo_rec)
        self.boton_rec = QPushButton("⏺ Grabar")
        self.boton_rec.setMinimumHeight(48)
        self.boton_rec.setStyleSheet(
            "background:#dc2626;color:white;font-weight:700;border-radius:8px;"
        )
        self.boton_rec.clicked.connect(self._alternar_grabacion)
        self.etiqueta_rec = QLabel("Sin grabación")
        self.monitor = QCheckBox("Monitor (escuchar la voz transformada)")
        self.monitor.setChecked(True)
        self.monitor.toggled.connect(self._cambio_monitor)
        fila_rec.addWidget(self.boton_rec)
        fila_rec.addWidget(self.etiqueta_rec, 1)
        fila_rec.addWidget(self.monitor)
        raiz.addWidget(grupo_rec)

        # --- Medidor de nivel --------------------------------------------- #
        fila_nivel = QHBoxLayout()
        fila_nivel.addWidget(QLabel("Nivel de salida:"))
        fila_nivel.addWidget(medidor, 1)
        raiz.addLayout(fila_nivel)

    # ------------------------------------------------------------------ #
    def poblar(self, voces) -> None:
        """Redibuja combo + grid de botones desde la lista de voces."""
        self.combo.blockSignals(True)
        self.combo.clear()
        for voz in voces:
            self.combo.addItem(f"{voz.icono} {voz.nombre}", userData=voz.id)
        self.combo.blockSignals(False)

        while self.grid_botones.count():
            item = self.grid_botones.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        columnas = 4
        for posicion, voz in enumerate(voces):
            boton = QPushButton(f"{voz.icono}\n{voz.nombre}")
            boton.setMinimumSize(150, 96)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setStyleSheet(
                f"QPushButton {{ background:{voz.color}; color:white;"
                "border:2px solid rgba(0,0,0,0.25); border-radius:12px;"
                "font-size:15px; font-weight:700; padding:8px; }"
                f"QPushButton:hover {{ border:2px solid #facc15; }}"
            )
            boton.clicked.connect(
                lambda _=False, vid=voz.id: self.activar_por_id(vid, desde_combo=True)
            )
            fila, columna = divmod(posicion, columnas)
            self.grid_botones.addWidget(boton, fila, columna)
            self._botones[voz.id] = boton

        if voces:
            self.combo.setCurrentIndex(0)
            self.activar_por_id(voces[0].id, desde_combo=False)

    def activar_por_id(self, id_voz: str, desde_combo: bool = True) -> None:
        voz = self.gestor_voces.buscar_por_id(id_voz)
        if voz is None:
            return
        self.motor.aplicar_voz(voz)
        if not desde_combo:
            indice = self.combo.findData(id_voz)
            if indice >= 0:
                self.combo.blockSignals(True)
                self.combo.setCurrentIndex(indice)
                self.combo.blockSignals(False)
        self._marcar_boton_activo(id_voz)

    def _marcar_boton_activo(self, id_voz: str) -> None:
        voz = self.gestor_voces.buscar_por_id(id_voz)
        for vid, boton in self._botones.items():
            color = voz.color if voz else "#6b7280"
            borde = "3px solid #facc15" if vid == id_voz else "2px solid rgba(0,0,0,0.25)"
            boton.setStyleSheet(
                f"QPushButton {{ background:{color}; color:white; border:{borde};"
                "border-radius:12px; font-size:15px; font-weight:700; padding:8px; }"
                "QPushButton:hover { border:3px solid #facc15; }"
            )

    def _cambio_combo(self, indice: int) -> None:
        id_voz = self.combo.itemData(indice)
        if id_voz:
            self.activar_por_id(id_voz, desde_combo=False)

    def _cambio_monitor(self, activo: bool) -> None:
        self.motor.monitor = activo

    def _alternar_grabacion(self) -> None:
        grabador = self.motor.grabador
        if not grabador.grabando:
            grabador.iniciar()
            self.boton_rec.setText("⏹ Detener")
            self.boton_rec.setStyleSheet(
                "background:#111827;color:white;font-weight:700;border-radius:8px;"
            )
            self.etiqueta_rec.setText("Grabando…")
        else:
            grabador.detener()
            self.boton_rec.setText("⏺ Grabar")
            self.boton_rec.setStyleSheet(
                "background:#dc2626;color:white;font-weight:700;border-radius:8px;"
            )
            self.etiqueta_rec.setText("Exportando…")

    def al_terminar_grabacion(self, ruta: str) -> None:
        self.etiqueta_rec.setText(f"Guardado: {ruta}")
