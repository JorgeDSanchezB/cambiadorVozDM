"""Pestaña 🎚️ Editor: sliders data-driven + prueba instantánea + CRUD de voces.

Cero hardcoding: los sliders se GENERAN desde data/parametros.json (mismo
catálogo que usa la Fábrica de cadenas). Añadir un parámetro nuevo al
catálogo = aparece en el editor sin tocar código.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from dominio.entidades import (
    IVoiceProfile,
    ParametrosDSP,
    PerfilDSP,
    PerfilIA,
)


class PestanaEditor(QWidget):
    ICONOS = ["🎙️", "👺", "🐉", "🍺", "🤖", "👻", "🧙", "🧟", "🧚", "🐺", "🦇", "👑"]

    def __init__(self, motor, gestor_voces, catalogo, al_cambiar_voces: Callable, padre=None):
        super().__init__(padre)
        self.motor = motor
        self.gestor_voces = gestor_voces
        self.catalogo = catalogo
        self.al_cambiar_voces = al_cambiar_voces  # callback → refrescar pestaña Voces
        self._voz_editada: IVoiceProfile | None = None
        self._controles: dict[str, tuple[QSlider, QDoubleSpinBox]] = {}

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        # --- Selección de voz a editar ------------------------------------- #
        fila_selector = QHBoxLayout()
        fila_selector.addWidget(QLabel("Editar voz:"))
        self.combo = QComboBox()
        self.combo.setMinimumHeight(38)
        self.combo.currentIndexChanged.connect(self._cargar_voz)
        fila_selector.addWidget(self.combo, 1)
        boton_nueva = QPushButton("➕ Nueva desde cero")
        boton_nueva.clicked.connect(self._nueva_voz)
        fila_selector.addWidget(boton_nueva)
        raiz.addLayout(fila_selector)

        # --- Sliders generados desde el catálogo --------------------------- #
        grupo = QGroupBox("Parámetros DSP")
        self.formulario = QFormLayout(grupo)
        self.formulario.setSpacing(8)
        for nombre, rango in catalogo.items():
            slider, spin = self._crear_control(nombre, rango)
            self._controles[nombre] = (slider, spin)
            self.formulario.addRow(QLabel(rango["etiqueta"]), self._fila_control(slider, spin))
        raiz.addWidget(grupo, 1)

        # --- Acciones ------------------------------------------------------- #
        fila_acciones = QHBoxLayout()
        boton_probar = QPushButton("▶ Probar (en vivo)")
        boton_probar.setMinimumHeight(46)
        boton_probar.setStyleSheet("background:#16a34a;color:white;font-weight:700;border-radius:8px;")
        boton_probar.clicked.connect(self._probar)
        boton_guardar = QPushButton("💾 Guardar cambios")
        boton_guardar.setMinimumHeight(46)
        boton_guardar.clicked.connect(self._guardar_cambios)
        boton_como_nueva = QPushButton("📤 Guardar como NUEVA voz")
        boton_como_nueva.setMinimumHeight(46)
        boton_como_nueva.clicked.connect(self._guardar_como_nueva)
        boton_duplicar = QPushButton("📋 Duplicar")
        boton_duplicar.setMinimumHeight(46)
        boton_duplicar.clicked.connect(self._duplicar)
        boton_eliminar = QPushButton("🗑️ Eliminar")
        boton_eliminar.setMinimumHeight(46)
        boton_eliminar.clicked.connect(self._eliminar)
        for boton in (boton_probar, boton_guardar, boton_como_nueva, boton_duplicar, boton_eliminar):
            fila_acciones.addWidget(boton)
        raiz.addLayout(fila_acciones)

    # ------------------------------------------------------------------ #
    #  Construcción de controles
    # ------------------------------------------------------------------ #
    @staticmethod
    def _fila_control(slider: QSlider, spin: QDoubleSpinBox) -> QWidget:
        fila = QWidget()
        disposicion = QHBoxLayout(fila)
        disposicion.setContentsMargins(0, 0, 0, 0)
        disposicion.addWidget(slider, 1)
        disposicion.addWidget(spin)
        return fila

    def _crear_control(self, nombre: str, rango: dict) -> tuple[QSlider, QDoubleSpinBox]:
        minimo, maximo, paso = float(rango["min"]), float(rango["max"]), float(rango["paso"])
        pasos = max(1, int(round((maximo - minimo) / paso)))

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, pasos)

        spin = QDoubleSpinBox()
        spin.setRange(minimo, maximo)
        spin.setSingleStep(paso)
        spin.setDecimals(2)
        spin.setMinimumWidth(90)

        def al_mover_slider(valor: int) -> None:
            spin.blockSignals(True)
            spin.setValue(minimo + valor * paso)
            spin.blockSignals(False)

        def al_escribir_spin(valor: float) -> None:
            slider.blockSignals(True)
            slider.setValue(int(round((valor - minimo) / paso)))
            slider.blockSignals(False)

        slider.valueChanged.connect(al_mover_slider)
        spin.valueChanged.connect(al_escribir_spin)
        return slider, spin

    def _valores_actuales(self) -> ParametrosDSP:
        datos = {nombre: spin.value() for nombre, (_, spin) in self._controles.items()}
        return ParametrosDSP.desde_dict(datos)

    def _poner_valores(self, parametros: ParametrosDSP) -> None:
        for nombre, (slider, spin) in self._controles.items():
            valor = float(getattr(parametros, nombre))
            spin.setValue(valor)
            slider.setValue(int(round((valor - float(spin.minimum())) / float(spin.singleStep()))))

    # ------------------------------------------------------------------ #
    #  Acciones
    # ------------------------------------------------------------------ #
    def poblar(self, voces) -> None:
        actual = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for voz in voces:
            self.combo.addItem(f"{voz.icono} {voz.nombre}", userData=voz.id)
        if actual:
            indice = self.combo.findData(actual)
            self.combo.setCurrentIndex(max(0, indice))
        self.combo.blockSignals(False)
        self._cargar_voz(self.combo.currentIndex())

    def _cargar_voz(self, indice: int) -> None:
        id_voz = self.combo.itemData(indice)
        self._voz_editada = self.gestor_voces.buscar_por_id(id_voz) if id_voz else None
        if self._voz_editada is None:
            self._poner_valores(ParametrosDSP())
            return
        if isinstance(self._voz_editada, PerfilDSP):
            self._poner_valores(self._voz_editada.parametros_dsp)
        else:  # PerfilIA → se edita la cadena DSP-post
            self._poner_valores(self._voz_editada.dsp_post)

    def _probar(self) -> None:
        """Aplica la cadena temporal en vivo SIN guardar nada."""
        self.motor.probar_cadena_temporal(self._valores_actuales())

    def _restaurar_voz(self) -> None:
        self.motor.restaurar_voz_activa()

    def _guardar_cambios(self) -> None:
        if self._voz_editada is None:
            QMessageBox.information(self, "Editor", "Selecciona una voz primero.")
            return
        if isinstance(self._voz_editada, PerfilDSP):
            self._voz_editada.parametros_dsp = self._valores_actuales()
        elif isinstance(self._voz_editada, PerfilIA):
            self._voz_editada.dsp_post = self._valores_actuales()
        try:
            self.gestor_voces.guardar(self._voz_editada)
        except ValueError as exc:
            QMessageBox.warning(self, "Parámetros inválidos", str(exc))
            return
        self.motor.restaurar_voz_activa()
        self.al_cambiar_voces()

    def _guardar_como_nueva(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Nueva voz", "Nombre de la voz:")
        if not ok or not nombre.strip():
            return
        icono, ok2 = QInputDialog.getItem(
            self, "Icono", "Elige un icono:", self.ICONOS, 0, False
        )
        color = "#4b5563"
        color_elegido = QColorDialog.getColor(parent=self, title="Color del botón")
        if color_elegido.isValid():
            color = color_elegido.name()
        perfil = PerfilDSP(
            id=self.gestor_voces._nuevo_id(),
            nombre=nombre.strip(),
            tipo="DSP",
            icono=icono,
            color=color,
            parametros_dsp=self._valores_actuales(),
        )
        try:
            self.gestor_voces.guardar(perfil)
        except ValueError as exc:
            QMessageBox.warning(self, "Parámetros inválidos", str(exc))
            return
        self.al_cambiar_voces()
        QMessageBox.information(
            self, "Voz creada", f"La voz '{perfil.nombre}' ya está disponible."
        )

    def _nueva_voz(self) -> None:
        self._poner_valores(ParametrosDSP())
        self._guardar_como_nueva()

    def _duplicar(self) -> None:
        if self._voz_editada is None:
            return
        nombre, ok = QInputDialog.getText(
            self, "Duplicar voz",
            f"Copia de '{self._voz_editada.nombre}' se llamará:",
            text=f"{self._voz_editada.nombre} (copia)",
        )
        if not ok or not nombre.strip():
            return
        try:
            self.gestor_voces.duplicar(self._voz_editada.id, nombre.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self.al_cambiar_voces()

    def _eliminar(self) -> None:
        if self._voz_editada is None:
            return
        if self._voz_editada.id == IVoiceProfile.ID_NEUTRAL:
            QMessageBox.warning(self, "Protegida", "La voz Neutral no se puede eliminar.")
            return
        respuesta = QMessageBox.question(
            self, "Eliminar voz",
            f"¿Eliminar '{self._voz_editada.nombre}' permanentemente?",
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.gestor_voces.eliminar(self._voz_editada.id)
            self.al_cambiar_voces()
