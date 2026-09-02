"""Fábrica de cadenas DSP (Fase 4): JSON → lista de efectos.

Regla de la "Voz Nueva": la cadena se construye DINÁMICAMENTE a partir de
ParametrosDSP. Los efectos en valor neutro NO se instancian → cadena mínima
= latencia mínima. Añadir una voz jamás requiere tocar este código.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.catalogo import CatalogoParametros
from app.domain.efectos import (
    EfectoEQ,
    Ganancia,
    IEfectoDSP,
    PitchShifter,
    ReverbSchroeder,
    Distorsion,
    RingMod,
    FormantShifter,
)
from app.domain.models import ParametrosDSP


@dataclass(frozen=True)
class ConfigCadena:
    """Ajustes de motor que afectan a la construcción de efectos."""
    tam_grano_pitch: int = 1024
    umbral_activacion: float = 1e-3   # por debajo → efecto omitido


class FabricaCadena:
    """Construye la cadena de efectos en el orden acústico correcto:

        Ganancia → Pitch → Formante → Distorsión → RingMod → EQ → Reverb

    Justificación del orden: el pitch se aplica sobre señal "limpia" (evita
    acentuar artefactos de distorsión), y la reverb SIEMPRE al final porque
    define el espacio acústico después de esculpir el timbre.
    """

    def __init__(self, catalogo: CatalogoParametros):
        self._catalogo = catalogo

    def construir(self, p: ParametrosDSP, sr: int, cfg: ConfigCadena) -> list[IEfectoDSP]:
        u = cfg.umbral_activacion
        cadena: list[IEfectoDSP] = []

        if abs(p.gain_db) > u:
            cadena.append(Ganancia(p.gain_db))

        if abs(p.pitch_semitonos) > u:
            cadena.append(PitchShifter(sr, p.pitch_semitonos, cfg.tam_grano_pitch))

        if abs(p.formant_shift - self._catalogo.def_de("formant_shift").neutro) > u:
            cadena.append(FormantShifter(sr, p.formant_shift))

        if p.distortion_drive > u:
            cadena.append(Distorsion(p.distortion_drive))

        if p.ring_mod_freq > u:
            cadena.append(RingMod(sr, p.ring_mod_freq))

        if any(abs(v) > u for v in (p.eq_low_db, p.eq_mid_db, p.eq_high_db)):
            cadena.append(EfectoEQ(sr, p.eq_low_db, p.eq_mid_db, p.eq_high_db))

        if p.reverb_room_size > u:
            cadena.append(ReverbSchroeder(sr, p.reverb_room_size, p.reverb_damping))

        return cadena

    def es_neutra(self, p: ParametrosDSP) -> bool:
        return self._catalogo.es_neutra(p)

    @staticmethod
    def latencia_total(cadena: list[IEfectoDSP]) -> int:
        return sum(efecto.latencia_muestras for efecto in cadena)
