"""Pestaña "⚙️ Ajustes" (Fase 5.4): buffer, dispositivos, carpeta MP3, atajos.

Todos los cambios se aplican al pulsar "💾 Guardar ajustes", que emite
`senal_config_actualizada(ConfigApp)`; la ventana principal persiste el JSON,
reinicia el stream de audio si hace falta y reconstruye los atajos.

Incluye el GESTOR DE MOTORES IA (idea del Model Manager de VoiceStudio):
muestra el estado real de cada pieza del modo IA y permite instalar la vía
ONNX (rmvpe-onnx + onnxruntime) sin salir de la app, en un hilo de fondo
que jamás bloquea la GUI. La degradación a DSP sigue intacta: si algo
falla, el modo IA avisa y el audio nunca se corta.
"""
from __future__ import annotations

import importlib
import logging
import subprocess
import sys
import threading
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    BUFFERS_VALIDOS,
    SAMPLE_RATES_VALIDOS,
    ConfigApp,
    ConfigAudio,
    ConfigGrabacion,
    ConfigMotor,
    ConfigUI,
)
from app.domain.models import IVoiceProfile
from app.engine.modulo_ia import ModuloIA, estado_motores
from app.engine import dataset
from app.engine.dataset import ErrorDataset
from app.engine.motor_audio import OVERHEAD_DRIVER_MS
from app.gui.tema import CLARO, Tema

log = logging.getLogger(__name__)

BITRATES_KBPS = (128, 192, 320)   # opciones de UI (no límite del motor)


