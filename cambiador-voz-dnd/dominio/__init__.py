"""Capa de dominio: entidades puras del sistema de voces.

Regla de arquitectura: este paquete NO importa PyQt6, sounddevice ni realiza
I/O. Solo modela el lenguaje del negocio (voces, parámetros, efectos).
"""
from dominio.entidades import (
    IVoiceProfile,
    ParametrosDSP,
    ParametrosIA,
    PerfilDSP,
    PerfilIA,
)
from dominio.fabrica_cadena import FabricaCadena

__all__ = [
    "IVoiceProfile",
    "ParametrosDSP",
    "ParametrosIA",
    "PerfilDSP",
    "PerfilIA",
    "FabricaCadena",
]
