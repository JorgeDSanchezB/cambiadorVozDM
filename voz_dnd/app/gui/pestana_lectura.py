"""Pestaña "📖 Leer" (Fase 6): leer un archivo de texto con la voz elegida.

El usuario elige un archivo de texto (o escribe/pega texto), selecciona la
voz neural de edge-tts y pulsa "▶ Leer". La ventana principal construye el
procesador de la voz ACTIVA y lanza la lectura en un hilo de trabajo; aquí
solo se recogen entradas y se muestra el estado del render.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.engine.lector_texto import VOCES_TTS_SUGERIDAS, VOZ_TTS_POR_DEFECTO
from app.gui.tema import CLARO, Tema


class PestanaLectura(QWidget):
    senal_leer = pyqtSignal(str)      # texto a leer
    senal_detener = pyqtSignal()      # detiene la reproducción
    senal_voz_tts = pyqtSignal(str)   # voz neural edge-tts elegida

    def __init__(self, tema: Tema | None = None):
        super().__init__()
        self._tema = tema or CLARO
        self._ruta_archivo: Path | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(8)

        # ---- Fila de archivo ----
        fila_archivo = QHBoxLayout()
        self.edit_ruta = QLineEdit()
        self.edit_ruta.setPlaceholderText("Selecciona un archivo de texto…")
        boton_examinar = QPushButton("📂 Examinar…")
        boton_examinar.clicked.connect(self._examinar)
        fila_archivo.addWidget(self.edit_ruta, 1)
        fila_archivo.addWidget(boton_examinar)
        raiz.addLayout(fila_archivo)

        # ---- Área de texto ----
        self.texto = QPlainTextEdit()
        self.texto.setPlaceholderText(
            "Escribe o pega aquí el texto que quieres que se lea\n"
            "con la voz seleccionada (o elige un archivo arriba).")
        raiz.addWidget(self.texto, 1)

        # ---- Fila de parámetros ----
        fila_params = QHBoxLayout()
        fila_params.addWidget(QLabel("Voz neural:"))
        self.combo_voz = QComboBox()
        for v in VOCES_TTS_SUGERIDAS:
            self.combo_voz.addItem(v, v)
        idx = self.combo_voz.findData(VOZ_TTS_POR_DEFECTO)
        if idx >= 0:
            self.combo_voz.setCurrentIndex(idx)
        self.combo_voz.currentIndexChanged.connect(self._emitir_voz)
        fila_params.addWidget(self.combo_voz)
        fila_params.addStretch(1)
        self.check_wav = QCheckBox("Guardar también en WAV")
        self.check_wav.setChecked(True)
        fila_params.addWidget(self.check_wav)
        raiz.addLayout(fila_params)

        # ---- Estado y acciones ----
        self.etiqueta_estado = QLabel("Listo. Elige un archivo y pulsa ▶ Leer.")
        self.etiqueta_estado.setWordWrap(True)
        self.etiqueta_estado.setStyleSheet(f"color:{self._tema.muted};")
        raiz.addWidget(self.etiqueta_estado)

        fila_botones = QHBoxLayout()
        self.boton_leer = QPushButton("▶ Leer")
        self.boton_leer.setMinimumHeight(44)
        self.boton_leer.setStyleSheet("font-weight:700;")
        self.boton_leer.clicked.connect(self._leer)
        self.boton_detener = QPushButton("⏹ Detener")
        self.boton_detener.setMinimumHeight(44)
        self.boton_detener.setEnabled(False)
        self.boton_detener.clicked.connect(self.senal_detener.emit)
        fila_botones.addWidget(self.boton_leer, 1)
        fila_botones.addWidget(self.boton_detener, 1)
        raiz.addLayout(fila_botones)

    # ------------------------------ API ---------------------------------- #
    def set_estado(self, texto: str) -> None:
        self.etiqueta_estado.setText(texto)

    def set_tema(self, tema: Tema) -> None:
        self._tema = tema
        self.etiqueta_estado.setStyleSheet(f"color:{tema.muted};")

    def set_leyendo(self, activo: bool) -> None:
        """Habilita/inhabilita los controles mientras se lee."""
        self.boton_leer.setEnabled(not activo)
        self.boton_detener.setEnabled(activo)
        self.edit_ruta.setEnabled(not activo)
        self.texto.setReadOnly(activo)
        self.combo_voz.setEnabled(not activo)

    # --------------------------- internos -------------------------------- #
    def _examinar(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Archivo de texto",
            str(self._ruta_archivo.parent if self._ruta_archivo else ""),
            "Textos (*.txt *.md *.rtf);;Todos (*.*)")
        if not ruta:
            return
        self._ruta_archivo = Path(ruta)
        self.edit_ruta.setText(ruta)
        try:
            contenido = ruta.read_text(encoding="utf-8", errors="replace")
            self.texto.setPlainText(contenido)
            self.set_estado(f"Archivo cargado: {self._ruta_archivo.name} "
                            f"({len(contenido.split())} palabras).")
        except OSError as exc:
            self.set_estado(f"No se pudo leer el archivo: {exc}")

    def _leer(self) -> None:
        texto = self.texto.toPlainText().strip()
        if not texto:
            self.set_estado("El texto está vacío. Escribe algo o elige un archivo.")
            return
        self.senal_leer.emit(texto)

    def _emitir_voz(self) -> None:
        self.senal_voz_tts.emit(self.combo_voz.currentData() or VOZ_TTS_POR_DEFECTO)
