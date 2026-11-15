"""GestorVoces (Fase 2/5): CRUD de voces en data/voces/*.json.

Tolerancia a fallos:
  * Un JSON corrupto se OMITE y se reporta como error (la GUI muestra un
    banner); el resto de voces carga con normalidad.
  * La voz "Neutral" se regenera sola si falta o está dañada.
  * Los valores fuera de rango se RECORTAN al rango del catálogo con aviso.

Invariante de integridad (una voz = un archivo, decisión 001):
  * Renombrar una voz borra su JSON anterior: antes el archivo viejo
    sobrevivía con el MISMO id y, al recargar, el orden alfabético decidía
    cuál ganaba (el renombre podía revertirse solo).
  * Dos voces con nombres que producen el mismo slug ("Dragón!" y "dragón")
    no se pisan: la segunda se guarda con sufijo -2, -3…
  * Al cargar, un id duplicado (fantasma manual) se resuelve por el archivo
    canónico (nombre == slug) y el residuo se reporta como aviso.
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
        self._rutas: dict[UUID, Path] = {}   # id → archivo real en disco

    # ------------------------------ carga -------------------------------- #
    def cargar_todas(self) -> CargaVoces:
        self._voces.clear()
        self._rutas.clear()
        carga = CargaVoces()
        for archivo in sorted(self._carpeta.glob("*.json")):
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
                voz = voz_desde_dict(datos)
                if isinstance(voz, PerfilDSP):
                    voz.parametros_dsp, avisos = self._catalogo.abrazar(voz.parametros_dsp)
                    for aviso in avisos:
                        carga.errores.append((archivo.name, aviso))
                if voz.id in self._voces:
                    # Id duplicado (p. ej. copia manual o fantasma de un
                    # renombrado antiguo): gana el archivo canónico
                    # (nombre == slug); el residuo se avisa, no se borra.
                    previa = self._rutas[voz.id]
                    if archivo.name == f"{_slug(voz.nombre)}.json":
                        carga.errores.append((
                            previa.name,
                            f"Residuo con el mismo id que «{voz.nombre}»; se "
                            f"ignora ({archivo.name} define esa voz). Vuelve a "
                            f"guardar la voz para limpiarlo."))
                        self._voces[voz.id] = voz
                        self._rutas[voz.id] = archivo
                    else:
                        carga.errores.append((
                            archivo.name,
                            f"Residuo con el mismo id que «{voz.nombre}»; se "
                            f"ignora ({previa.name} define esa voz). Vuelve a "
                            f"guardar la voz para limpiarlo."))
                    log.warning("Id de voz duplicado: %s vs %s",
                                previa.name, archivo.name)
                    continue
                self._voces[voz.id] = voz
                self._rutas[voz.id] = archivo
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
        ruta = self._ruta_libre(voz)
        ruta.write_text(
            json.dumps(voz.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._voces[voz.id] = voz
        self._rutas[voz.id] = ruta
        self._limpiar_residuos(voz.id, ruta)
        log.info("Voz guardada: %s → %s", voz.nombre, ruta.name)
        return ruta

    def _ruta_libre(self, voz: IVoiceProfile) -> Path:
        """Ruta de destino sin pisar a OTRA voz (colisión de slug).

        Si `slug.json` existe con el mismo id → es la propia voz (renombre
        de vuelta): se sobreescribe. Si existe con OTRO id → sufijo -2, -3…
        """
        base = _slug(voz.nombre)
        candidata = self._carpeta / f"{base}.json"
        numero = 1
        while candidata.exists():
            id_en_disco = self._id_de_archivo(candidata)
            if id_en_disco in (None, voz.id):
                break  # inexistente/ilegible o la propia voz: se pisa
            numero += 1
            candidata = self._carpeta / f"{base}-{numero}.json"
        return candidata

    def _id_de_archivo(self, ruta: Path) -> UUID | None:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            return UUID(str(datos.get("id", "")))
        except Exception:  # noqa: BLE001 — archivo ilegible: se pisa con cuidado
            return None

    def _limpiar_residuos(self, id_voz, ruta_actual: Path) -> None:
        """Borra archivos con el MISMO id pero distinta ruta (fantasmas).

        Garantiza el invariante "una voz = un archivo" (decisión 001):
        tras un renombrado, el JSON viejo con el mismo id desaparece.
        """
        for archivo in self._carpeta.glob("*.json"):
            if archivo == ruta_actual or not archivo.is_file():
                continue
            if self._id_de_archivo(archivo) == id_voz:
                try:
                    archivo.unlink()
                    log.info("Residuo eliminado tras guardar: %s", archivo.name)
                except OSError:
                    log.warning("No se pudo eliminar el residuo %s", archivo.name)

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
        ruta = self._rutas.pop(id_voz, None) or (
            self._carpeta / f"{_slug(voz.nombre)}.json")
        if ruta.exists():
            try:
                ruta.unlink()
            except OSError:
                log.warning("No se pudo eliminar %s", ruta)
        log.info("Voz eliminada: %s", voz.nombre)
        return True
