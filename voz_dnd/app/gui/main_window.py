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
    QApplication,
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
from app.engine.lector_texto import LectorTexto, configurar_voz_tts
from app.engine.modulo_ia import ModuloIA
from app.engine.motor_audio import MotorAudio
from app.engine.procesador import ProcesadorBase, ProcesadorDSP, ProcesadorIA
from app.gui.medidor_nivel import MedidorNivel
from app.gui.pestana_ajustes import PestanaAjustes
from app.gui.pestana_editor import PestanaEditor
from app.gui.pestana_lectura import PestanaLectura
from app.gui.pestana_voces import PestanaVoces
from app.gui.tema import Tema, estilo_global, tema_por_nombre
from app.gui.widgets import BannerAlerta
from app.rutas import CARPETA_VOCES, DATA_DIR, RUTA_CONFIG, RUTA_PARAMETROS

log = logging.getLogger(__name__)

DURACION_PREVIEW_MS = 2000
INTERVALO_METRO_MS = 33       # ~30 FPS para el medidor de nivel
INTERVALO_RELOJ_MS = 500      # timer de grabación


class VentanaPrincipal(QMainWindow):
    senal_exportacion = pyqtSignal(object, object)  # (Path|None, aviso|None)
    senal_progreso_lectura = pyqtSignal(str)        # texto de estado del render
    senal_lectura_lista = pyqtSignal(object, object)  # (ruta_wav|None, info|None)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎲 Cambiador de Voz · DM de D&D")
        self._fijar_tamano_base()
        self.repo_cfg = RepoConfig(RUTA_CONFIG)
        self.cfg, avisos_cfg = self.repo_cfg.cargar()
        self._tema = tema_por_nombre(self.cfg.ui.tema)
        self.setStyleSheet(estilo_global(self._tema))

        # ---------- Infraestructura: composición de capas (Fase 1) ----------
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
        self._hilo_lectura: threading.Thread | None = None
        self._lectura_cancelada = False
        self._leyendo = False
        self._ultima_lectura = None  # (buffer, ruta_wav|None) para "reproducir de nuevo"

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
        else:
            if self.motor.usando_dispositivos_default:
                self.banner.mostrar_info(
                    "Los dispositivos guardados no se pudieron abrir; "
                    "se usan los del sistema. Revisa Ajustes → dispositivos.")

        self.senal_exportacion.connect(self._mostrar_exportacion)
        self._refrescar_info_motor()
        self._ajustar_a_pantalla()

    def showEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        """Al mostrarse se re-ajusta y centra la ventana (el layout de los
        paneles con scroll puede terminar de calcularse al mostrarse)."""
        super().showEvent(evento)
        self._ajustar_a_pantalla()

    def _fijar_tamano_base(self) -> None:
        """Tamaño inicial recortado al área visible (antes de construir la UI)."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1000, 680)
            return
        disp = screen.availableGeometry()
        self.resize(min(1000, disp.width() - 40), min(680, disp.height() - 60))

    def _ajustar_a_pantalla(self) -> None:
        """Tras construir la UI: ajusta el tamaño al contenido sin pasarse del
        área visible y centra la ventana para que nunca quede fuera (ni por la
        parte de abajo). El tamaño mínimo se recorta también para que un
        contenido grande no fuerce a la ventana a salirse de la pantalla (los
        paneles internos con scroll absorben el sobrante)."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        disp = screen.availableGeometry()
        ancho_max = disp.width() - 40
        alto_max = disp.height() - 60
        self.setMinimumSize(
            min(self.minimumSizeHint().width(), ancho_max),
            min(self.minimumSizeHint().height(), alto_max))
        self.adjustSize()
        self.resize(min(self.size().width(), ancho_max),
                    min(self.size().height(), alto_max))
        self.move(disp.x() + (disp.width() - self.width()) // 2,
                  disp.y() + (disp.height() - self.height()) // 2)

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
        self.boton_pausa = QPushButton("⏸ Pausa mic")
        self.boton_pausa.setStyleSheet(
            "background:#3a5a8a;color:white;font-weight:700;padding:6px 18px;"
            "border-radius:8px;")
        self.boton_pausa.clicked.connect(self._alternar_pausa)
        barra.addWidget(titulo)
        barra.addStretch(1)
        barra.addWidget(QLabel("Nivel:"))
        barra.addWidget(self.medidor)
        barra.addWidget(self.boton_pausa)
        barra.addWidget(self.check_monitoreo)
        barra.addWidget(self.boton_rec)
        barra.addWidget(self.etiqueta_reloj)
        raiz.addLayout(barra)

        # ---- Banner de avisos (tolerancia a fallos) ----
        self.banner = BannerAlerta()
        raiz.addWidget(self.banner)

        # ---- Pestañas ----
        self.pestana_voces = PestanaVoces()
        self.pestana_voces.set_tema(self._tema)
        self.pestana_editor = PestanaEditor(self.gestor_voces, self.catalogo)
        self.pestana_ajustes = PestanaAjustes(
            self.cfg, self.gestor_voces.todas(), self._tema)
        carpeta_wav = self._carpeta_wav_base()
        self.pestana_lectura = PestanaLectura(self._tema, carpeta_wav)
        pestanas = QTabWidget()
        pestanas.addTab(self.pestana_voces, "🎤 Voces")
        pestanas.addTab(self.pestana_editor, "🎚️ Editor")
        pestanas.addTab(self.pestana_lectura, "📖 Leer")
        pestanas.addTab(self.pestana_ajustes, "⚙️ Ajustes")
        raiz.addWidget(pestanas, 1)

        # ---- Pie ----
        pie = QLabel("Consejo: usa auriculares para evitar realimentación "
                     "(micrófono → altavoces).")
        pie.setStyleSheet(f"color:{self._tema.tenue};")
        raiz.addWidget(pie)

        # ---- Conexiones entre pestañas y la ventana ----
        self.pestana_voces.senal_voz_seleccionada.connect(self._cambiar_voz)
        self.pestana_voces.senal_recargar.connect(self._recargar_voces)
        self.pestana_editor.senal_probar.connect(self._probar_parametros)
        self.pestana_editor.senal_voces_cambiadas.connect(self._voces_cambiadas)
        self.pestana_ajustes.senal_config_actualizada.connect(self._aplicar_config)

        self.pestana_lectura.senal_leer.connect(self._leer_texto)
        self.pestana_lectura.senal_detener.connect(self._detener_lectura)
        self.pestana_lectura.senal_voz_tts.connect(configurar_voz_tts)
        self.pestana_lectura.senal_abrir_carpeta.connect(
            lambda c: self._abrir_carpeta(Path(c or ".")))
        self.pestana_lectura.senal_reproducir.connect(self._reproducir_ultima)
        self.senal_progreso_lectura.connect(self.pestana_lectura.set_estado)
        self.senal_lectura_lista.connect(self._mostrar_lectura_lista)

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

    # ========================= lectura de texto =========================== #
    def _leer_texto(self, texto: str) -> None:
        """Lee el texto con la voz activa en un hilo de trabajo.

        Construye un procesador FRESCO desde la voz seleccionada (igual que
        el micrófono), sintetiza el texto con edge-tts, le aplica la voz y
        primero reproduce el resultado por el stream y (opcional) lo guarda
        en WAV. Todo el trabajo pesado/TTS/RVC ocurre fuera del hilo de la
        GUI y del de audio.
        """
        if self._leyendo:
            self.banner.mostrar_info("Ya hay una lectura en curso.")
            return
        texto = texto.strip()
        if not texto:
            self.pestana_lectura.set_estado("El texto está vacío.")
            return

        voz = self._voz_actual
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
            else:
                procesador = ProcesadorDSP(voz, sr, self._cfg_cadena, self._fabrica)
        except Exception as exc:  # noqa: BLE001
            log.exception("No se pudo preparar la voz para leer")
            self.banner.mostrar_error(f"No se pudo preparar la voz para leer: {exc}")
            return

        self._lectura_cancelada = False
        self._leyendo = True
        self.pestana_lectura.set_leyendo(True)
        self.pestana_lectura.set_estado("Preparando la voz…")
        ruta_wav = None
        if self.pestana_lectura.guardar_wav:
            ruta_wav = self._ruta_wav_salida()
        self._hilo_lectura = threading.Thread(
            target=self._lectura_en_hilo,
            args=(texto, procesador, sr, ruta_wav), daemon=True)
        self._hilo_lectura.start()

    def _lectura_en_hilo(self, texto, procesador, sr, ruta_wav) -> None:
        lector = LectorTexto()
        try:
            # El modo IA requiere cargar su modelo (lento → aquí en el hilo).
            preparar = getattr(procesador, "preparar", None)
            if callable(preparar):
                preparar()
            if self._lectura_cancelada:
                return
            salida = lector.renderizar(
                texto, procesador, sr, ruta_wav=ruta_wav,
                on_progreso=self._reportar_progreso if not self._lectura_cancelada
                else None)
            if self._lectura_cancelada:
                return
            self.senal_lectura_lista.emit((ruta_wav, salida), None)
        except Exception as exc:  # noqa: BLE001
            log.exception("Error al leer el texto")
            self.senal_lectura_lista.emit((None, None), f"Error: {exc}")
        finally:
            cerrar = getattr(procesador, "cerrar", None)
            if callable(cerrar):
                try:
                    cerrar()
                except Exception:  # noqa: BLE001
                    log.exception("Error al cerrar el procesador de lectura")

    def _reportar_progreso(self, mensaje: str) -> None:
        if not self._lectura_cancelada:
            self.senal_progreso_lectura.emit(mensaje)

    def _mostrar_lectura_lista(self, resultado, error) -> None:
        # resultado = (ruta_wav|None, salida|None)
        self._leyendo = False
        self.pestana_lectura.set_leyendo(False)
        if error:
            self.pestana_lectura.set_estado(str(error))
            self.banner.mostrar_error(str(error))
            return
        ruta_wav, salida = resultado
        if self._lectura_cancelada:
            self.pestana_lectura.set_estado("Lectura detenida.")
            return

        # Guardamos el resultado para poder reproducirlo de nuevo.
        self._ultima_lectura = (salida, ruta_wav)
        self.pestana_lectura.marcar_reproducible(salida is not None)

        # Aviso si no hay audio donde reproducir (evita el "se leyó" falso).
        if not self.motor.audio_activo:
            base = ("⚠ No hay dispositivo de audio disponible para reproducir "
                    "la lectura.")
        else:
            base = "▶ Reproduciendo el texto con tu voz."
            self.motor.reproducir(salida)

        if ruta_wav is not None:
            base += (f"\n\n📁 WAV guardado en:\n {ruta_wav}\n"
                     "(usa «Abrir» o el botón para ver la carpeta)")
        self.pestana_lectura.set_estado(base)

    def _reproducir_ultima(self) -> None:
        """Reproduce de nuevo el último texto leído (si hay audio e resultado)."""
        if not self._ultima_lectura or self._ultima_lectura[0] is None:
            self.pestana_lectura.set_estado("Aún no hay una lectura para repetir.")
            return
        if not self.motor.audio_activo:
            self.banner.mostrar_error(
                "No hay dispositivo de audio disponible para reproducir.")
            return
        self.motor.reproducir(self._ultima_lectura[0])
        self.banner.mostrar_info("🔁 Reproduciendo la última lectura.")

    def _detener_lectura(self) -> None:
        """Detiene la reproducción en curso y pide al hilo que aborte."""
        self._lectura_cancelada = True
        self.motor.detener_reproduccion()

    def _carpeta_wav_base(self) -> str:
        """Carpeta por defecto para el WAV de lectura (visible en la pestaña)."""
        destino = self.cfg.grabacion.carpeta_destino.strip()
        if destino:
            carpeta = Path(destino)
        else:
            carpeta = DATA_DIR / "lectura"
        return str(carpeta)

    def _ruta_wav_salida(self) -> Path:
        """Ruta destino del WAV de lectura con fecha/hora en el nombre."""
        from datetime import datetime
        carpeta = Path(self.pestana_lectura.carpeta_destino
                       or self._carpeta_wav_base())
        nombre = f"lectura_{datetime.now():%Y%m%d_%H%M%S}.wav"
        return carpeta / nombre

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
        cambio_tema = (cfg.ui.tema != self.cfg.ui.tema)
        self.cfg = cfg
        self.repo_cfg.guardar(cfg)
        if cambio_tema:
            self._tema = tema_por_nombre(cfg.ui.tema)
            self.setStyleSheet(estilo_global(self._tema))
            self.pestana_voces.set_tema(self._tema)
            self.pestana_ajustes.set_tema(self._tema)
            self.pestana_lectura.set_tema(self._tema)
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

    def _alternar_pausa(self) -> None:
        if self.motor.pausado:
            self.motor.reanudar()
            self.boton_pausa.setText("⏸ Pausa mic")
            self.boton_pausa.setStyleSheet(
                "background:#3a5a8a;color:white;font-weight:700;padding:6px 18px;"
                "border-radius:8px;")
            self.banner.mostrar_info("Micrófono reanudado.")
        else:
            self.motor.pausar()
            self.boton_pausa.setText("▶ Reanudar mic")
            self.boton_pausa.setStyleSheet(
                "background:#5a5a2a;color:white;font-weight:700;padding:6px 18px;"
                "border-radius:8px;")
            self.banner.mostrar_info("Micrófono en pausa.")

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
        self._detener_lectura()
        self.motor.detener()
        evento.accept()
