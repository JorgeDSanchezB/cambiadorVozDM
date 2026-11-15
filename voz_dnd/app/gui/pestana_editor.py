"""Pestaña "🎚️ Editor de Voces" (Fase 5.2): sliders data-driven.

Los sliders NO están hardcodeados: se generan automáticamente a partir de
data/parametros.json (CatalogoParametros). El botón "▶ Probar" aplica la
cadena temporal durante 2 s sin tocar la voz guardada (la ventana principal
lo orquesta vía la señal `senal_probar`).

Para voces IA (PerfilIA) se edita su cadena `dsp_post`; los parámetros del
modelo (modelo_rvc, pitch_rvc…) se gestionan en el JSON de la voz, tal y
como documenta el README.
"""
from __future__ import annotations

import logging
from dataclasses import fields
from uuid import uuid4

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.domain.catalogo import CatalogoParametros, DefParametro
from app.domain.models import (
    ParametrosDSP,
    PerfilDSP,
    PerfilIA,
    TIPO_IA,
)
from app.engine.gestor_voces import GestorVoces

log = logging.getLogger(__name__)

ICONOS_SUGERIDOS = ("👺", "🐉", "🍺", "🧙", "🧌", "🤖", "👑", "💀", "🐺", "🦇")


class PestanaEditor(QWidget):
    senal_probar = pyqtSignal(object)        # ParametrosDSP (preview 2 s)
    senal_voces_cambiadas = pyqtSignal(str)  # mensaje tras guardar/eliminar

    def __init__(self, gestor: GestorVoces, catalogo: CatalogoParametros):
        super().__init__()
        self._gestor = gestor
        self._catalogo = catalogo
        self._voz_editada: PerfilDSP | PerfilIA | None = None
        self._cargando = False  # evita rebotes slider ↔ spinbox
        self._controles: dict[str, tuple[QSlider, QDoubleSpinBox]] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(10)

        # ---- Fila superior: selección de voz + acciones ----
        fila_superior = QHBoxLayout()
        self.combo_voz = QComboBox()
        self.combo_voz.setMinimumHeight(34)
        self.combo_voz.currentIndexChanged.connect(self._voz_combo_cambiada)
        boton_nueva = QPushButton("➕ Nueva")
        boton_nueva.clicked.connect(self._nueva_voz)
        boton_duplicar = QPushButton("📋 Duplicar")
        boton_duplicar.clicked.connect(self._duplicar_voz)
        boton_eliminar = QPushButton("🗑️ Eliminar")
        boton_eliminar.clicked.connect(self._eliminar_voz)
        fila_superior.addWidget(QLabel("Editar voz:"))
        fila_superior.addWidget(self.combo_voz, 1)
        fila_superior.addWidget(boton_nueva)
        fila_superior.addWidget(boton_duplicar)
        fila_superior.addWidget(boton_eliminar)
        raiz.addLayout(fila_superior)

        self.etiqueta_tipo = QLabel("")
        raiz.addWidget(self.etiqueta_tipo)

        # ---- Sliders generados desde el catálogo (scroll) ----
        contenedor = QWidget()
        self._form = QFormLayout(contenedor)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setSpacing(8)
        self._construir_sliders()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenedor)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        raiz.addWidget(scroll, 1)

        # ---- Acciones inferiores ----
        fila_inferior = QGridLayout()
        boton_probar = QPushButton("▶ Probar (2 s)")
        boton_probar.setMinimumHeight(44)
        boton_probar.setStyleSheet("font-weight:700;")
        boton_probar.clicked.connect(self._probar)
        boton_guardar = QPushButton("💾 Guardar cambios")
        boton_guardar.setMinimumHeight(44)
        boton_guardar.clicked.connect(self._guardar)
        boton_como_nueva = QPushButton("💾 Guardar como nueva voz…")
        boton_como_nueva.setMinimumHeight(44)
        boton_como_nueva.clicked.connect(self._guardar_como_nueva)
        fila_inferior.addWidget(boton_probar, 0, 0)
        fila_inferior.addWidget(boton_guardar, 0, 1)
        fila_inferior.addWidget(boton_como_nueva, 0, 2)
        raiz.addLayout(fila_inferior)

    # ----------------------- construcción de sliders ---------------------- #
    def _construir_sliders(self) -> None:
        for dparam in self._catalogo.todos():
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(round(dparam.minimo / dparam.paso)),
                            int(round(dparam.maximo / dparam.paso)))

            spin = QDoubleSpinBox()
            spin.setRange(dparam.minimo, dparam.maximo)
            spin.setSingleStep(dparam.paso)
            spin.setDecimals(self._decimales(dparam.paso))
            spin.setSuffix(f" {dparam.unidad}" if dparam.unidad else "")
            spin.setMinimumWidth(110)

            # Slider (unidades de paso) → SpinBox (valor real)
            slider.valueChanged.connect(
                lambda v, d=dparam, sp=spin: self._slider_a_spin(v, d, sp))
            # SpinBox → Slider
            spin.valueChanged.connect(
                lambda v, d=dparam, sl=slider: self._spin_a_slider(v, d, sl))

            etiqueta = QLabel(dparam.etiqueta)
            self._form.addRow(etiqueta, slider)
            self._form.addRow("", spin)
            self._controles[dparam.clave] = (slider, spin)

    @staticmethod
    def _decimales(paso: float) -> int:
        decimales = 0
        p = paso
        while p < 0.999 and decimales < 4:
            p *= 10
            decimales += 1
        return decimales

    def _slider_a_spin(self, valor: int, d: DefParametro, spin: QDoubleSpinBox) -> None:
        if self._cargando:
            return
        self._cargando = True
        spin.setValue(d.minimo + valor * d.paso)
        self._cargando = False

    def _spin_a_slider(self, valor: float, d: DefParametro, slider: QSlider) -> None:
        if self._cargando:
            return
        self._cargando = True
        slider.setValue(int(round((valor - d.minimo) / d.paso)))
        self._cargando = False

    # ------------------------------ API ----------------------------------- #
    def refrescar(self, id_seleccionado: str | None = None) -> None:
        """Repuebla el combo tras guardar/eliminar/recargar voces."""
        self._cargando = True
        self.combo_voz.clear()
        for voz in self._gestor.todas():
            self.combo_voz.addItem(f"{voz.icono} {voz.nombre}", str(voz.id))
        indice = self.combo_voz.findData(id_seleccionado) if id_seleccionado else -1
        if indice >= 0:
            self.combo_voz.setCurrentIndex(indice)
        elif self.combo_voz.count() > 0:
            self.combo_voz.setCurrentIndex(0)
        self._cargando = False
        self._cargar_voz_actual()

    # --------------------------- slots internos ---------------------------- #
    def _voz_combo_cambiada(self, indice: int) -> None:
        if not self._cargando:
            self._cargar_voz_actual()

    def _cargar_voz_actual(self) -> None:
        id_voz = self.combo_voz.currentData()
        self._voz_editada = self._gestor.por_id(id_voz) if id_voz else None
        if self._voz_editada is None:
            self.etiqueta_tipo.setText("")
            return
        self._cargando = True
        if isinstance(self._voz_editada, PerfilIA):
            self.etiqueta_tipo.setText(
                "Modo IA: se edita la cadena DSP post-proceso. El modelo RVC, "
                "pitch_rvc e index_rate se configuran en el JSON de la voz.")
            params = self._voz_editada.dsp_post
        else:
            self.etiqueta_tipo.setText("Voz DSP: ajusta los sliders y prueba al instante.")
            params = self._voz_editada.parametros_dsp
        for f in fields(ParametrosDSP):
            par = self._controles.get(f.name)
            if par is not None:
                dparam = self._catalogo.def_de(f.name)
                valor = float(getattr(params, f.name))
                par[1].setValue(valor)                                   # spin
                par[0].setValue(int(round((valor - dparam.minimo) / dparam.paso)))  # slider
        self._cargando = False

    def _parametros_actuales(self) -> ParametrosDSP:
        valores = {}
        for f in fields(ParametrosDSP):
            par = self._controles.get(f.name)
            valores[f.name] = par[1].value() if par is not None else 0.0
        return ParametrosDSP(**valores)

    # ------------------------------ acciones ------------------------------- #
    def _probar(self) -> None:
        self.senal_probar.emit(self._parametros_actuales())

    def _guardar(self) -> None:
        if self._voz_editada is None:
            return
        try:
            if isinstance(self._voz_editada, PerfilIA):
                self._voz_editada.dsp_post = self._parametros_actuales()
            else:
                self._voz_editada.parametros_dsp = self._parametros_actuales()
            ruta = self._gestor.guardar(self._voz_editada)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return
        self.senal_voces_cambiadas.emit(f"Voz guardada en {ruta.name}")

    def _guardar_como_nueva(self, nombre_inicial: str = "") -> None:
        texto_inicial = nombre_inicial
        if not texto_inicial and self._voz_editada is not None:
            texto_inicial = self._voz_editada.nombre
        nombre, ok = QInputDialog.getText(
            self, "Nueva voz", "Nombre de la voz:", text=texto_inicial)
        if not ok or not nombre.strip():
            return
        color = "#5a7a3b"
        if self._voz_editada is not None:
            color = self._voz_editada.color
        from PyQt6.QtWidgets import QColorDialog  # import local (diálogo modal)
        color_elegido = QColorDialog.getColor(
            self._hex_a_qcolor(color), self, "Color del botón")
        if color_elegido.isValid():
            color = color_elegido.name()

        perfil = PerfilDSP(
            id=uuid4(),
            nombre=nombre.strip(),
            icono=self._elegir_icono(),
            color=color,
            parametros_dsp=self._parametros_actuales(),
        )
        try:
            ruta = self._gestor.guardar(perfil)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo crear la voz", str(exc))
            return
        self.refrescar(str(perfil.id))
        self.senal_voces_cambiadas.emit(f"Voz «{perfil.nombre}» creada en {ruta.name}")

    def _duplicar_voz(self) -> None:
        if self._voz_editada is None:
            return
        self._guardar_como_nueva(nombre_inicial=f"{self._voz_editada.nombre} (copia)")

    def _nueva_voz(self) -> None:
        self._guardar_como_nueva(nombre_inicial="")

    def _eliminar_voz(self) -> None:
        if self._voz_editada is None:
            return
        from app.engine.gestor_voces import GestorVoces as _G
        if self._voz_editada.id == _G.ID_NEUTRA:
            QMessageBox.information(self, "Voz Neutral",
                                    "La voz Neutral no se puede eliminar: es el "
                                    "modo seguro del sistema.")
            return
        respuesta = QMessageBox.question(
            self, "Eliminar voz",
            f"¿Eliminar «{self._voz_editada.nombre}» y su JSON?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        if self._gestor.eliminar(self._voz_editada.id):
            self.refrescar()
            self.senal_voces_cambiadas.emit("Voz eliminada.")

    def _elegir_icono(self) -> str:
        iconos, ok = QInputDialog.getItem(
            self, "Icono de la voz", "Elige un icono:",
            list(ICONOS_SUGERIDOS), 0, False)
        return iconos if ok and iconos else "🎙️"

    @staticmethod
    def _hex_a_qcolor(hex_color: str):
        from PyQt6.QtGui import QColor
        return QColor(hex_color)
