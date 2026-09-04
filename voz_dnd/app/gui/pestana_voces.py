"""Pestaña "🎤 Voces": lista compacta y buscable (Fase 5.1, rediseño).

Con decenas de voces, la antigua cuadrícula de botones gigantes resultaba
incómoda y difícil de desplazar. Este rediseño la sustituye por una **lista
de filas compactas** (swatch de color · nombre · atajo) agrupada por tipo
(Neutral → IA → DSP) y con un buscador que filtra al instante, dentro de
un área con scroll natural.

Los datos siguen viniendo DESDE JSON (icono, color, nombre, atajo, tipo);
añadir una voz no requiere tocar esta clase. El estilo es coherente con el
tema oscuro de la app, con un único acento cálido (ácaro/antorcha) para la
voz activa.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import IVoiceProfile, TIPO_IA
from app.gui.tema import CLARO, Tema


class PestanaVoces(QWidget):
    senal_voz_seleccionada = pyqtSignal(str)   # id (UUID como str)
    senal_recargar = pyqtSignal()              # re-lee los JSON del disco

    def __init__(self, tema: Tema | None = None):
        super().__init__()
        self._tema = tema or CLARO
        self._voces: list[IVoiceProfile] = []
        self._filas: dict[str, QPushButton] = {}   # id → fila
        self._chips: dict[str, QLabel] = {}        # id → chip del atajo
        self._cabeceras: list[QLabel] = []         # etiquetas de sección
        self._activa: str | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(8)

        # ---- Fila superior: buscador + recargar ----
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("🔍 Buscar voz…")
        self.buscador.setClearButtonEnabled(True)
        self.buscador.setTextMargins(4, 0, 4, 0)
        self.buscador.textChanged.connect(self._filtrar)
        boton_recargar = QPushButton("↻ Recargar")
        boton_recargar.setToolTip("Re-lee las voces de data/voces/")
        boton_recargar.clicked.connect(self.senal_recargar.emit)
        fila.addWidget(self.buscador, 1)
        fila.addWidget(boton_recargar)
        raiz.addLayout(fila)

        self.etiqueta_estado = QLabel("")
        self.etiqueta_estado.setStyleSheet(f"color:{self._tema.muted};")
        raiz.addWidget(self.etiqueta_estado)

        # ---- Contenedor de listado dentro de un área con scroll ----
        self._contenido = QWidget()
        self._lista = QVBoxLayout(self._contenido)
        self._lista.setContentsMargins(0, 0, 0, 0)
        self._lista.setSpacing(4)

        self._aviso_vacio = QLabel(
            "No hay voces que coincidan con tu búsqueda.\n"
            "Cambia el texto para ver todas las voces de nuevo.")
        self._aviso_vacio.setStyleSheet(
            f"color:{self._tema.muted};padding:28px;font-size:13px;")
        self._aviso_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._aviso_vacio.setWordWrap(True)
        self._aviso_vacio.setVisible(False)
        self._lista.addWidget(self._aviso_vacio)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._contenido)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        self._scroll = scroll
        raiz.addWidget(scroll, 1)

    # ------------------------------ API ---------------------------------- #
    def poblar(self, voces: list[IVoiceProfile], seleccionar_id: str | None = None) -> None:
        self._voces = voces
        self._activa = str(seleccionar_id) if seleccionar_id is not None else None
        self._limpiar_lista()
        self._reconstruir_agrupado()
        self.buscador.clear()
        self.set_estado("")
        self._fijar_altura()

    def marcar_activa(self, id_voz: str) -> None:
        self._activa = str(id_voz)
        self._refrescar_estilos_filas()
        fila = self._filas.get(str(id_voz))
        if fila is not None:
            self._scroll.ensureWidgetVisible(
                fila, 8, 8)  # mantiene la voz activa a la vista

    def set_estado(self, texto: str) -> None:
        self.etiqueta_estado.setText(texto)

    def set_tema(self, tema: Tema) -> None:
        """Cambia el tema de la tabla de voces (modo claro/oscuro)."""
        self._tema = tema
        t = self._tema
        self.etiqueta_estado.setStyleSheet(f"color:{t.muted};")
        self._aviso_vacio.setStyleSheet(
            f"color:{t.muted};padding:28px;font-size:13px;")
        for cabecera in self._cabeceras:
            cabecera.setStyleSheet(
                f"color:{t.muted};font-size:11px;font-weight:700;"
                f"padding:8px 2px 2px 2px;letter-spacing:1px;")
        for id_voz, chip in self._chips.items():
            chip.setStyleSheet(self._estilo_chip())
        self._refrescar_estilos_filas()

    # --------------------------- internos -------------------------------- #
    def _limpiar_lista(self) -> None:
        self._filas.clear()
        self._chips.clear()
        self._cabeceras.clear()
        # Conserva el aviso de lista vacía; el resto (cabeceras + filas) se borra.
        for i in reversed(range(self._lista.count())):
            widget = self._lista.itemAt(i).widget()
            if widget is not None and widget is not self._aviso_vacio:
                self._lista.takeAt(i)
                widget.deleteLater()
        self._aviso_vacio.setVisible(False)

    def _reconstruir_agrupado(self) -> None:
        # Orden: Neutral (debe existir) → IA → DSP, alfabético dentro.
        neutras = [v for v in self._voces if v.nombre.strip().lower() == "neutral"]
        ia = [v for v in self._voces if v.tipo == TIPO_IA]
        dsp = [v for v in self._voces if v not in neutras and v.tipo != TIPO_IA]
        ordenadas = (sorted(neutras, key=lambda v: v.nombre)
                     + sorted(ia, key=lambda v: v.nombre)
                     + sorted(dsp, key=lambda v: v.nombre))

        seccion_anterior = None
        for voz in ordenadas:
            seccion = self._seccion_de(voz)
            if seccion != seccion_anterior:
                self._lista.addWidget(self._titulo_seccion(seccion))
                seccion_anterior = seccion
            fila = self._construir_fila(voz)
            self._lista.addWidget(fila)
            self._filas[str(voz.id)] = fila

    @staticmethod
    def _seccion_de(voz: IVoiceProfile) -> str:
        if voz.nombre.strip().lower() == "neutral":
            return "Voz base"
        if voz.tipo == TIPO_IA:
            return "Personajes IA"
        return "Personajes"

    def _titulo_seccion(self, nombre: str) -> QLabel:
        etiqueta = QLabel(nombre)
        etiqueta.setProperty("seccion", nombre)
        etiqueta.setStyleSheet(
            f"color:{self._tema.muted};font-size:11px;font-weight:700;"
            f"padding:8px 2px 2px 2px;letter-spacing:1px;")
        self._cabeceras.append(etiqueta)
        return etiqueta

    def _construir_fila(self, voz: IVoiceProfile) -> QPushButton:
        fila = QPushButton()
        fila.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        fila.setToolTip(self._tooltip_de(voz))
        fila.setProperty("id_fila", str(voz.id))
        fila.setStyleSheet(self._estilo_fila(str(voz.id) == self._activa))

        dise = QHBoxLayout(fila)
        dise.setContentsMargins(12, 8, 12, 8)
        dise.setSpacing(10)

        charm = QLabel("")
        charm.setFixedSize(16, 16)
        charm.setStyleSheet(
            f"background:{voz.color};border-radius:5px;border:1px solid #00000055;")
        charm.setToolTip(voz.tipo)

        nombre = QLabel(voz.nombre)
        nombre.setStyleSheet(
            f"color:{self._tema.texto};font-size:14px;font-weight:600;")

        dise.addWidget(charm)
        dise.addWidget(nombre, 1)

        if voz.atajo:
            chip = QLabel(voz.atajo)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(self._estilo_chip())
            chip.setToolTip(f"Atajo de teclado: {voz.atajo}")
            self._chips[str(voz.id)] = chip
            dise.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)

        fila.clicked.connect(
            lambda _=False, id_voz=str(voz.id): self.senal_voz_seleccionada.emit(id_voz))
        fila.setObjectName("fila_voz")
        return fila

    @staticmethod
    def _tooltip_de(voz: IVoiceProfile) -> str:
        base = f"{voz.nombre} · modo {'IA' if voz.tipo == TIPO_IA else 'DSP'}"
        if voz.atajo:
            base += f" · atajo {voz.atajo}"
        return base

    def _filtrar(self, texto: str) -> None:
        texto = texto.strip().lower()
        hay_texto = bool(texto)
        visibles = 0
        for id_voz, fila in self._filas.items():
            voz = self._voz_por_id(id_voz)
            coincide = voz is not None and (
                not hay_texto
                or texto in voz.nombre.lower()
                or texto in str(voz.atajo or "").lower())
            fila.setVisible(coincide)
            if coincide:
                visibles += 1
        self._actualizar_cabeceras()
        self._fijar_altura()
        # Aviso de lista vacía: solo cuando hay texto y nada coincide.
        self._aviso_vacio.setVisible(hay_texto and visibles == 0 and bool(self._voces))

    def _actualizar_cabeceras(self) -> None:
        """Muestra cada cabecera solo si su sección tiene alguna fila visible."""
        items = [self._lista.itemAt(i) for i in range(self._lista.count())]
        for idx, item in enumerate(items):
            cabecera = item.widget()
            if not isinstance(cabecera, QLabel) or cabecera.property("seccion") is None:
                continue
            visible = False
            for j in range(idx + 1, len(items)):
                w = items[j].widget()
                if not isinstance(w, QWidget) or w is self._aviso_vacio:
                    continue
                if isinstance(w, QLabel) and w is not cabecera \
                        and w.property("seccion") is not None:
                    break  # siguiente cabecera: se acabó la sección
                if w.isVisible() and w.property("id_fila") is not None:
                    visible = True
                    break
            cabecera.setVisible(visible)

    def _refrescar_estilos_filas(self) -> None:
        for id_voz, fila in self._filas.items():
            activo = id_voz == self._activa
            fila.setStyleSheet(self._estilo_fila(activo))

    def _fijar_altura(self) -> None:
        """Ancla la altura mínima del contenido para que el scroll nunca colapse.

        Con `widgetResizable(True)` el área intenta caber la lista en el
        viewport; si solo se deja al layout la altura natural, en el primer
        render puede encoger el contenido y "perder" voces hacia abajo.
        Al fijar la altura mínima a `sizeHint()` (que solo cuenta filas
        visibles), el scroll se mantiene correcto aunque haya muchas voces
        y se actualiza al filtrar.
        """
        self._contenido.setMinimumHeight(self._contenido.sizeHint().height())

    def _voz_por_id(self, id_voz: str | None) -> IVoiceProfile | None:
        if id_voz is None:
            return None
        for voz in self._voces:
            if str(voz.id) == id_voz:
                return voz
        return None

    def _estilo_fila(self, activo: bool) -> str:
        t = self._tema
        if activo:
            return (
                f"QPushButton{{background:{t.acento_suave};border:1px solid {t.acento};"
                f"border-left:4px solid {t.acento};border-radius:6px;"
                f"color:{t.acento_texto};}}"
                f"QPushButton:hover{{background:{t.acento_suave};}}")
        return (
            f"QPushButton{{background:{t.fila};border:1px solid {t.fila_borde};"
            f"border-radius:6px;color:{t.texto};}}"
            f"QPushButton:hover{{background:{t.fila_hover};border:1px solid {t.fila_borde_hover};}}"
            f"QPushButton:pressed{{background:{t.fila_pressed};}}")

    def _estilo_chip(self) -> str:
        t = self._tema
        return (
            f"color:{t.chip_texto};background:{t.chip_bg};border:1px solid {t.chip_borde};"
            f"border-radius:8px;padding:2px 8px;font-size:11px;")
