"""Entidades del dominio (Fase 2 del diseño).

- IVoiceProfile : contrato raíz de toda voz (DSP o IA).
- PerfilDSP     : voz procesada con una cadena de efectos local.
- PerfilIA      : voz clonada con RVC (opcional) + cadena DSP post.

Cero hardcoding: los RANGOS válidos de cada parámetro viven en
data/parametros.json (CatalogoParametros) y la PERSISTENCIA en
data/voces/*.json. Nada de números mágicos en la lógica.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from uuid import UUID, uuid4

TIPO_DSP = "DSP"
TIPO_IA = "IA"


class VozCorruptaError(ValueError):
    """El JSON de una voz se pudo leer pero su contenido es inválido."""


@dataclass
class ParametrosDSP:
    """Parámetros de la cadena DSP. Cada valor 'neutro' desactiva su efecto.

    Los rangos reales (min/max/paso) NO están aquí: viven en
    data/parametros.json y los interpreta CatalogoParametros.
    """
    pitch_semitonos: float = 0.0     # neutro 0.0  (±12 semitonos)
    formant_shift: float = 1.0       # neutro 1.0  (<1 garganta pequeña, >1 grande)
    reverb_room_size: float = 0.0    # neutro 0.0  (0..1, mezcla "wet")
    reverb_damping: float = 0.5      #             (0..1, amortiguación de agudos)
    distortion_drive: float = 0.0    # neutro 0.0  (0..1)
    gain_db: float = 0.0             # neutro 0.0  (dB)
    ring_mod_freq: float = 0.0       # neutro 0.0  (0 = desactivado, Hz)
    eq_low_db: float = 0.0           # shelf 120 Hz
    eq_mid_db: float = 0.0           # peaking 1.2 kHz
    eq_high_db: float = 0.0          # shelf 6 kHz


@dataclass
class ParametrosIA:
    """Parámetros del modo avanzado (clonación RVC). Opcional."""
    modelo_rvc: str = ""             # ruta al modelo .pth
    pitch_rvc: int = 0               # corrección de tono en semitonos
    index_rate: float = 0.66         # 0..1 (mezcla del índice de hablante)
    usar_gpu: bool = True            # se degrada a CPU/GPU ausente con aviso


@dataclass
class IVoiceProfile(ABC):
    """Contrato raíz para toda voz del sistema."""
    id: UUID = field(default_factory=uuid4)
    nombre: str = "Sin nombre"
    tipo: str = TIPO_DSP
    icono: str = "🎙️"
    color: str = "#4a5d3a"
    atajo: str | None = None

    @abstractmethod
    def validar(self) -> list[str]:
        """Devuelve la lista de errores de validación (vacía = perfil sano)."""

    @abstractmethod
    def a_dict(self) -> dict[str, Any]:
        """Serializa a un dict compatible con data/voces/*.json."""


@dataclass
class PerfilDSP(IVoiceProfile):
    parametros_dsp: ParametrosDSP = field(default_factory=ParametrosDSP)

    def validar(self) -> list[str]:
        errores: list[str] = []
        if not self.nombre.strip():
            errores.append("El nombre de la voz está vacío.")
        return errores

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "tipo": self.tipo,
            "icono": self.icono,
            "color": self.color,
            "atajo": self.atajo,
            "parametros_dsp": asdict(self.parametros_dsp),
        }


@dataclass
class PerfilIA(IVoiceProfile):
    parametros_ia: ParametrosIA = field(default_factory=ParametrosIA)
    dsp_post: ParametrosDSP = field(default_factory=ParametrosDSP)

    def validar(self) -> list[str]:
        errores: list[str] = []
        if not self.nombre.strip():
            errores.append("El nombre de la voz está vacío.")
        if not self.parametros_ia.modelo_rvc:
            errores.append("Voz IA sin modelo RVC asignado (parametros_ia.modelo_rvc).")
        return errores

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "tipo": self.tipo,
            "icono": self.icono,
            "color": self.color,
            "atajo": self.atajo,
            "parametros_ia": asdict(self.parametros_ia),
            "dsp_post": asdict(self.dsp_post),
        }


def _fl(d: dict, clave: str, defecto: float) -> float:
    valor = d.get(clave, defecto)
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise VozCorruptaError(f"Valor no numérico en '{clave}': {valor!r}") from exc


def voz_desde_dict(d: dict) -> IVoiceProfile:
    """Deserializa un dict JSON a PerfilDSP o PerfilIA.

    Tolerancia a fallos: claves ausentes → valores por defecto;
    tipos incorrectos → VozCorruptaError (el GestorVoces omite el archivo
    y avisa, y el sistema cae a la voz Neutral).
    """
    if not isinstance(d, dict):
        raise VozCorruptaError("El JSON raíz no es un objeto.")

    tipo = d.get("tipo", TIPO_DSP)
    if tipo not in (TIPO_DSP, TIPO_IA):
        raise VozCorruptaError(f"Tipo de voz desconocido: {tipo!r}")

    try:
        id_voz = UUID(str(d.get("id", "")))
    except (ValueError, AttributeError, TypeError):
        id_voz = uuid4()  # id ausente/roto: se regenera (no invalida la voz)

    base: dict[str, Any] = {
        "id": id_voz,
        "nombre": str(d.get("nombre") or "Sin nombre"),
        "tipo": tipo,
        "icono": str(d.get("icono") or "🎙️"),
        "color": str(d.get("color") or "#4a5d3a"),
        "atajo": d.get("atajo") if isinstance(d.get("atajo"), str) else None,
    }

    if tipo == TIPO_DSP:
        pd = d.get("parametros_dsp", {})
        if not isinstance(pd, dict):
            raise VozCorruptaError("'parametros_dsp' debe ser un objeto.")
        neutros = ParametrosDSP()
        kwargs = {f.name: _fl(pd, f.name, getattr(neutros, f.name))
                  for f in fields(ParametrosDSP)}
        return PerfilDSP(**base, parametros_dsp=ParametrosDSP(**kwargs))

    # ---- Tipo IA ----
    pi = d.get("parametros_ia", {})
    if not isinstance(pi, dict):
        raise VozCorruptaError("'parametros_ia' debe ser un objeto.")
    p_ia = ParametrosIA(
        modelo_rvc=str(pi.get("modelo_rvc", "")),
        pitch_rvc=int(_fl(pi, "pitch_rvc", 0.0)),
        index_rate=_fl(pi, "index_rate", 0.66),
        usar_gpu=bool(pi.get("usar_gpu", True)),
    )
    post = d.get("dsp_post", {})
    if not isinstance(post, dict):
        post = {}
    neutros = ParametrosDSP()
    kwargs_post = {f.name: _fl(post, f.name, getattr(neutros, f.name))
                   for f in fields(ParametrosDSP)}
    return PerfilIA(**base, parametros_ia=p_ia, dsp_post=ParametrosDSP(**kwargs_post))
