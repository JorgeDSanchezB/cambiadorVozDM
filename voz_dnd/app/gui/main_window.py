"""Ventana principal (Fase 5): barra superior + 3 pestañas + tolerancia a fallos.

Responsabilidades:
  * Componer las capas (RepoConfig, GestorVoces, MotorAudio, catálogo).
  * Orquestar el cambio de voz (DSP o IA) y el preview del Editor.
  * Timer de grabación (QTimer 500 ms) y medidor de nivel (QTimer 33 ms).
  * Exportación de MP3 en un hilo de trabajo con señal de vuelta a la GUI.
  * Atajos de teclado reconstruibles desde config.json.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigApp, RepoConfig
from app.domain.catalogo import CatalogoParametros
from app.domain.models import ParametrosDSP, PerfilDSP, PerfilIA
from app.engine.fabrica_cadena import ConfigCadena, FabricaCadena
from app.engine.gestor_voces import GestorVoces
from app.engine.modulo_ia import ModuloIA
from app.engine.motor_audio import MotorAudio
from app.engine.procesador import ProcesadorBase, ProcesadorDSP, ProcesadorIA
from app.gui.medidor_nivel import MedidorNivel
from app.gui.pestana_ajustes import PestanaAjustes
from app.gui.pestana_editor import PestanaEditor
from app.gui.pestana_voces import PestanaVoces
from app.gui.widgets import BannerAlerta
from app.rutas import CARPETA_VOCES, RUTA_CONFIG, RUTA_PARAMETROS

log = logging.getLogger(__name__)

DURACION_PREVIEW_MS = 2000
INTERVALO_METRO_MS = 33       # ~30 FPS para el medidor de nivel
INTERVALO_RELOJ_MS = 500      # timer de grabación

ESTILO = """
QMainWindow { background: #14161a; }
QTabWidget::pane { border: 1px solid #2a2e36; border-radius: 6px; background: #191c22; }
QTabBar::tab { background: #1f232b; color: #9aa4b2; padding: 8px 18px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #191c22; color: #e8e3d5; font-weight: 700; }
QWidget { color: #cfd6e0; font-size: 13px; }
QLabel#titulo { color: #e8e3d5; font-size: 17px; font-weight: 700; }
QLabel#reloj { color: #ff6b6b; font-size: 16px; font-weight: 700; }
QLabel#latencia { color: #9aa4b2; font-size: 12px; }
QPushButton { min-height: 30px; background: #242933; border: 1px solid #333a47;
              border-radius: 6px; padding: 4px 12px; }
QPushButton:hover { background: #2c3240; }
QGroupBox { border: 1px solid #2a2e36; border-radius: 8px; margin-top: 10px;
            padding: 10px; font-weight: 600; }
QGroupBox::title { color: #9aa4b2; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
     background: #10131a; border: 1px solid #333a47; border-radius: 4px; padding: 4px; }
QCheckBox::indicator { width: 16px; height: 16px; }
"""


class VentanaPrincipal(QMainWindow):
    senal_exportacion = pyqtSignal(object, object)  # (Path|None, aviso|None)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎲 Cambiador de Voz · DM de D&D")
        self.resize(1000, 680)
        self.setStyleSheet(ESTILO)

        # ---------- Infraestructura: composición de capas (Fase 1) ----------
        self.repo_cfg = RepoConfig(RUTA_CONFIG)
        self.cfg, avisos_cfg = self.repo_cfg.cargar()
        self.catalogo = CatalogoParametros.desde_json(RUTA_PARAMETROS)
        self.gestor_voces = GestorVoces(CARPETA_VOCES, self.catalogo)
        carga = self.gestor_voces.cargar_todas()

        self._fabrica = FabricaCadena(self.catalogo)
        self._cfg_cadena = ConfigCadena(tam_grano_pitch=self.cfg.motor.tam_grano_pitch)
        neutral = self.gestor_voces.por_id(GestorVoces.ID_NEUTRA)
        assert neutral is not None  # GestorVoces garantiza la voz Neutral
        self.motor = MotorAudio(
            self.cfg,
            ProcesadorDSP(neutral, self.cfg.audio.sample_rate,
                          self._cfg_cadena, self._fabrica),
        )
        self._voz_actual = neutral
        self._preview_previo: ProcesadorBase | None = None
        self._timer_preview = QTimer(self)
        self._timer_preview.setSingleShot(True)
        self._timer_preview.timeout.connect(self._terminar_preview)
        self._grabacion_en_curso = False
        self._atajos: list[QShortcut] = []

        # ---------------------------- UI -------------------------------- #
        self._construir_ui()

        # --------------------- estado inicial --------------------------- #
        self._poblar_voces(carga.voces, str(neutral.id))
        self._reconstruir_atajos()
        self._conectar_timers()
        avisos = [f"{archivo}: {mensaje}" for archivo, mensaje in carga.errores]
        avisos.extend(avisos_cfg)
        if avisos:
            self.banner.mostrar_avisos(avisos)

        try:
            self.motor.iniciar()
        except Exception as exc:  # noqa: BLE001
            log.exception("Sin audio al arrancar")
            self.banner.mostrar_error(
                f"No se pudo abrir el audio: {exc}\n"
                "Revisa Ajustes → dispositivos y pulsa Guardar ajustes para reintentar.")

        self.senal_exportacion.connect(self._mostrar_exportacion)
        self._refrescar_info_motor()

    # ============================ construcción UI ========================== #
    def _construir_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(12, 10, 12, 10)
        raiz.setSpacing(8)

        # ---- Barra superior: título · nivel · monitoreo · REC ----
        barra = QHBoxLayout()
        titulo = QLabel("🎲 Cambiador de Voz · DM")
        titulo.setObjectName("titulo")
        self.medidor = MedidorNivel()
        self.check_monitoreo = QCheckBox("Monitoreo")
        self.check_monitoreo.setChecked(True)
        self.check_monitoreo.setToolTip(
            "Desactívalo para grabar sin oírte (evita realimentación).")
        self.check_monitoreo.toggled.connect(self._cambiar_monitoreo)
        self.etiqueta_reloj = QLabel("⏺ 00:00:00")
        self.etiqueta_reloj.setObjectName("reloj")
        self.boton_rec = QPushButton("🎤 Grabar")
        self.boton_rec.setStyleSheet(
            "background:#8f2d2d;color:white;font-weight:700;padding:6px 18px;"
            "border-radius:8px;")
        self.boton_rec.clicked.connect(self._alternar_grabacion)
        barra.addWidget(titulo)
        barra.addStretch(1)
        barra.addWidget(QLabel("Nivel:"))
        barra.addWidget(self.medidor)
        barra.addWidget(self.check_monitoreo)
        barra.addWidget(self.boton_rec)
        barra.addWidget(self.etiqueta_reloj)
        raiz.addLayout(barra)

        # ---- Banner de avisos (tolerancia a fallos) ----
        self.banner = BannerAlerta()
        raiz.addWidget(self.banner)

        # ---- Pestañas ----
        self.pestana_voces = PestanaVoces()
        self.pestana_editor = PestanaEditor(self.gestor_voces, self.catalogo)
        self.pestana_ajustes = PestanaAjustes(self.cfg, self.gestor_voces.todas())
        pestanas = QTabWidget()
        pestanas.addTab(self.pestana_voces, "🎤 Voces")
        pestanas.addTab(self.pestana_editor, "🎚️ Editor")
        pestanas.addTab(self.pestana_ajustes, "⚙️ Ajustes")
        raiz.addWidget(pestanas, 1)

        # ---- Pie ----
        pie = QLabel("Consejo: usa auriculares para evitar realimentación "
                     "(micrófono → altavoces).")
        pie.setStyleSheet("color:#7d8590;")
        raiz.addWidget(pie)

        # ---- Conexiones entre pestañas y la ventana ----
        self.pestana_voces.senal_voz_seleccionada.connect(self._cambiar_voz)
        self.pestana_voces.senal_recargar.connect(self._recargar_voces)
        self.pestana_editor.senal_probar.connect(self._probar_parametros)
        self.pestana_editor.senal_voces_cambiadas.connect(self._voces_cambiadas)
        self.pestana_ajustes.senal_config_actualizada.connect(self._aplicar_config)

    # ============================== voces ================================== #
    def _poblar_voces(self, voces, seleccionar_id: str | None) -> None:
        self.pestana_voces.poblar(voces, seleccionar_id)
        self.pestana_editor.refrescar(seleccionar_id)

    def _cambiar_voz(self, id_voz: str) -> None:
        if not id_voz:
            return
        voz = self.gestor_voces.por_id(id_voz)
        if voz is None:
            return
        sr = self.cfg.audio.sample_rate
        try:
            if isinstance(voz, PerfilIA):
                if not self.cfg.motor.permitir_ia:
                    self.banner.mostrar_error(
                        "El modo IA está deshabilitado en Ajustes.")
                    return
                motor_ia = ModuloIA(voz.parametros_ia, sr)
                procesador: ProcesadorBase = ProcesadorIA(
                    voz, sr, self._cfg_cadena, self._fabrica, motor_ia)
                # Carga del modelo en segundo plano (nunca bloquea la UI)
                threading.Thread(target=procesador.preparar, daemon=True).start()
                self.banner.mostrar_info(
                    "Modo IA: preparando el modelo… mientras carga sonará solo "
                    "su cadena DSP post.")
            else:
                procesador = ProcesadorDSP(voz, sr, self._cfg_cadena, self._fabrica)
        except Exception as exc:  # noqa: BLE001
            log.exception("No se pudo construir la voz %s", voz.nombre)
            self.banner.mostrar_error(f"No se pudo activar «{voz.nombre}»: {exc}")
            return

        if self._preview_previo is not None:  # cancela preview en curso
            self._terminar_preview()
        self.motor.cambiar_procesador(procesador)
        self._voz_actual = voz
        self.pestana_voces.marcar_activa(str(voz.id))
        self._refrescar_info_motor()

    def _recargar_voces(self) -> None:
        carga = self.gestor_voces.cargar_todas()
        seleccion = str(self._voz_actual.id) if self._voz_actual else None
        self._poblar_voces(carga.voces, seleccion)
        self._reconstruir_atajos()
        avisos = [f"{archivo}: {mensaje}" for archivo, mensaje in carga.errores]
        if avisos:
            self.banner.mostrar_avisos(avisos)
        else:
            self.banner.mostrar_info("Voces recargadas desde data/voces/.")

    def _voces_cambiadas(self, mensaje: str) -> None:
        carga = self.gestor_voces.cargar_todas()
        seleccion = str(self._voz_actual.id) if self._voz_actual else None
        self._poblar_voces(carga.voces, seleccion)
        self._reconstruir_atajos()
        self.banner.mostrar_info(mensaje)

    # ============================== preview ================================ #
    def _probar_parametros(self, params: ParametrosDSP) -> None:
        """Preview temporal (2 s) del Editor sin tocar la voz guardada."""
        self._preview_previo = self.motor.procesador_actual
        temporal = ProcesadorDSP(
            PerfilDSP(nombre="(preview)", parametros_dsp=params),
            self.cfg.audio.sample_rate, self._cfg_cadena, self._fabrica)
        self.motor.cambiar_procesador(temporal)
        self.banner.mostrar_info("▶ Probando ajustes temporales… "
                                 "(se restaurará la voz en 2 s)")
        self._timer_preview.start(DURACION_PREVIEW_MS)

    def _terminar_preview(self) -> None:
        if self._preview_previo is not None:
            self.motor.cambiar_procesador(self._preview_previo)
            self._preview_previo = None
            self._refrescar_info_motor()

    # ============================ grabación ================================ #
    def _alternar_grabacion(self) -> None:
        if not self._grabacion_en_curso:
            self.motor.grabador.iniciar()
            self._grabacion_en_curso = True
            self.boton_rec.setText("⏹ Detener")
            self.boton_rec.setStyleSheet(
                "background:#c2453a;color:white;font-weight:700;padding:6px 18px;"
                "border-radius:8px;")
            self.banner.mostrar_info("🔴 Grabando la voz PROCESADA "
                                     "(lo que se oye es lo que se guarda).")
        else:
            self._grabacion_en_curso = False
            self.boton_rec.setEnabled(False)
            self.boton_rec.setText("⏳ Exportando…")
            self.boton_rec.setStyleSheet(
                "background:#8f2d2d;color:white;font-weight:700;padding:6px 18px;"
                "border-radius:8px;")
            threading.Thread(target=self._exportar_en_hilo, daemon=True).start()

    def _exportar_en_hilo(self) -> None:
        ruta, aviso = self.motor.grabador.detener_y_exportar()
        self.senal_exportacion.emit(ruta, aviso)

    def _mostrar_exportacion(self, ruta, aviso) -> None:
        self.boton_rec.setEnabled(True)
        self.boton_rec.setText("🎤 Grabar")
        self.etiqueta_reloj.setText("⏺ 00:00:00")
        if ruta is None:
            self.banner.mostrar_error(aviso or "No se pudo exportar la grabación.")
            return
        texto = f"Grabación guardada en:\n{ruta}"
        if aviso:
            texto += f"\n\n⚠ {aviso}"
        caja = QMessageBox(self)
        caja.setWindowTitle("Grabación lista")
        caja.setText(texto)
        boton_carpeta = caja.addButton(
            "Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
        boton_carpeta.clicked.connect(lambda: self._abrir_carpeta(ruta.parent))
        caja.addButton(QMessageBox.StandardButton.Ok)
        caja.exec()

    @staticmethod
    def _abrir_carpeta(carpeta: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(carpeta))  # type: ignore[attr-defined] # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(carpeta)])
            else:
                subprocess.Popen(["xdg-open", str(carpeta)])
        except Exception:  # noqa: BLE001
            log.exception("No se pudo abrir la carpeta %s", carpeta)

    # ============================== timers ================================= #
    def _conectar_timers(self) -> None:
        self.timer_metro = QTimer(self)
        self.timer_metro.setInterval(INTERVALO_METRO_MS)
        self.timer_metro.timeout.connect(self._tick_metro)
        self.timer_metro.start()

        self.timer_reloj = QTimer(self)
        self.timer_reloj.setInterval(INTERVALO_RELOJ_MS)
        self.timer_reloj.timeout.connect(self._tick_reloj)
        self.timer_reloj.start()

    def _tick_metro(self) -> None:
        self.medidor.set_nivel(self.motor.nivel_db)
        errores = self.motor.extraer_errores()
        if errores:
            self.banner.mostrar_avisos(errores)
        # Auto-stop por límite de duración (polling, Fase 3)
        if self._grabacion_en_curso and not self.motor.grabador.activo:
            self._alternar_grabacion()

    def _tick_reloj(self) -> None:
        if self._grabacion_en_curso:
            segundos = int(self.motor.grabador.duracion())
            self.etiqueta_reloj.setText(
                f"⏺ {segundos // 3600:02d}:{segundos // 60 % 60:02d}:{segundos % 60:02d}")

    # =========================== atajos y config =========================== #
    def _reconstruir_atajos(self) -> None:
        for atajo in self._atajos:
            atajo.setParent(None)
        self._atajos.clear()
        for tecla, id_voz in self.cfg.atajos.items():
            if not tecla or not id_voz:
                continue
            atajo = QShortcut(QKeySequence(tecla), self)
            atajo.activated.connect(
                lambda _=False, i=id_voz: self._cambiar_voz(i))
            self._atajos.append(atajo)

    def _aplicar_config(self, cfg: ConfigApp) -> None:
        cambio_audio = (cfg.audio != self.cfg.audio)
        self.cfg = cfg
        self.repo_cfg.guardar(cfg)
        self._cfg_cadena = ConfigCadena(tam_grano_pitch=cfg.motor.tam_grano_pitch)
        if cambio_audio:
            try:
                self.motor.aplicar_config_audio(cfg)
                self.banner.mostrar_info(
                    f"Audio aplicado: buffer {cfg.audio.buffer_size} · "
                    f"latencia ≈ {self.motor.latencia_estimada_ms:.0f} ms")
            except Exception as exc:  # noqa: BLE001
                log.exception("Fallo al reiniciar el audio")
                self.banner.mostrar_error(f"No se pudo reiniciar el audio: {exc}")
        self._reconstruir_atajos()
        self._refrescar_info_motor()

    def _cambiar_monitoreo(self, activo: bool) -> None:
        self.motor.monitoreo = activo

    def _refrescar_info_motor(self) -> None:
        modo = ("IA" if isinstance(self.motor.procesador_actual, ProcesadorIA)
                else "DSP")
        degradado = getattr(self.motor.procesador_actual, "degradado", False)
        aviso = " · ⚠ degradada a DSP" if degradado else ""
        self.pestana_voces.set_estado(
            f"Voz activa: {self._voz_actual.icono} {self._voz_actual.nombre} · "
            f"Modo: {modo}{aviso} · "
            f"Latencia ≈ {self.motor.latencia_estimada_ms:.0f} ms")

    # ============================== cierre ================================= #
    def closeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if self._grabacion_en_curso:
            respuesta = QMessageBox.question(
                self, "Grabación en curso",
                "Hay una grabación en curso. ¿Detenerla y guardarla antes de salir?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel)
            if respuesta == QMessageBox.StandardButton.Cancel:
                evento.ignore()
                return
            if respuesta == QMessageBox.StandardButton.Yes:
                self._grabacion_en_curso = False
                ruta, aviso = self.motor.grabador.detener_y_exportar()
                if ruta is not None:
                    QMessageBox.information(self, "Grabación guardada", str(ruta))
                elif aviso:
                    QMessageBox.warning(self, "Grabación", aviso)
        self.motor.detener()
        evento.accept()
