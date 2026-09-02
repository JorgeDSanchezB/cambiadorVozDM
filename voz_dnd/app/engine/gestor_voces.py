"""GestorVoces (Fase 2/5): CRUD de voces en data/voces/*.json.

Tolerancia a fallos:
  * Un JSON corrupto se OMITE y se reporta como error (la GUI muestra un
    banner); el resto de voces carga con normalidad.
  * La voz "Neutral" se regenera sola si falta o está dañada.
  * Los valores fuera de rango se RECORTAN al rango del catálogo con aviso.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from app.domain.catalogo import CatalogoParametros
from app.domain.models import (
    IVoiceProfile,
    ParametrosDSP,
    PerfilDSP,
    TIPO_DSP,
    TIPO_IA,
    VozCorruptaError,
    voz_desde_dict,
)

log = logging.getLogger(__name__)


@dataclass
class CargaVoces:
    voces: list[IVoiceProfile] = field(default_factory=list)
    errores: list[tuple[str, str]] = field(default_factory=list)  # (archivo, mensaje)


def _slug(nombre: str) -> str:
    """Nombre de archivo seguro a partir del nombre de la voz."""
    normalizado = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in normalizado if not unicodedata.combining(c))
    limpio = "".join(c.lower() if c.isalnum() else "_" for c in sin_tildes)
    return limpio.strip("_") or "voz"


class GestorVoces:
    ID_NEUTRA = UUID("00000000-0000-0000-0000-000000000001")

    def __init__(self, carpeta: Path, catalogo: CatalogoParametros):
        self._carpeta = carpeta
        self._catalogo = catalogo
        carpeta.mkdir(parents=True, exist_ok=True)
        self._voces: dict[UUID, IVoiceProfile] = {}

    # ------------------------------ carga -------------------------------- #
    def cargar_todas(self) -> CargaVoces:
        self._voces.clear()
        carga = CargaVoces()
        for archivo in sorted(self._carpeta.glob("*.json")):
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
                voz = voz_desde_dict(datos)
                if isinstance(voz, PerfilDSP):
                    voz.parametros_dsp, avisos = self._catalogo.abrazar(voz.parametros_dsp)
                    for aviso in avisos:
                        carga.errores.append((archivo.name, aviso))
                self._voces[voz.id] = voz
            except (json.JSONDecodeError, VozCorruptaError, ValueError,
                    KeyError, OSError) as exc:
                carga.errores.append((archivo.name, f"Archivo dañado y omitido: {exc}"))
                log.warning("Voz dañada %s: %s", archivo.name, exc)
        self._asegurar_neutral(carga)
        carga.voces = sorted(self._voces.values(), key=lambda v: v.nombre.lower())
        return carga

    def _asegurar_neutral(self, carga: CargaVoces) -> None:
        if self.ID_NEUTRA not in self._voces:
            neutral = self.crear_neutral()
            ruta = self.guardar(neutral)
            carga.errores.append((ruta.name, "Faltaba la voz Neutral: se regeneró."))

    def crear_neutral(self) -> PerfilDSP:
        return PerfilDSP(
            id=self.ID_NEUTRA,
            nombre="Neutral",
            tipo=TIPO_DSP,
            icono="🛡️",
            color="#4a5d3a",
            atajo=None,
            parametros_dsp=ParametrosDSP(),
        )

    # ------------------------- consulta / CRUD --------------------------- #
    def todas(self) -> list[IVoiceProfile]:
        return sorted(self._voces.values(), key=lambda v: v.nombre.lower())

    def por_id(self, id_voz) -> IVoiceProfile | None:
        try:
            return self._voces.get(UUID(str(id_voz)))
        except (ValueError, AttributeError, TypeError):
            return None

    def guardar(self, voz: IVoiceProfile) -> Path:
        errores = voz.validar()
        if errores:
            raise VozCorruptaError("; ".join(errores))
        if isinstance(voz, PerfilDSP):
            voz.parametros_dsp, _ = self._catalogo.abrazar(voz.parametros_dsp)
        elif isinstance(voz, IVoiceProfile) and voz.tipo == TIPO_IA:
            pass  # los rangos IA se validan al usar el modelo
        ruta = self._carpeta / f"{_slug(voz.nombre)}.json"
        ruta.write_text(
            json.dumps(voz.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._voces[voz.id] = voz
        log.info("Voz guardada: %s → %s", voz.nombre, ruta.name)
        return ruta

    def eliminar(self, id_voz) -> bool:
        try:
            id_voz = UUID(str(id_voz))
        except (ValueError, AttributeError, TypeError):
            return False
        if id_voz == self.ID_NEUTRA:
            return False  # la voz Neutral nunca se elimina
        voz = self._voces.pop(id_voz, None)
        if voz is None:
            return False
        ruta = self._carpeta / f"{_slug(voz.nombre)}.json"
        if ruta.exists():
            ruta.unlink()
        log.info("Voz eliminada: %s", voz.nombre)
        return True
