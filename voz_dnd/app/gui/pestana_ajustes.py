"""Pestaña "⚙️ Ajustes" (Fase 5.4): buffer, dispositivos, carpeta MP3, atajos.

Todos los cambios se aplican al pulsar "💾 Guardar ajustes", que emite
`senal_config_actualizada(ConfigApp)`; la ventana principal persiste el JSON,
reinicia el stream de audio si hace falta y reconstruye los atajos.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtGui import QKeySequence
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    BUFFERS_VALIDOS,
    ConfigApp,
    ConfigAudio,
    ConfigGrabacion,
    ConfigMotor,
)
from app.domain.models import IVoiceProfile
from app.engine.modulo_ia import ModuloIA

log = logging.getLogger(__name__)

MUESTREOS = (44100, 48000)
BITRATES_KBPS = (128, 192, 320)
OVERHEAD_DRIVER_MS = 8.0


class PestanaAjustes(QWidget):
    senal_config_actualizada = pyqtSignal(object)  # ConfigApp

    def __init__(self, cfg: ConfigApp, voces: list[IVoiceProfile]):
        super().__init__()
        self._cfg = cfg
        self._voces = voces
        self._editores_atajo: dict[str, QKeySequenceEdit] = {}  # id → editor
        self._form_atajos: QFormLayout | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(12)

        # ------------------------- Audio ------------------------- #
        grupo_audio = QGroupBox("🎙️ Audio (latencia)")
        form_audio = QFormLayout(grupo_audio)

        self.combo_buffer = QComboBox()
        for b in BUFFERS_VALIDOS:
            self.combo_buffer.addItem(f"{b} muestras", b)
        self.combo_buffer.setCurrentIndex(
            list(BUFFERS_VALIDOS).index(cfg.audio.buffer_size))
        self.combo_buffer.currentIndexChanged.connect(self._refrescar_latencia)
        form_audio.addRow("Tamaño de buffer:", self.combo_buffer)

        self.combo_sr = QComboBox()
        for sr in MUESTREOS:
            self.combo_sr.addItem(f"{sr} Hz", sr)
        self.combo_sr.setCurrentIndex(list(MUESTREOS).index(cfg.audio.sample_rate))
        self.combo_sr.currentIndexChanged.connect(self._refrescar_latencia)
        form_audio.addRow("Frecuencia de muestreo:", self.combo_sr)

        self.combo_entrada = QComboBox()
        self.combo_salida = QComboBox()
        self._poblar_dispositivos()
        form_audio.addRow("Micrófono:", self.combo_entrada)
        form_audio.addRow("Salida:", self.combo_salida)

        self.etiqueta_latencia = QLabel("")
        form_audio.addRow("Latencia estimada:", self.etiqueta_latencia)
        self._refrescar_latencia()
        raiz.addWidget(grupo_audio)

        # ------------------------ Grabación ---------------------- #
        grupo_grab = QGroupBox("💾 Grabación (MP3)")
        form_grab = QFormLayout(grupo_grab)

        fila_carpeta = QHBoxLayout()
        self.edit_carpeta = QLineEdit(cfg.grabacion.carpeta_destino)
        self.edit_carpeta.setPlaceholderText(
            str(Path.home() / "Music" / "SesionesDnD"))
        boton_carpeta = QPushButton("Examinar…")
        boton_carpeta.clicked.connect(self._elegir_carpeta)
        fila_carpeta.addWidget(self.edit_carpeta)
        fila_carpeta.addWidget(boton_carpeta)
        form_grab.addRow("Carpeta destino:", fila_carpeta)

        self.combo_bitrate = QComboBox()
        for kbps in BITRATES_KBPS:
            self.combo_bitrate.addItem(f"{kbps} kbps", kbps)
        if cfg.grabacion.bitrate_kbps in BITRATES_KBPS:
            self.combo_bitrate.setCurrentIndex(
                list(BITRATES_KBPS).index(cfg.grabacion.bitrate_kbps))
        form_grab.addRow("Calidad MP3:", self.combo_bitrate)

        fila_ffmpeg = QHBoxLayout()
        self.edit_ffmpeg = QLineEdit(cfg.motor.ffmpeg_ruta)
        self.edit_ffmpeg.setPlaceholderText("(dejar vacío si ffmpeg está en el PATH)")
        boton_ffmpeg = QPushButton("Examinar…")
        boton_ffmpeg.clicked.connect(self._elegir_ffmpeg)
        fila_ffmpeg.addWidget(self.edit_ffmpeg)
        fila_ffmpeg.addWidget(boton_ffmpeg)
        form_grab.addRow("Ruta de ffmpeg:", fila_ffmpeg)
        raiz.addWidget(grupo_grab)

        # -------------------------- Motor IA ---------------------- #
        grupo_ia = QGroupBox("🧠 Modo avanzado (IA)")
        form_ia = QFormLayout(grupo_ia)
        self.check_ia = QCheckBox("Permitir voces IA (clonación RVC)")
        self.check_ia.setChecked(cfg.motor.permitir_ia)
        form_ia.addRow(self.check_ia)
        con_gpu, detalle = ModuloIA.estado_gpu()
        self.etiqueta_gpu = QLabel(("✔ " if con_gpu else "✖ ") + detalle)
        self.etiqueta_gpu.setStyleSheet(
            "color:#7fb069;" if con_gpu else "color:#d8b13c;")
        form_ia.addRow("GPU:", self.etiqueta_gpu)
        raiz.addWidget(grupo_ia)

        # -------------------------- Atajos ------------------------- #
        grupo_atajos = QGroupBox("⌨️ Atajos de teclado (F1…F12 recomendado)")
        self._form_atajos = QFormLayout(grupo_atajos)
        self._construir_atajos(self._form_atajos)
        raiz.addWidget(grupo_atajos)

        raiz.addStretch(1)

        boton_guardar = QPushButton("💾 Guardar ajustes")
        boton_guardar.setMinimumHeight(44)
        boton_guardar.setStyleSheet("font-weight:700;")
        boton_guardar.clicked.connect(self._guardar)
        raiz.addWidget(boton_guardar)

    # --------------------------- dispositivos ------------------------------ #
    def _poblar_dispositivos(self) -> None:
        try:
            import sounddevice as sd
            dispositivos = sd.query_devices()
        except Exception as exc:  # noqa: BLE001 — sin PortAudio en el sistema
            log.warning("No se pudieron listar dispositivos de audio: %s", exc)
            self.combo_entrada.addItem("(dispositivo por defecto)", None)
            self.combo_salida.addItem("(dispositivo por defecto)", None)
            return

        self.combo_entrada.addItem("(dispositivo por defecto)", None)
        self.combo_salida.addItem("(dispositivo por defecto)", None)
        for i, d in enumerate(dispositivos):
            nombre = (f"{d['name']} "
                      f"({d['max_input_channels']}in/{d['max_output_channels']}out)")
            if d["max_input_channels"] > 0:
                self.combo_entrada.addItem(f"🎤 {nombre}", i)
            if d["max_output_channels"] > 0:
                self.combo_salida.addItem(f"🔊 {nombre}", i)

        # Selección guardada en config.json
        idx_e = self.combo_entrada.findData(self._cfg.audio.dispositivo_entrada)
        idx_s = self.combo_salida.findData(self._cfg.audio.dispositivo_salida)
        if idx_e >= 0:
            self.combo_entrada.setCurrentIndex(idx_e)
        if idx_s >= 0:
            self.combo_salida.setCurrentIndex(idx_s)

    def _elegir_carpeta(self) -> None:
        ruta = QFileDialog.getExistingDirectory(
            self, "Carpeta de grabaciones", self.edit_carpeta.text() or "")
        if ruta:
            self.edit_carpeta.setText(ruta)

    def _elegir_ffmpeg(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Ejecutable de ffmpeg (ffmpeg.exe)")
        if ruta:
            self.edit_ffmpeg.setText(ruta)

    # ------------------------------ atajos ---------------------------------- #
    def _construir_atajos(self, form: QFormLayout) -> None:
        tecla_por_id = {str(id_voz): tecla
                        for tecla, id_voz in self._cfg.atajos.items()}
        for voz in self._voces:
            editor = QKeySequenceEdit()
            tecla = tecla_por_id.get(str(voz.id))
            if tecla:
                editor.setKeySequence(QKeySequence(tecla))
            form.addRow(f"{voz.icono} {voz.nombre}:", editor)
            self._editores_atajo[str(voz.id)] = editor

    def refrescar_atajos(self, voces: list[IVoiceProfile],
                         atajos: dict[str, str]) -> None:
        """Reconstruye la tabla de atajos tras crear/eliminar/recargar voces."""
        self._voces = voces
        self._cfg.atajos = dict(atajos)
        for editor in list(self._editores_atajo.values()):
            editor.setParent(None)
            editor.deleteLater()
        self._editores_atajo.clear()
        if self._form_atajos is not None:
            self._construir_atajos(self._form_atajos)

    # ------------------------------ guardar --------------------------------- #
    def _refrescar_latencia(self) -> None:
        buffer = self.combo_buffer.currentData() or 256
        sr = self.combo_sr.currentData() or 48000
        base = 2.0 * buffer / sr * 1000.0
        self.etiqueta_latencia.setText(
            f"≈ {base + OVERHEAD_DRIVER_MS:.0f} ms (sin contar efectos DSP)")

    def _guardar(self) -> None:
        cfg = ConfigApp(
            audio=ConfigAudio(
                sample_rate=self.combo_sr.currentData() or 48000,
                buffer_size=self.combo_buffer.currentData() or 256,
                dispositivo_entrada=self.combo_entrada.currentData(),
                dispositivo_salida=self.combo_salida.currentData(),
            ),
            grabacion=ConfigGrabacion(
                carpeta_destino=self.edit_carpeta.text().strip(),
                formato="mp3",
                bitrate_kbps=self.combo_bitrate.currentData() or 192,
                patron_nombre=self._cfg.grabacion.patron_nombre,
            ),
            motor=ConfigMotor(
                modo=self._cfg.motor.modo,
                permitir_ia=self.check_ia.isChecked(),
                tam_grano_pitch=self._cfg.motor.tam_grano_pitch,
                ffmpeg_ruta=self.edit_ffmpeg.text().strip(),
            ),
            ui=self._cfg.ui,
        )
        atajos: dict[str, str] = {}
        for id_voz, editor in self._editores_atajo.items():
            secuencia = editor.keySequence().toString()
            if secuencia:
                atajos[secuencia] = id_voz
        cfg.atajos = atajos
        self.senal_config_actualizada.emit(cfg)
