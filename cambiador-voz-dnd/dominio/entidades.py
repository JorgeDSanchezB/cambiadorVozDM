"""Entidades de dominio: voces y parámetros (fuertemente tipadas con dataclasses).

Jerarquía:
    IVoiceProfile (ABC)
    ├── PerfilDSP  -> cadena de efectos DSP construida desde JSON
    └── PerfilIA   -> clonación de voz (RVC) + cadena DSP post opcional

Cero hardcoding: los RANGOS de los parámetros viven en `data/parametros.json`
(catálogo) y se inyectan en `validar()`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, fields
from typing import Any, ClassVar

TipoVoz = str  # "DSP" | "IA" (validado en IVoiceProfile.desde_dict)


# --------------------------------------------------------------------------- #
#  Parámetros DSP
# --------------------------------------------------------------------------- #
@dataclass
class ParametrosDSP:
    """Valores de la cadena de efectos. Los rangos canónicos están en el
    catálogo `data/parametros.json` que comparten la Fábrica y el Editor."""

    pitch_semitonos: float = 0.0     # -12..+12
    formant_shift: float = 1.0       # 0.5..2.0 (factor de frecuencia de formantes)
    gain_db: float = 0.0             # -24..+24
    distortion_drive: float = 0.0    # 0..1
    ring_mod_freq: float = 0.0       # 0 = desactivado
    eq_low_db: float = 0.0           # shelf 120 Hz
    eq_mid_db: float = 0.0           # peaking 1.2 kHz
    eq_high_db: float = 0.0          # shelf 6 kHz
    reverb_room_size: float = 0.0    # 0..1 (tamaño sala; también escala wet)
    reverb_damping: float = 0.5      # 0..1 (amortiguación de agudos)

    CAMPOS: ClassVar[frozenset[str]] = frozenset()  # se rellena tras la clase

    @classmethod
    def desde_dict(cls, datos: dict[str, Any] | None) -> "ParametrosDSP":
        """Construye ignorando claves desconocidas (tolerancia a fallos)."""
        datos = datos or {}
        validos = {f.name for f in fields(cls)}
        filtrados = {}
        for clave, valor in datos.items():
            if clave in validos and isinstance(valor, (int, float)) and not isinstance(valor, bool):
                filtrados[clave] = float(valor)
        return cls(**filtrados)

    def a_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}

    def validar(self, catalogo: dict[str, dict]) -> list[str]:
        """Devuelve errores de rango usando el catálogo cargado desde JSON."""
        errores: list[str] = []
        for nombre, rango in (catalogo or {}).items():
            valor = getattr(self, nombre, None)
            if valor is None:
                continue
            if not (float(rango["min"]) - 1e-9 <= float(valor) <= float(rango["max"]) + 1e-9):
                errores.append(
                    f"Parámetro '{nombre}'={valor} fuera de "
                    f"[{rango['min']}, {rango['max']}]"
                )
        return errores

    def es_neutral(self) -> bool:
        """True si todos los parámetros están en su valor neutro (bypass)."""
        neutral = ParametrosDSP()
        return all(
            abs(getattr(self, f.name) - getattr(neutral, f.name)) < 1e-9
            for f in fields(self)
        )


ParametrosDSP.CAMPOS = frozenset(f.name for f in fields(ParametrosDSP))


# --------------------------------------------------------------------------- #
#  Parámetros IA (Modo Avanzado)
# --------------------------------------------------------------------------- #
@dataclass
class ParametrosIA:
    """Configuración del módulo de clonación de voz (RVC u otro plugin)."""

    modelo_rvc: str = ""          # ruta relativa al archivo del modelo (.pth)
    pitch_rvc: int = 0            # transposición del modelo en semitonos
    index_rate: float = 0.5       # 0..1 fuerza del índice de timbre
    usar_gpu: bool = True         # requerir GPU si está disponible

    @classmethod
    def desde_dict(cls, datos: dict[str, Any] | None) -> "ParametrosIA":
        datos = datos or {}
        validos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in validos})

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validar(self) -> list[str]:
        errores: list[str] = []
        if not self.modelo_rvc:
            errores.append("parametros_ia.modelo_rvc está vacío")
        if not (0.0 <= float(self.index_rate) <= 1.0):
            errores.append("parametros_ia.index_rate debe estar en [0, 1]")
        return errores


# --------------------------------------------------------------------------- #
#  Jerarquía de voces
# --------------------------------------------------------------------------- #
@dataclass
class IVoiceProfile(ABC):
    """Contrato raíz para cualquier voz del sistema."""

    TIPOS_VALIDOS: ClassVar[frozenset[str]] = frozenset({"DSP", "IA"})
    ID_NEUTRAL: ClassVar[str] = "00000000-0000-0000-0000-000000000000"

    id: str
    nombre: str
    tipo: TipoVoz
    icono: str = "🎙️"
    color: str = "#6b7280"
    atajo: str | None = None       # se inyecta desde config.json (atajos)

    @abstractmethod
    def validar(self, catalogo: dict[str, dict]) -> list[str]:
        """Valida el perfil contra el catálogo; devuelve lista de errores."""

    def a_dict(self) -> dict[str, Any]:
        base = {
            "id": self.id,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "icono": self.icono,
            "color": self.color,
        }
        return base

    # ---- fábrica polimórfica desde JSON ---------------------------------- #
    @staticmethod
    def desde_dict(datos: dict[str, Any]) -> "IVoiceProfile":
        """Construye PerfilDSP o PerfilIA según el campo `tipo`.

        Lanza ValueError si el JSON es irrecuperable (id/nombre/tipo).
        """
        if not isinstance(datos, dict):
            raise ValueError("El JSON de voz debe ser un objeto")
        tipo = str(datos.get("tipo", "")).upper()
        if tipo not in IVoiceProfile.TIPOS_VALIDOS:
            raise ValueError(f"tipo desconocido: {datos.get('tipo')!r}")
        if not datos.get("id") or not datos.get("nombre"):
            raise ValueError("Toda voz requiere 'id' y 'nombre'")

        comunes = dict(
            id=str(datos["id"]),
            nombre=str(datos["nombre"]),
            tipo=tipo,  # type: ignore[arg-type]
            icono=str(datos.get("icono", "🎙️")),
            color=str(datos.get("color", "#6b7280")),
        )
        if tipo == "DSP":
            return PerfilDSP(
                **comunes,
                parametros_dsp=ParametrosDSP.desde_dict(datos.get("parametros_dsp")),
            )
        return PerfilIA(
            **comunes,
            parametros_ia=ParametrosIA.desde_dict(datos.get("parametros_ia")),
            dsp_post=ParametrosDSP.desde_dict(datos.get("dsp_post")),
        )


@dataclass
class PerfilDSP(IVoiceProfile):
    """Voz procesada 100 % en tiempo real con la cadena DSP (latencia baja)."""

    parametros_dsp: ParametrosDSP = field(default_factory=ParametrosDSP)

    def validar(self, catalogo: dict[str, dict]) -> list[str]:
        return self.parametros_dsp.validar(catalogo)

    def a_dict(self) -> dict[str, Any]:
        return {**super().a_dict(), "parametros_dsp": self.parametros_dsp.a_dict()}


@dataclass
class PerfilIA(IVoiceProfile):
    """Voz por clonación de IA (RVC). Requiere GPU opcional; `dsp_post` se
    aplica después del modelo (ej. reverb de caverna para un dragón)."""

    parametros_ia: ParametrosIA = field(default_factory=ParametrosIA)
    dsp_post: ParametrosDSP = field(default_factory=ParametrosDSP)

    def validar(self, catalogo: dict[str, dict]) -> list[str]:
        return self.parametros_ia.validar() + self.dsp_post.validar(catalogo)

    def a_dict(self) -> dict[str, Any]:
        return {
            **super().a_dict(),
            "parametros_ia": self.parametros_ia.a_dict(),
            "dsp_post": self.dsp_post.a_dict(),
        }
