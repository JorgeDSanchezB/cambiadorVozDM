"""Fundación experimental de la clonación de voz (RVC) — dataset y consentimiento.

Idea del voice cloning de VoiceStudio: una voz limpia de referencia → voz
clonada. Aquí preparamos la PRIMERA pieza de esa vía en el escritorio:
reunir y registrar muestras WAV limpias de un sujeto CON CONSENTIMIENTO
explícito, en `data/clonacion/<sujeto>/` (no versionada).

Honestidad de alcance: el ENTRENAMIENTO RVC NO vive aquí todavía (exige
GPU y una cadena de entrenamiento aparte). Este módulo deja el dataset
listo para que ese futuro entrenamiento lo consuma, y para que el
`rvc_adapter` existente pueda apoyarse en él. Solo stdlib (wave/json):
sin dependencias nuevas, testeable headless.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
import wave
from pathlib import Path

from app.rutas import CARPETA_CLONACION

log = logging.getLogger(__name__)

# Objetivo honesto de RVC: ~3 minutos de voz limpia como mínimo usable
# (10 min es lo ideal; aquí pedimos el suelo, no el ideal).
OBJETIVO_SEGUNDOS = 180.0
MIN_SEGUNDOS_MUESTRA = 2.0

VERSION_DATASET = 1


class ErrorDataset(ValueError):
    """Petición inválida del dataset (nombre, consentimiento, archivo)."""


def _slug(nombre: str) -> str:
    limpio = "".join(
        c if c.isalnum() else "_" for c in nombre.strip().lower()
    )
    slug = "_".join(p for p in limpio.split("_") if p)[:40]
    return slug or "sujeto"


def _ruta_sujeto(nombre: str, ruta_base: Path) -> Path:
    return ruta_base / _slug(nombre)


def _leer_registro(ruta: Path) -> dict:
    """Tolerante a accesos.json corrupto o ausente (regla del proyecto)."""
    try:
        dato = json.loads(ruta.read_text(encoding="utf-8"))
        if isinstance(dato, dict) and isinstance(dato.get("muestras"), list):
            return dato
    except Exception:  # noqa: BLE001 — corrupto: se reconstruye con aviso
        log.warning("Registro de dataset corrupto o ausente: %s", ruta)
    return {}


def segundos_wav(ruta: Path) -> float:
    """Duración de un WAV PCM con la stdlib. Lanza si no es legible."""
    with wave.open(str(ruta), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        if rate <= 0:
            raise ErrorDataset(f"WAV sin tasa válida: {ruta.name}")
        return frames / float(rate)


def crear_sujeto(
    nombre: str,
    consentimiento: bool,
    ruta_base: Path = CARPETA_CLONACION,
) -> dict:
    """Crea `data/clonacion/<slug>/` con registro de consentimiento.

    El consentimiento es OBLIGATORIO y queda registrado con fecha: clonar
    una voz ajena sin permiso no entra en la forja. Devuelve el registro.
    """
    nombre = nombre.strip()
    if not nombre:
        raise ErrorDataset("Ponle nombre al sujeto de la clonación.")
    if not consentimiento:
        raise ErrorDataset(
            "Se requiere consentimiento explícito para reunir la voz de "
            "un sujeto (propia o permiso por escrito)."
        )
    carpeta = _ruta_sujeto(nombre, ruta_base)
    carpeta.mkdir(parents=True, exist_ok=True)
    registro = _leer_registro(carpeta / "accesos.json")
    if not registro:
        registro = {
            "version": VERSION_DATASET,
            "id": str(uuid.uuid4()),
            "nombre": nombre,
            "consentimiento": True,
            "consentimiento_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "creado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "muestras": [],
        }
    (carpeta / "accesos.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registro


def anadir_muestras(
    nombre: str,
    rutas: list[Path],
    ruta_base: Path = CARPETA_CLONACION,
) -> dict:
    """Copia WAVs limpios al dataset del sujeto y los registra.

    Devuelve el estado actualizado. Los archivos no-WAV, corruptos o más
    cortos que MIN_SEGUNDOS_MUESTRA se rechazan UNO A UNO (los válidos se
    quedan): la respuesta lleva `rechazados` para avisar con detalle.
    """
    carpeta = _ruta_sujeto(nombre, ruta_base)
    if not carpeta.exists():
        raise ErrorDataset(f"El sujeto «{nombre}» aún no tiene dataset.")
    registro = _leer_registro(carpeta / "accesos.json")
    muestras = list(registro.get("muestras", []))
    rechazados: list[str] = []
    for ruta in rutas:
        ruta = Path(ruta)
        try:
            if ruta.suffix.lower() != ".wav":
                raise ErrorDataset("solo WAV (usa MP3→WAV antes, sin recortes de calidad)")
            segundos = segundos_wav(ruta)
            if segundos < MIN_SEGUNDOS_MUESTRA:
                raise ErrorDataset(f"demasiado corta ({segundos:.1f} s)")
            destino = carpeta / f"muestra_{uuid.uuid4().hex[:8]}.wav"
            shutil.copy2(ruta, destino)
            muestras.append({
                "archivo": destino.name,
                "segundos": round(segundos, 2),
                "anadido_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        except ErrorDataset as exc:
            rechazados.append(f"{ruta.name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — wav corrupto, permisos…
            rechazados.append(f"{ruta.name}: no legible ({exc})")
            log.warning("Muestra rechazada para %s: %s", nombre, exc)

    registro["muestras"] = muestras
    registro["segundos_totales"] = round(
        sum(m.get("segundos", 0.0) for m in muestras), 2
    )
    (carpeta / "accesos.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if rechazados:
        log.info("Muestras rechazadas (%d) para %s", len(rechazados), nombre)
    return {**estado_sujeto(nombre, ruta_base), "rechazados": rechazados}


def estado_sujeto(nombre: str, ruta_base: Path = CARPETA_CLONACION) -> dict:
    """Resumen del dataset de un sujeto (para la UI y el futuro trainer)."""
    carpeta = _ruta_sujeto(nombre, ruta_base)
    registro = _leer_registro(carpeta / "accesos.json")
    muestras = list(registro.get("muestras", []))
    segundos = sum(m.get("segundos", 0.0) for m in muestras)
    return {
        "nombre": registro.get("nombre", nombre),
        "existe": carpeta.exists(),
        "consentimiento": bool(registro.get("consentimiento")),
        "n_muestras": len(muestras),
        "segundos": round(segundos, 2),
        "suficiente": segundos >= OBJETIVO_SEGUNDOS,
        "objetivo_segundos": OBJETIVO_SEGUNDOS,
    }


def sujetos(ruta_base: Path = CARPETA_CLONACION) -> list[dict]:
    """Todos los datasets existentes (para el resumen de Ajustes)."""
    if not ruta_base.exists():
        return []
    out: list[dict] = []
    for carpeta in sorted(ruta_base.iterdir()):
        if carpeta.is_dir():
            try:
                out.append(estado_sujeto(carpeta.name, ruta_base))
            except Exception:  # noqa: BLE001 — nunca bloquear por un dataset raro
                log.warning("Dataset ilegible: %s", carpeta)
    return out
