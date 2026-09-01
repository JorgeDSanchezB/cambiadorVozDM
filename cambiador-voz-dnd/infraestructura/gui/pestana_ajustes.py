"""Pestaña ⚙️ Ajustes: buffer/latencia, dispositivos, carpeta MP3, atajos, GPU."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import (
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
from PyQt6.QtGui import QKeySequence

from aplicacion.motor_audio import TAMANIOS_BUFFER_VALIDOS


class PestanaAjustes(QWidget):
    def __init__(self, motor, config, gestor_voces, repo_config,
                 al_aplicar_config: Callable, padre=None):
        super().__init__(padre)
        self.motor = motor
        self.config = config
        self.gestor_voces = gestor_voces
        self.repo_config = repo_config
        self.al_aplicar_config = al_aplicar_config  # callback → rehacer atajos/recargar

        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        # --- Audio / latencia ---------------------------------------------- #
        grupo_audio = QGroupBox("Audio y latencia")
        forma_audio = QFormLayout(grupo_audio)
        self.combo_buffer = QComboBox()
        for tamanio in TAMANIOS_BUFFER_VALIDOS:
            latencia = 2.0 * tamanio / motor.sr * 1000.0 + 8.0
            self.combo_buffer.addItem(f"{tamanio} muestras (≈ {latencia:.0f} ms)", tamanio)
        indice = list(TAMANIOS_BUFFER_VALIDOS).index(
            int(config["audio"]["buffer_size"])
        ) if int(config["audio"]["buffer_size"]) in TAMANIOS_BUFFER_VALIDOS else 1
        self.combo_buffer.setCurrentIndex(indice)
        forma_audio.addRow("Tamaño de buffer (menor = menos latencia):", self.combo_buffer)

        self.combo_entrada = QComboBox()
        self.combo_salida = QComboBox()
        self._poblar_dispositivos()
        forma_audio.addRow("Micrófono (entrada):", self.combo_entrada)
        forma_audio.addRow("Altavoces (salida):", self.combo_salida)
        raiz.addWidget(grupo_audio)

        # --- Grabación ------------------------------------------------------ #
        grupo_grab = QGroupBox("Grabación MP3")
        forma_grab = QFormLayout(grupo_grab)
        fila_carpeta = QHBoxLayout()
        self.campo_carpeta = QLineEdit(config["grabacion"]["carpeta_destino"])
        boton_carpeta = QPushButton("📁 Examinar…")
        boton_carpeta.clicked.connect(self._elegir_carpeta)
        fila_carpeta.addWidget(self.campo_carpeta, 1)
        fila_carpeta.addWidget(boton_carpeta)
        forma_grab.addRow("Carpeta de destino:", fila_carpeta)
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["128", "192", "256", "320"])
        self.combo_bitrate.setCurrentText(str(config["grabacion"]["bitrate_kbps"]))
        forma_grab.addRow("Bitrate MP3 (kbps):", self.combo_bitrate)
        from aplicacion.gestor_grabacion import comprobar_ffmpeg
        estado_ff = "✔ ffmpeg detectado (MP3 listo)" if comprobar_ffmpeg() \
            else "✖ ffmpeg NO detectado: se exportará WAV"
        etiqueta_ff = QLabel(estado_ff)
        etiqueta_ff.setStyleSheet("font-weight:700;")
        forma_grab.addRow("", etiqueta_ff)
        raiz.addWidget(grupo_grab)

        # --- Atajos de teclado ---------------------------------------------- #
        grupo_atajos = QGroupBox("Atajos de teclado (F1–F12 recomendados)")
        self.forma_atajos = QFormLayout(grupo_atajos)
        self.editores_atajo: dict[str, QKeySequenceEdit] = {}
        for voz in gestor_voces.voces:
            editor = QKeySequenceEdit(QKeySequence(voz.atajo or ""))
            editor.setMaximumSequenceLength(1)
            self.forma_atajos.addRow(f"{voz.icono} {voz.nombre}", editor)
            self.editores_atajo[voz.id] = editor
        raiz.addWidget(grupo_atajos)

        # --- Modo IA / GPU --------------------------------------------------- #
        grupo_ia = QGroupBox("Modo Avanzado (IA · RVC)")
        forma_ia = QFormLayout(grupo_ia)
        self.check_ia = QComboBox()
        self.check_ia.addItem("Habilitado", True)
        self.check_ia.addItem("Deshabilitado (solo DSP)", False)
        self.check_ia.setCurrentIndex(0 if config["motor"].get("permitir_ia", True) else 1)
        forma_ia.addRow("Clonación de voz:", self.check_ia)
        etiqueta_gpu = QLabel(self._estado_gpu())
        etiqueta_gpu.setStyleSheet("font-weight:700;")
        forma_ia.addRow("Hardware:", etiqueta_gpu)
        raiz.addWidget(grupo_ia)

        # --- Guardar --------------------------------------------------------- #
        boton_guardar = QPushButton("💾 Guardar y aplicar")
        boton_guardar.setMinimumHeight(50)
        boton_guardar.setStyleSheet("background:#2563eb;color:white;font-weight:700;border-radius:8px;")
        boton_guardar.clicked.connect(self._guardar)
        raiz.addWidget(boton_guardar)
        raiz.addStretch(1)

    # ------------------------------------------------------------------ #
    def _poblar_dispositivos(self) -> None:
        import sounddevice as sd

        self.combo_entrada.addItem("Predeterminado del sistema", None)
        self.combo_salida.addItem("Predeterminado del sistema", None)
        try:
            for indice, disp in enumerate(sd.query_devices()):
                if int(disp.get("max_input_channels", 0)) > 0:
                    self.combo_entrada.addItem(disp["name"], disp["name"])
                if int(disp.get("max_output_channels", 0)) > 0:
                    self.combo_salida.addItem(disp["name"], disp["name"])
        except Exception:
            pass
        nombre_in = self.config["audio"].get("dispositivo_entrada")
        nombre_out = self.config["audio"].get("dispositivo_salida")
        if nombre_in:
            if self.combo_entrada.findText(nombre_in) >= 0:
                self.combo_entrada.setCurrentText(nombre_in)
        if nombre_out:
            if self.combo_salida.findText(nombre_out) >= 0:
                self.combo_salida.setCurrentText(nombre_out)

    @staticmethod
    def _estado_gpu() -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return f"✔ GPU lista: {torch.cuda.get_device_name(0)}"
            return "✖ Sin GPU (CUDA no disponible) — IA en CPU, latencia alta"
        except ImportError:
            return "— PyTorch no instalado (solo Modo DSP)"

    def _elegir_carpeta(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de grabaciones")
        if ruta:
            self.campo_carpeta.setText(ruta)

    def _guardar(self) -> None:
        self.config["audio"]["buffer_size"] = self.combo_buffer.currentData()
        self.config["audio"]["dispositivo_entrada"] = self.combo_entrada.currentData()
        self.config["audio"]["dispositivo_salida"] = self.combo_salida.currentData()
        self.config["grabacion"]["carpeta_destino"] = self.campo_carpeta.text().strip() \
            or "./grabaciones"
        self.config["grabacion"]["bitrate_kbps"] = int(self.combo_bitrate.currentText())
        self.config["motor"]["permitir_ia"] = self.check_ia.currentData()

        atajos: dict[str, str] = {}
        for id_voz, editor in self.editores_atajo.items():
            secuencia = editor.keySequence().toString()
            if secuencia:
                atajos[secuencia] = id_voz
        self.config["atajos"] = atajos

        self.repo_config.guardar(self.config)
        self.motor.cambiar_buffer(int(self.config["audio"]["buffer_size"]))
        self.al_aplicar_config()
