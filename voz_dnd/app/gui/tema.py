"""Tema visual de la interfaz (modo oscuro / claro).

Centraliza los colores de la app (antes dispersos en QSS e inline styles)
en tokens con dos presets: `OSCURO` (la identidad original de la app) y
`CLARO` (variante "pergamino"/luz diurna para una mesa de DM bien iluminada).

El único acento de marca es la "antorcha" (`acento`): se gasta en un solo
lugar, la voz activa de la pestaña Voces, y el resto de la UI se mantiene
discreto. `estilo_global(tema)` produce el QSS global que la ventana
principal aplica a toda la app.
"""
from __future__ import annotations

from dataclasses import dataclass

NOMBRE_OSCURO = "oscuro"
NOMBRE_CLARO = "claro"


@dataclass(frozen=True)
class Tema:
    nombre: str
    base: str            # fondo de ventana
    panel: str           # paneles / pane de pestañas
    borde: str           # bordes generales
    texto: str           # texto principal
    muted: str           # texto secundario (etiquetas, chis)
    tenue: str           # texto tenue (pie)
    acento: str          # único acento de marca (antorcha)
    acento_suave: str    # fondo de la voz activa
    acento_texto: str    # texto sobre el acento
    fila: str            # fondo de fila
    fila_hover: str      # fondo de fila al pasar el ratón
    fila_pressed: str    # fondo de fila al pulsar
    fila_borde: str
    fila_borde_hover: str
    chip_bg: str
    chip_borde: str
    chip_texto: str
    input_bg: str
    tab_bg: str
    tab_bg_sel: str
    reloj: str


# ------------------------- preset oscuro (identidad) ----------------------- #
OSCURO = Tema(
    nombre=NOMBRE_OSCURO,
    base="#14161a",
    panel="#191c22",
    borde="#2a2e36",
    texto="#cfd6e0",
    muted="#9aa4b2",
    tenue="#7d8590",
    acento="#d98e4a",
    acento_suave="#3a3126",
    acento_texto="#ffe4c4",
    fila="#1c2027",
    fila_hover="#232833",
    fila_pressed="#262c36",
    fila_borde="#262c36",
    fila_borde_hover="#333a47",
    chip_bg="#232832",
    chip_borde="#333a47",
    chip_texto="#9aa4b2",
    input_bg="#10131a",
    tab_bg="#1f232b",
    tab_bg_sel="#191c22",
    reloj="#ff6b6b",
)

# ------------------- preset claro (pergamino / luz diurna) ----------------- #
CLARO = Tema(
    nombre=NOMBRE_CLARO,
    base="#f2efe7",
    panel="#ffffff",
    borde="#cfc7b4",
    texto="#1f2126",
    muted="#474c53",
    tenue="#565c64",
    acento="#b4571e",
    acento_suave="#f5e4d3",
    acento_texto="#5a2c0d",
    fila="#ffffff",
    fila_hover="#f3eee1",
    fila_pressed="#ece5d5",
    fila_borde="#ddd6c2",
    fila_borde_hover="#bcae91",
    chip_bg="#f2eee4",
    chip_borde="#cfc7b4",
    chip_texto="#474c53",
    input_bg="#ffffff",
    tab_bg="#e6e1d2",
    tab_bg_sel="#ffffff",
    reloj="#c0392b",
)

_TEMAS: dict[str, Tema] = {t.nombre: t for t in (OSCURO, CLARO)}


def tema_por_nombre(nombre: str) -> Tema:
    """Devuelve el preset de tema; nombre inválido cae en claro."""
    return _TEMAS.get(nombre, CLARO)


def estilo_global(tema: Tema) -> str:
    """QSS global equivalente al ESTILO original, pero parametrizado."""
    return f"""
QMainWindow {{ background: {tema.base}; }}
QTabWidget::pane {{ border: 1px solid {tema.borde}; border-radius: 6px;
                   background: {tema.panel}; }}
QTabBar::tab {{ background: {tema.tab_bg}; color: {tema.muted};
               padding: 8px 18px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ background: {tema.tab_bg_sel}; color: {tema.texto};
                        font-weight: 700; }}
QWidget {{ color: {tema.texto}; font-size: 13px; }}
QLabel#titulo {{ color: {tema.texto}; font-size: 17px; font-weight: 700; }}
QLabel#reloj {{ color: {tema.reloj}; font-size: 16px; font-weight: 700; }}
QLabel#latencia {{ color: {tema.muted}; font-size: 12px; }}
QPushButton {{ min-height: 30px; background: {tema.tab_bg};
              border: 1px solid {tema.fila_borde_hover};
              border-radius: 6px; padding: 4px 12px; }}
QPushButton:hover {{ background: {tema.fila_hover}; }}
QGroupBox {{ border: 1px solid {tema.borde}; border-radius: 8px;
            margin-top: 10px; padding: 10px; font-weight: 600; }}
QGroupBox::title {{ color: {tema.muted}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
     background: {tema.input_bg}; color: {tema.texto};
     border: 1px solid {tema.fila_borde_hover};
     border-radius: 4px; padding: 4px; }}
QCheckBox {{ color: {tema.texto}; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QScrollArea {{ background: {tema.panel}; border: none; }}
"""
