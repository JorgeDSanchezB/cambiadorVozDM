"""Packs de voces: exportar/importar ZIP de data/voces/*.json.

Idea de los Model Packs de VoiceStudio (petición explícita del usuario):
compartir el elenco con otros DMs. Un pack es un ZIP con los JSON de las
voces del catálogo propio + un pack.json de manifiesto (versión, fecha,
total). Política de importación conservadora:

- Cada voz importada se le REGENERA el id (uuid4): jamás pisa las voces
  del que importa.
- Se omite la voz Neutral (es la voz de seguridad integrada, no delenco).
- Se omite si ya existe una voz con ese nombre (sin duplicados raros).
- Los parámetros se abrazan al catálogo al guardar (GestorVoces lo hace).
- Sin pack.json o ZIP roto → ErrorPack con mensaje claro.

Solo stdlib (zipfile/json/shutil): testeable headless.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import zipfile
from pathlib import Path

from app.domain.models import PerfilDSP, voz_desde_dict
from app.engine.gestor_voces import GestorVoces

log = logging.getLogger(__name__)

VERSION_PACK = 1
MANIFIESTO = "pack.json"


class ErrorPack(ValueError):
    """Pack inválido o operación imposible (ZIP roto, sin manifiesto…)."""


def exportar_pack(destino: Path, gestor: GestorVoces) -> dict:
    """Empaqueta las voces del catálogo propio (sin la Neutral) en un ZIP."""
    destino = Path(destino)
    voces = [
        v for v in gestor.todas()
        if not (str(v.id) == str(GestorVoces.ID_NEUTRA) or v.nombre.strip() == "Neutral")
    ]
    if not voces:
        raise ErrorPack("No hay voces propias que empaquetar (solo está la Neutral).")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr(MANIFIESTO, json.dumps({
            "version": VERSION_PACK,
            "creado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(voces),
            "fuente": "DMVoiceChanger (voz_dnd)",
        }, ensure_ascii=False, indent=2))
        for voz in voces:
            paquete.writestr(f"voces/{voz.nombre}.json",
                             json.dumps(voz.a_dict(), ensure_ascii=False, indent=2))
    return {"total": len(voces), "destino": str(destino)}


def importar_pack(ruta_pack: Path, gestor: GestorVoces) -> dict:
    """Añade al elenco las voces de un pack, conservadoras y con ids nuevos."""
    ruta_pack = Path(ruta_pack)
    if not ruta_pack.exists():
        raise ErrorPack(f"No existe el pack: {ruta_pack.name}")
    try:
        with zipfile.ZipFile(ruta_pack) as paquete:
            nombres = paquete.namelist()
            if MANIFIESTO not in nombres:
                raise ErrorPack(
                    "El ZIP no parece un pack de voces (falta pack.json).")
            try:
                manifiesto = json.loads(paquete.read(MANIFIESTO))
                if not isinstance(manifiesto, dict) or "version" not in manifiesto:
                    raise ErrorPack("El manifiesto del pack está dañado.")
            except json.JSONDecodeError as exc:
                raise ErrorPack(f"Manifiesto ilegible: {exc}") from exc

            anadidas: list[str] = []
            omitidas: list[str] = []
            nombres_existentes = {v.nombre.strip().lower()
                                  for v in gestor.todas()}
            for entrada in nombres:
                if entrada == MANIFIESTO or entrada.endswith("/"):
                    continue
                if not entrada.lower().endswith(".json"):
                    continue  # carpetas extra: se ignoran sin drama
                try:
                    datos = json.loads(paquete.read(entrada))
                    voz = voz_desde_dict(datos)
                except Exception as exc:  # noqa: BLE001 — voz rota del pack
                    omitidas.append(f"{Path(entrada).name}: dañada ({exc})")
                    log.warning("Voz del pack omitida (%s): %s", entrada, exc)
                    continue
                if (str(voz.id) == str(GestorVoces.ID_NEUTRA)
                        or voz.nombre.strip() == "Neutral"):
                    omitidas.append(f"{voz.nombre}: es la voz de seguridad "
                                    "integrada, no va en packs")
                    continue
                if voz.nombre.strip().lower() in nombres_existentes:
                    omitidas.append(f"{voz.nombre}: ya tienes una voz con "
                                    "ese nombre")
                    continue
                # Id nuevo SIEMPRE: el pack de otro no pisa mis voces.
                voz.id = uuid.uuid4()
                gestor.guardar(voz)
                nombres_existentes.add(voz.nombre.strip().lower())
                anadidas.append(voz.nombre)
            return {
                "anadidas": anadidas,
                "omitidas": omitidas,
                "total_pack": manifiesto.get("total", "?"),
            }
    except zipfile.BadZipFile as exc:
        raise ErrorPack("El ZIP está dañado o no es un ZIP.") from exc


def es_dsp(voz) -> bool:
    """Ayuda para la UI: ¿la voz importada es DSP? (las IA piden modelo)."""
    return isinstance(voz, PerfilDSP)
