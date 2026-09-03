"""VentanaPrincipal: barra superior (REC + timer + medidor) y las 3 pestañas.

Hilos y GUI: un QTimer de 100 ms drena la cola de eventos del motor (el hilo
de audio JAMÁS toca Qt); un QTimer de 1 s refresca el cronómetro de grabación.
"""
from __future__ import annotations

import queue

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from aplicacion.gestor_grabacion import comprobar_ffmpeg
from dominio.entidades import IVoiceProfile
from infraestructura.gui.pestana_ajustes import PestanaAjustes
from infraestructura.gui.pestana_editor import PestanaEditor
from infraestructura.gui.pestana_voces import PestanaVoces
from infraestructura.gui.widgets import BannerAlerta, MedidorNivel

TECLA_NEUTRAL = "Esc"  # pánico: volver a voz neutra siempre disponible


class VentanaPrincipal(QMainWindow):
    def __init__(self, motor, gestor_voces, config, repo_config, catalogo: dict) -> None:
        super().__init__()
        self.motor = motor
        self.gestor_voces = gestor_voces
        self.config = config
        self.repo_config = repo_config
        self.catalogo = catalogo
        self.eventos: "queue.SimpleQueue[tuple[str, ...]]" = motor.eventos

        self.setWindowTitle("🎲 Cambiador de Voz en Tiempo Real · DM de D&D")
        self.resize(1000, 720)

        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setSpacing(10)

        # ------------------------------------------------------------------ #
        #  Barra superior: indicador REC + cronómetro + medidor + latencia
        # ------------------------------------------------------------------ #
        barra = QHBoxLayout()
        self.punto_rec = QLabel("●")
        self.punto_rec.setStyleSheet("color:#9ca3af; font-size:22px;")
        self.cronometro = QLabel("00:00")
        self.cronometro.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 18px; font-weight: 700;"
        )
        self.etiqueta_estado = QLabel("Voz: — · Modo: —")
        self.etiqueta_estado.setStyleSheet("font-weight:700;")
        self.medidor = MedidorNivel(motor)
        self.etiqueta_latencia = QLabel("Latencia ≈ — ms")
        barra.addWidget(self.punto_rec)
        barra.addWidget(self.cronometro)
        barra.addSpacing(12)
        barra.addWidget(self.etiqueta_estado, 1)
        barra.addWidget(self.medidor)
        barra.addWidget(self.etiqueta_latencia)
        raiz.addLayout(barra)

        self.banner = BannerAlerta()
        raiz.addWidget(self.banner)

        # ------------------------------------------------------------------ #
        #  Pestañas
        # ------------------------------------------------------------------ #
        self.pestanas = QTabWidget()
        self.pestana_voces = PestanaVoces(motor, gestor_voces, self.medidor)
        self.pestana_editor = PestanaEditor(
            motor, gestor_voces, catalogo, self._recargar_todo
        )
        self.pestana_ajustes = PestanaAjustes(
            motor, config, gestor_voces, repo_config, self._aplicar_ajustes
        )
        self.pestanas.addTab(self.pestana_voces, "🎤 Voces")
        self.pestanas.addTab(self.pestana_editor, "🎚️ Editor")
        self.pestanas.addTab(self.pestana_ajustes, "⚙️ Ajustes")
        raiz.addWidget(self.pestanas, 1)
        self.setCentralWidget(central)

        self._montar_menu()

        # ------------------------------------------------------------------ #
        #  Temporizadores de la GUI (drenaje de eventos + cronómetro REC)
        # ------------------------------------------------------------------ #
        self.timer_eventos = QTimer(self)
        self.timer_eventos.setInterval(100)
        self.timer_eventos.timeout.connect(self._drenar_eventos)
        self.timer_eventos.start()

        self.timer_rec = QTimer(self)
        self.timer_rec.setInterval(1000)
        self.timer_rec.timeout.connect(self._refrescar_rec)
        self.timer_rec.start()

        self.timer_parpaadeo = QTimer(self)
        self.timer_parpaadeo.setInterval(500)
        self.timer_parpaadeo.timeout.connect(self._parpadear)
        self._rec_visible = False

        self._montar_atajos()
        self._refrescar_latencia()

    # ------------------------------------------------------------------ #
    def _montar_menu(self) -> None:
        from PyQt6.QtGui import QAction

        menu_archivo = self.menuBar().addMenu("&Archivo")
        accion_recargar = QAction("🔄 Recargar voces", self)
        accion_recargar.triggered.connect(self._recargar_todo)
        menu_archivo.addAction(accion_recargar)
        accion_salir = QAction("Salir", self)
        accion_salir.setShortcut(QKeySequence("Ctrl+Q"))
        accion_salir.triggered.connect(self.close)
        menu_archivo.addAction(accion_salir)

        menu_ayuda = self.menuBar().addMenu("A&yuda")
        accion_acerca = QAction("Acerca de…", self)
        accion_acerca.triggered.connect(
            lambda: QMessageBox.information(
                self, "Acerca de",
                "Cambiador de Voz en Tiempo Real para Dungeon Masters\n"
                "DSP: Numpy/Scipy · Audio: SoundDevice · GUI: PyQt6\n\n"
                f"ffmpeg (MP3): {'✔ listo' if comprobar_ffmpeg() else '✖ falta (usará WAV)'}",
            )
        )
        menu_ayuda.addAction(accion_acerca)

    # ------------------------------------------------------------------ #
    #  Atajos de teclado (config.json → QShortcut)
    # ------------------------------------------------------------------ #
    def _montar_atajos(self) -> None:
        self._atajos: list[QShortcut] = []
        atajos: dict[str, str] = self.config.get("atajos", {})
        for tecla, id_voz in atajos.items():
            if self.gestor_voces.buscar_por_id(id_voz) is None:
                continue
            atajo = QShortcut(QKeySequence(tecla), self)
            atajo.activated.connect(
                lambda vid=id_voz: self.pestana_voces.activar_por_id(vid)
            )
            self._atajos.append(atajo)

        # Pánico: Esc → voz Neutral (siempre disponible).
        atajo_neutral = QShortcut(QKeySequence(TECLA_NEUTRAL), self)
        atajo_neutral.activated.connect(
            lambda: self.pestana_voces.activar_por_id(IVoiceProfile.ID_NEUTRAL)
        )
        self._atajos.append(atajo_neutral)

    # ------------------------------------------------------------------ #
    #  Eventos del motor (drenados desde la cola, 10 Hz)
    # ------------------------------------------------------------------ #
    def _drenar_eventos(self) -> None:
        while True:
            try:
                evento = self.eventos.get_nowait()
            except queue.Empty:
                break
            self._manejar_evento(evento)

    def _manejar_evento(self, evento: tuple[str, ...]) -> None:
        tipo = evento[0]
        if tipo == "voz_activada":
            nombre, modo = evento[1], evento[2]
            icono_ia = "  ⚠ latencia alta" if modo == "IA" else ""
            self.etiqueta_estado.setText(f"Voz: {nombre} · Modo: {modo}{icono_ia}")
            self._refrescar_latencia()
        elif tipo == "preview":
            self.banner.mostrar("▶ Cadena temporal activa (no guardada)", "aviso", 4)
        elif tipo == "voz_corrupta":
            self.banner.mostrar(f"⚠ {evento[1]}", "error", 15)
        elif tipo in ("aviso", "ia_fallo"):
            self.banner.mostrar(f"⚠ {evento[1]}", "aviso", 12)
        elif tipo == "ia_gpu":
            self.banner.mostrar(evento[1], "ok", 5)
        elif tipo == "ia_lista":
            self.banner.mostrar(f"🤖 {evento[1]} — Modo IA activo", "ok", 6)
        elif tipo == "error_audio":
            self.banner.mostrar(f"✖ {evento[1]}", "error", 15)
        elif tipo == "aviso_audio":
            pass  # overruns ocasionales: no saturar la UI
        elif tipo == "grabacion_lista":
            self.pestana_voces.al_terminar_grabacion(evento[1])
            if len(evento) > 2 and evento[2]:
                self.banner.mostrar(f"⚠ {evento[2]}", "aviso", 15)
            else:
                self.banner.mostrar(f"💾 Grabación guardada en:\n{evento[1]}", "ok", 12)
        elif tipo == "error_grabacion":
            self.banner.mostrar(f"✖ Error al exportar: {evento[1]}", "error", 15)
        elif tipo == "buffer_cambiado":
            self._refrescar_latencia()

    # ------------------------------------------------------------------ #
    def _refrescar_rec(self) -> None:
        grabador = self.motor.grabador
        segundos = grabador.segundos_transcurridos()
        minutos, resto = divmod(segundos, 60)
        horas, minutos = divmod(minutos, 60)
        self.cronometro.setText(
            f"{horas:02d}:{minutos:02d}:{resto:02d}" if horas else f"{minutos:02d}:{resto:02d}"
        )
        if grabador.grabando:
            self.punto_rec.setStyleSheet("color:#dc2626; font-size:22px;")
        else:
            self.punto_rec.setStyleSheet("color:#9ca3af; font-size:22px;")

    def _parpadear(self) -> None:
        self._rec_visible = not self._rec_visible
        self.punto_rec.setVisible(self._rec_visible or not self.motor.grabador.grabando)

    def _refrescar_latencia(self) -> None:
        self.etiqueta_latencia.setText(f"Latencia ≈ {self.motor.latencia_estimada_ms():.0f} ms")

    # ------------------------------------------------------------------ #
    def _recargar_todo(self) -> None:
        voces = self.gestor_voces.cargar_todas()
        self.gestor_voces.aplicar_atajos(self.config.get("atajos", {}))
        self.pestana_voces.poblar(voces)
        self.pestana_editor.poblar(voces)
        self._reconstruir_ajustes()
        self._montar_atajos()

    def _aplicar_ajustes(self) -> None:
        self._recargar_todo()
        self.banner.mostrar("✔ Ajustes guardados y aplicados", "ok", 5)

    def _reconstruir_ajustes(self) -> None:
        indice = self.pestanas.indexOf(self.pestana_ajustes)
        self.pestana_ajustes = PestanaAjustes(
            self.motor, self.config, self.gestor_voces, self.repo_config,
            self._aplicar_ajustes,
        )
        self.pestanas.removeTab(indice)
        self.pestanas.insertTab(indice, self.pestana_ajustes, "⚙️ Ajustes")

    # ------------------------------------------------------------------ #
    def iniciar_audio(self) -> None:
        self._recargar_todo()
        if not self.motor.iniciar():
            self.banner.mostrar(
                "✖ No se pudo abrir el audio. Revisa Ajustes → dispositivos.", "error", 20
            )

    def closeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        self.motor.detener()
        super().closeEvent(evento)