class PestanaAjustes(QWidget):
    senal_config_actualizada = pyqtSignal(object)  # ConfigApp
    senal_ia_instalado = pyqtSignal(bool, str)  # ok, resumen (emitida desde el hilo de fondo)
    senal_dataset_listo = pyqtSignal(bool, str)  # ok, resumen (hilo de fondo, copia de WAVs)

    def __init__(self, cfg: ConfigApp, voces: list[IVoiceProfile],
                 tema: Tema | None = None):
        super().__init__()
        self._cfg = cfg
        self._voces = voces
        self._tema = tema or CLARO
        self._editores_atajo: dict[str, QKeySequenceEdit] = {}  # id → editor
        self._form_atajos: QFormLayout | None = None
        # El resultado de la instalación (hilo de fondo) llega por señal
        # (queued automáticamente desde un hilo no-GUI) y se pinta aquí.
        self.senal_ia_instalado.connect(self._al_terminar_instalacion)
        self.senal_dataset_listo.connect(self._al_terminar_dataset)

        contenido = QWidget()
        raiz = QVBoxLayout(contenido)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(12)
        self._contenido = contenido
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(contenido)
        self._scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        raiz_ventana = QVBoxLayout(self)
        raiz_ventana.setContentsMargins(0, 0, 0, 0)
        raiz_ventana.addWidget(self._scroll)
        self._raiz_ventana = raiz_ventana

        # ------------------------ Apariencia ---------------------- #
        grupo_tema = QGroupBox("🎨 Apariencia")
        form_tema = QFormLayout(grupo_tema)
        self.combo_tema = QComboBox()
        self.combo_tema.addItem("🌙 Oscuro", "oscuro")
        self.combo_tema.addItem("☀️ Claro", "claro")
        self.combo_tema.setCurrentIndex(
            0 if self._tema.nombre == "oscuro" else 1)
        form_tema.addRow("Tema:", self.combo_tema)
        raiz.addWidget(grupo_tema)

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
        for sr in SAMPLE_RATES_VALIDOS:
            self.combo_sr.addItem(f"{sr} Hz", sr)
        self.combo_sr.setCurrentIndex(
            list(SAMPLE_RATES_VALIDOS).index(cfg.audio.sample_rate))
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

        # Gestor de motores: estado real de cada pieza + instalación de la
        # vía ONNX sin salir de la app (hilo de fondo, nunca bloquea la GUI).
        self.etiqueta_motores = QLabel("")
        self.etiqueta_motores.setWordWrap(True)
        self._refrescar_motores()
        form_ia.addRow("Motores:", self.etiqueta_motores)
        self.boton_ia_instalar = QPushButton("⬇️ Instalar vía ONNX (CPU)")
        self.boton_ia_instalar.setToolTip(
            "Instala rmvpe-onnx + onnxruntime en este Python. Con eso el "
            "modo IA funciona en cualquier PC; sin ello degrada a DSP.")
        self.boton_ia_instalar.clicked.connect(self._instalar_ia_onnx)
        form_ia.addRow("", self.boton_ia_instalar)
        raiz.addWidget(grupo_ia)

        # ----------------- Clonación (preparación) ----------------- #
        grupo_clon = QGroupBox("🧬 Clonación de voz (preparación experimental)")
        form_clon = QFormLayout(grupo_clon)
        self.edit_sujeto = QLineEdit()
        self.edit_sujeto.setPlaceholderText(
            "P. ej. Aria la Bardo (tu voz o la de quien te dio permiso)")
        form_clon.addRow("Sujeto:", self.edit_sujeto)
        self.check_consentimiento = QCheckBox(
            "Es mi propia voz o tengo permiso explícito para clonarla")
        form_clon.addRow(self.check_consentimiento)
        self.boton_wavs_dataset = QPushButton("⬇️ Añadir WAVs limpios al dataset")
        self.boton_wavs_dataset.setToolTip(
            "Copia WAV PCM limpios (≥ 2 s cada uno) al dataset del sujeto. "
            "Objetivo honesto: 3 minutos de voz limpia o más.")
        self.boton_wavs_dataset.clicked.connect(self._anadir_wavs_dataset)
        form_clon.addRow("", self.boton_wavs_dataset)
        self.etiqueta_dataset = QLabel("")
        self.etiqueta_dataset.setWordWrap(True)
        self._refrescar_dataset()
        form_clon.addRow("Dataset:", self.etiqueta_dataset)
        nota_clon = QLabel(
            "Honesto: hoy esto PREPARA el dataset (muestras + consentimiento "
            "registrado). El entrenamiento RVC llegará más adelante y usará "
            "exactamente estos datos.")
        nota_clon.setWordWrap(True)
        form_clon.addRow(nota_clon)
        raiz.addWidget(grupo_clon)

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

    # ----------------------- gestor de motores IA -------------------------- #
    PAQUETES_IA_ONNX = ("rmvpe-onnx", "onnxruntime")

    def _texto_motores(self) -> str:
        estado = estado_motores()
        if estado["ia_lista"]:
            linea_ia = "✔ Modo IA LISTO"
        else:
            linea_ia = ("✖ Sin vía RVC completa: el modo IA degradará a DSP "
                        "(el audio sigue funcionando igual)")
        return (f"{linea_ia}\n"
                f"  PyTorch: {'✔' if estado['torch'] else '✖'}  ·  "
                f"onnxruntime: {'✔' if estado['onnxruntime'] else '✖'}  ·  "
                f"rmvpe-onnx: {'✔' if estado['rmvpe_onnx'] else '✖'}  ·  "
                f"tts-with-rvc: {'✔' if estado['tts_with_rvc'] else '✖'}\n"
                f"  ({estado['detalle_backend']})")

    def _refrescar_motores(self) -> None:
        """Relee el estado real de las piezas del modo IA y lo muestra."""
        self.etiqueta_motores.setText(self._texto_motores())
        estado = estado_motores()
        self.boton_ia_instalar.setVisible(not estado["ia_lista"])

    def _instalar_ia_onnx(self) -> None:
        """Lanza pip install de la vía ONNX en un hilo de fondo.

        El subprocess usa el MISMO Python que ejecuta la app (sys.executable:
        en desarrollo el venv, en el instalador el runtime embebido). Al
        terminar se invalidan los cachés de imports y se relee el estado:
        si todo fue bien, el modo IA queda usable sin reiniciar.
        """
        self.boton_ia_instalar.setEnabled(False)
        self.boton_ia_instalar.setText("Instalando… (tarda un rato)")

        def en_hilo() -> None:
            ok = False
            resumen = ""
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet",
                     *self.PAQUETES_IA_ONNX],
                    capture_output=True, text=True, timeout=600,
                )
                ok = proc.returncode == 0
                cola = (proc.stderr or proc.stdout or "").strip().splitlines()
                resumen = cola[-1] if cola else ("instalado" if ok else "sin detalle")
            except Exception as exc:  # noqa: BLE001 — pip puede fallar de mil maneras
                resumen = str(exc)
            if ok:
                # Los paquetes nuevos deben ser visibles sin reiniciar la app.
                importlib.invalidate_caches()
            self.senal_ia_instalado.emit(ok, resumen)

        threading.Thread(target=en_hilo, daemon=True).start()

    def _al_terminar_instalacion(self, ok: bool, resumen: str) -> None:
        """Vuelve del hilo de fondo: refresca y avisa con honestidad."""
        self.boton_ia_instalar.setEnabled(True)
        self.boton_ia_instalar.setText("⬇️ Instalar vía ONNX (CPU)")
        self._refrescar_motores()
        log.info("Instalación de la vía ONNX: ok=%s (%s)", ok, resumen)

    # ------------------ clonación: dataset + consentimiento ---------------- #
    def _refrescar_dataset(self) -> None:
        """Resumen honesto de los datasets existentes (nada = aviso amable)."""
        resumen = dataset.sujetos()
        if not resumen:
            self.etiqueta_dataset.setText(
                "Aún no hay datasets. Nombra al sujeto, marca el "
                "consentimiento y añade WAVs limpios.")
            return
        filas = []
        for s in resumen:
            estado = ("suficiente (≥ 3 min)" if s["suficiente"]
                      else f"{s['segundos']:.0f} s de {s['objetivo_segundos']:.0f} s")
            filas.append(
                f"  · {s['nombre']}: {s['n_muestras']} muestra(s), {estado}")
        self.etiqueta_dataset.setText("\n".join(filas))

    def _anadir_wavs_dataset(self) -> None:
        """Registra al sujeto y copia WAVs al dataset en un hilo de fondo.

        El consentimiento es OBLIGATORIO y queda registrado con fecha en
        accesos.json: sin él no hay dataset. La copia es local pero puede
        ser de muchos MB: mismo patrón de hilo que la instalación ONNX.
        """
        nombre = self.edit_sujeto.text().strip()
        try:
            dataset.crear_sujeto(nombre, self.check_consentimiento.isChecked())
        except ErrorDataset as exc:
            QMessageBox.warning(self, "Falta el consentimiento", str(exc))
            return

        rutas, _ = QFileDialog.getOpenFileNames(
            self, "WAVs limpios del sujeto", "", "WAV (*.wav)")
        if not rutas:
            self._refrescar_dataset()
            return
        self.boton_wavs_dataset.setEnabled(False)
        self.boton_wavs_dataset.setText("Copiando muestras…")

        def en_hilo() -> None:
            ok = True
            resumen = ""
            try:
                resultado = dataset.anadir_muestras(
                    nombre, [Path(r) for r in rutas])
                rechazados = resultado.get("rechazados", [])
                resumen = (
                    f"{resultado['n_muestras']} muestra(s) añadidas "
                    f"({resultado['segundos']:.0f} s)"
                    + (f", {len(rechazados)} rechazadas" if rechazados else ""))
            except Exception as exc:  # noqa: BLE001 — copia puede fallar
                ok = False
                resumen = str(exc)
            self.senal_dataset_listo.emit(ok, resumen)

        threading.Thread(target=en_hilo, daemon=True).start()

    def _al_terminar_dataset(self, ok: bool, resumen: str) -> None:
        self.boton_wavs_dataset.setEnabled(True)
        self.boton_wavs_dataset.setText("⬇️ Añadir WAVs limpios al dataset")
        self._refrescar_dataset()
        if ok:
            QMessageBox.information(
                self, "Dataset actualizado", resumen
                + "\nRecuerda: el entrenamiento RVC llega más adelante.")
        else:
            QMessageBox.critical(self, "No se pudo actualizar el dataset", resumen)
        log.info("Dataset: ok=%s (%s)", ok, resumen)

    # ------------------------------ guardar --------------------------------- #
    def _refrescar_latencia(self) -> None:
        buffer = self.combo_buffer.currentData() or 256
        sr = self.combo_sr.currentData() or 48000
        base = 2.0 * buffer / sr * 1000.0
        self.etiqueta_latencia.setText(
            f"≈ {base + OVERHEAD_DRIVER_MS:.0f} ms (sin contar efectos DSP)")

    def _guardar(self) -> None:
        atajos: dict[str, str] = {}
        for id_voz, editor in self._editores_atajo.items():
            secuencia = editor.keySequence().toString()
            if secuencia:
                atajos[secuencia] = id_voz

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
            ui=ConfigUI(
                vista_botones=self._cfg.ui.vista_botones,
                tema=self.combo_tema.currentData() or "oscuro",
            ),
            atajos=atajos,
        )
        self.senal_config_actualizada.emit(cfg)

    def set_tema(self, tema: Tema) -> None:
        """Aplicado externamente (p. ej. al recargar config): sincroniza el combo."""
        self._tema = tema
        self.combo_tema.setCurrentIndex(0 if tema.nombre == "oscuro" else 1)
