"""Pestaña "🎤 Voces": lista desplegable + botones grandes (Fase 5.1).

Los botones se generan DESDE JSON (icono, color, nombre, atajo): añadir
una voz nueva no requiere tocar esta clase. La voz activa se resalta con
un borde claro y el combo se mantiene sincronizado en ambos sentidos.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import IVoiceProfile

COLUMNAS_GRID = 4


class PestanaVoces(QWidget):
    senal_voz_seleccionada = pyqtSignal(str)   # id (UUID como str)
    senal_recargar = pyqtSignal()              # re-lee los JSON del disco

    def __init__(self):
        super().__init__()
        self._voces: list[IVoiceProfile] = []
        self._botones: dict[str, QPushButton] = {}
        self._cargando = False  # evita rebotes de señales al repoblar

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(10)

        # ---- Fila superior: combo + recargar + estado del motor ----
        fila = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumHeight(34)
        self.combo.currentIndexChanged.connect(self._combo_cambiado)
        boton_recargar = QPushButton("🔄 Recargar")
        boton_recargar.clicked.connect(self.senal_recargar.emit)
        fila.addWidget(QLabel("Voz:"))
        fila.addWidget(self.combo, 1)
        fila.addWidget(boton_recargar)
        raiz.addLayout(fila)

        self.etiqueta_estado = QLabel("")
        self.etiqueta_estado.setStyleSheet("color:#9aa4b2;")
        raiz.addWidget(self.etiqueta_estado)

        # ---- Grid de botones grandes dentro de un scroll ----
        self.contenedor_grid = QWidget()
        self.grid = QGridLayout(self.contenedor_grid)
        self.grid.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.contenedor_grid)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        raiz.addWidget(scroll, 1)

    # ------------------------------ API ---------------------------------- #
    def poblar(self, voces: list[IVoiceProfile], seleccionar_id: str | None = None) -> None:
        self._cargando = True
        self._voces = voces
        self._limpiar_grid()

        self.combo.clear()
        for voz in voces:
            etiqueta_atajo = f"  [{voz.atajo}]" if voz.atajo else ""
            self.combo.addItem(f"{voz.icono} {voz.nombre}{etiqueta_atajo}", str(voz.id))

        for i, voz in enumerate(voces):
            boton = QPushButton(f"{voz.icono}\n{voz.nombre}"
                                + (f"\n({voz.atajo})" if voz.atajo else ""))
            boton.setMinimumSize(150, 96)
            boton.clicked.connect(
                lambda _=False, id_voz=str(voz.id): self.senal_voz_seleccionada.emit(id_voz))
            boton.setStyleSheet(self._estilo_boton(voz.color, activo=False))
            self._botones[str(voz.id)] = boton
            self.grid.addWidget(boton, i // COLUMNAS_GRID, i % COLUMNAS_GRID)

        indice = self._indice_de(seleccionar_id)
        if indice >= 0:
            self.combo.setCurrentIndex(indice)
        self._cargando = False

    def marcar_activa(self, id_voz: str) -> None:
        self._cargando = True  # el combo se mueve por código, sin re-emitir
        for id_actual, boton in self._botones.items():
            voz = self._voz_por_id(id_actual)
            activo = (id_actual == id_voz)
            color = voz.color if voz is not None else "#4a5d3a"
            boton.setStyleSheet(self._estilo_boton(color, activo))
            if activo:
                indice = self._indice_de(id_voz)
                if indice >= 0:
                    self.combo.setCurrentIndex(indice)
        self._cargando = False

    def set_estado(self, texto: str) -> None:
        self.etiqueta_estado.setText(texto)

    # ---------------------------- internos -------------------------------- #
    def _limpiar_grid(self) -> None:
        self._botones.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _indice_de(self, id_voz: str | None) -> int:
        if id_voz is None:
            return -1
        return self.combo.findData(str(id_voz))

    def _voz_por_id(self, id_voz: str) -> IVoiceProfile | None:
        for voz in self._voces:
            if str(voz.id) == id_voz:
                return voz
        return None

    def _combo_cambiado(self, indice: int) -> None:
        if self._cargando or indice < 0:
            return
        id_voz = self.combo.itemData(indice)
        if id_voz:
            self.senal_voz_seleccionada.emit(str(id_voz))

    @staticmethod
    def _estilo_boton(color: str, activo: bool) -> str:
        borde = "3px solid #e8e3d5" if activo else "2px solid transparent"
        return (
            f"QPushButton{{background-color:{color};color:#ffffff;border-radius:10px;"
            f"font-size:14px;font-weight:600;padding:6px;border:{borde};}}"
            "QPushButton:hover{border:2px solid #ffffff88;}"
            f"QPushButton:pressed{{background-color:{color};}}"
        )
