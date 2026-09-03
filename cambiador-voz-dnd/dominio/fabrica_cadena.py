"""Fábrica de cadenas de efectos: convierte parámetros JSON → pipeline DSP.

Regla de la "Voz Nueva": añadir una voz NUNCA toca este archivo. La cadena
se construye dinámicamente instanciando SOLO los efectos con parámetros
activos (cadena mínima = latencia mínima).
"""
from __future__ import annotations

import numpy as np

from dominio.efectos import (
    BiquadEQ,
    Distorsion,
    FormantShifter,
    Ganancia,
    IEfectoDSP,
    PitchShifter,
    Reverb,
    RingMod,
    FREC_EQ_AGUDOS_HZ,
    FREC_EQ_GRAVES_HZ,
    FREC_EQ_MEDIOS_HZ,
)
from dominio.entidades import ParametrosDSP

# Orden acústico justificado en la Fase 4:
# ganancia → pitch → formantes → distorsión → ring mod → EQ → reverb.
_ORDEN_DOCUMENTADO = (
    "Ganancia, PitchShifter, FormantShifter, Distorsion, RingMod, EQ x3, Reverb"
)


class FabricaCadena:
    """Constructor de la cadena de responsabilidad a partir de ParametrosDSP."""

    @staticmethod
    def construir(p: ParametrosDSP, sr: int) -> list[IEfectoDSP]:
        cadena: list[IEfectoDSP] = []

        if abs(p.gain_db) > 1e-6:
            cadena.append(Ganancia(sr, p.gain_db))

        if abs(p.pitch_semitonos) > 1e-6:
            ratio = 2.0 ** (p.pitch_semitonos / 12.0)
            cadena.append(PitchShifter(sr, ratio))

        if abs(p.formant_shift - 1.0) > 1e-3:
            cadena.append(FormantShifter(sr, p.formant_shift))

        if p.distortion_drive > 1e-6:
            cadena.append(Distorsion(sr, p.distortion_drive))

        if p.ring_mod_freq > 0.0:
            cadena.append(RingMod(sr, p.ring_mod_freq))

        if abs(p.eq_low_db) > 1e-6:
            cadena.append(BiquadEQ(sr, "low_shelf", FREC_EQ_GRAVES_HZ, p.eq_low_db))
        if abs(p.eq_mid_db) > 1e-6:
            cadena.append(BiquadEQ(sr, "peaking", FREC_EQ_MEDIOS_HZ, p.eq_mid_db))
        if abs(p.eq_high_db) > 1e-6:
            cadena.append(BiquadEQ(sr, "high_shelf", FREC_EQ_AGUDOS_HZ, p.eq_high_db))

        if p.reverb_room_size > 1e-6:
            cadena.append(Reverb(sr, p.reverb_room_size, p.reverb_damping))

        return cadena

    @staticmethod
    def latencia_total_muestras(cadena: list[IEfectoDSP]) -> int:
        return sum(efecto.latencia_muestras for efecto in cadena)

    @staticmethod
    def probar_cadena(cadena: list[IEfectoDSP], bloque: np.ndarray, sr: int) -> np.ndarray:
        """Utilidad: ejecuta una señal por la cadena (usada por autoverificación)."""
        y = bloque.astype(np.float32, copy=False)
        for efecto in cadena:
            y = efecto.procesar(y, sr)
        return y
