"""Procesadores de voz: unidad intercambiable que usa el callback de audio.

ProcesadorDSP  → cadena de efectos local (modo base).
ProcesadorIA   → módulo RVC opcional + cadena DSP post (modo avanzado).
ProcesadorBypass → paso recto (voz Neutral / emergencia).

El MotorAudio intercambia la REFERENCIA al procesador de forma atómica
(sin locks) desde el hilo de la GUI: es seguro bajo el GIL de CPython.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

from app.domain.models import IVoiceProfile, PerfilDSP, PerfilIA
from app.engine.fabrica_cadena import ConfigCadena, FabricaCadena
from app.engine.modulo_ia import ModuloIA

log = logging.getLogger(__name__)


class ProcesadorBase(ABC):
    degradado: bool = False  # True → avisar en la UI (p. ej. IA caída a DSP)

    def __init__(self, perfil: IVoiceProfile | None):
        self.perfil = perfil
        self.id_voz = perfil.id if perfil is not None else None

    @abstractmethod
    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray: ...

    def preparar(self) -> None:
        """Carga diferida (solo ProcesadorIA la implementa)."""

    @property
    def latencia_muestras(self) -> int:
        return 0

    @property
    def nombre(self) -> str:
        return self.perfil.nombre if self.perfil is not None else "—"


class ProcesadorBypass(ProcesadorBase):
    """Paso recto: voz Neutral o modo de emergencia (nunca bloquea)."""

    def __init__(self):
        super().__init__(None)

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        return bloque


class ProcesadorDSP(ProcesadorBase):
    def __init__(self, perfil: PerfilDSP, sr: int, cfg: ConfigCadena,
                 fabrica: FabricaCadena):
        super().__init__(perfil)
        self._cadena = fabrica.construir(perfil.parametros_dsp, sr, cfg)

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        for efecto in self._cadena:
            bloque = efecto.procesar(bloque, sr)
        return bloque

    def reset(self) -> None:
        for efecto in self._cadena:
            efecto.reset()

    @property
    def latencia_muestras(self) -> int:
        return FabricaCadena.latencia_total(self._cadena)


class ProcesadorIA(ProcesadorBase):
    """Modo avanzado: RVC (si está disponible) + cadena DSP post del perfil.

    Degradación con gracia: mientras el modelo carga, o si falla (sin GPU,
    paquete ausente, modelo corrupto), sigue sonando SOLO la cadena DSP post
    y `degradado` se marca para que la UI muestre el aviso correspondiente.
    """

    def __init__(self, perfil: PerfilIA, sr: int, cfg: ConfigCadena,
                 fabrica: FabricaCadena, motor_ia: ModuloIA):
        super().__init__(perfil)
        self._motor_ia = motor_ia
        self._cadena_post = fabrica.construir(perfil.dsp_post, sr, cfg)
        self.degradado = not motor_ia.esta_listo()

    def preparar(self) -> None:
        """LLAMAR DESDE UN HILO EN SEGUNDO PLANO (nunca desde el de audio)."""
        self._motor_ia.inicializar()
        if self._motor_ia.error:
            self.degradado = True
            log.warning("ProcesadorIA degradado: %s", self._motor_ia.error)
        else:
            self.degradado = False

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        salida = bloque
        if self._motor_ia.esta_listo():
            try:
                salida = self._motor_ia.procesar(bloque, sr)
            except Exception as exc:  # noqa: BLE001 — el audio nunca debe morir
                self.degradado = True
                log.exception("Fallo de inferencia IA; se continúa con DSP: %s", exc)
        for efecto in self._cadena_post:
            salida = efecto.procesar(salida, sr)
        return salida

    @property
    def latencia_muestras(self) -> int:
        return (self._motor_ia.latencia_muestras
                + FabricaCadena.latencia_total(self._cadena_post))
