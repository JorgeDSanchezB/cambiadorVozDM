#!/usr/bin/env python3
"""Genera el catálogo de voces de la web desde los JSON del escritorio.

Lee `voz_dnd/data/voces/*.json` y `voz_dnd/data/parametros.json` (app de
escritorio) y produce `web/src/data/voces.json` + `web/src/data/parametros.json`
(regla del espejo entre ramas, ver AGENTS.md). Solo librería estándar.

Uso:
    python3 web/scripts/sincronizar_voces.py
    python3 web/scripts/sincronizar_voces.py --origen DIR --destino DIR
    python3 web/scripts/sincronizar_voces.py --autotest
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_RAIZ = Path(__file__).resolve().parents[2]
ORIGEN_DEFECTO = REPO_RAIZ / "voz_dnd" / "data" / "voces"
CATALOGO_DEFECTO = REPO_RAIZ / "voz_dnd" / "data" / "parametros.json"
DESTINO_DEFECTO = REPO_RAIZ / "web" / "src" / "data"
GENERADO_POR = "web/scripts/sincronizar_voces.py"

CAMPOS_TEXTO = ("id", "nombre", "tipo", "icono", "color")


class ErrorFatal(Exception):
    """Error irrecuperable: catálogo roto, sin voz Neutral, destino no escribible."""


def _es_numero(valor: object) -> bool:
    # bool es subclase de int en Python: un `true` no es un valor DSP válido.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def registrar_aviso(mensaje: str, avisos: list) -> None:
    avisos.append(mensaje)
    print("AVISO: " + mensaje, file=sys.stderr)


def cargar_catalogo(ruta: Path) -> dict:
    try:
        catalogo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErrorFatal("no se pudo leer el catálogo de parámetros {}: {}".format(ruta, exc)) from exc
    if not isinstance(catalogo, dict) or not catalogo:
        raise ErrorFatal("catálogo de parámetros inválido en {}: se esperaba un objeto no vacío".format(ruta))
    for nombre, espec in catalogo.items():
        if not isinstance(espec, dict) or not _es_numero(espec.get("min")) or not _es_numero(espec.get("max")):
            raise ErrorFatal(
                "catálogo de parámetros inválido en {}: '{}' necesita 'min' y 'max' numéricos".format(ruta, nombre)
            )
        if espec["min"] > espec["max"]:
            raise ErrorFatal("catálogo de parámetros inválido en {}: '{}' tiene min > max".format(ruta, nombre))
    return catalogo


def procesar_voz(ruta: Path, catalogo: dict, avisos: list) -> dict | None:
    """Valida y normaliza una voz. Devuelve None (con aviso) si hay que saltarla."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        registrar_aviso("{}: JSON ilegible ({}); voz saltada".format(ruta.name, exc), avisos)
        return None

    if not isinstance(datos, dict):
        registrar_aviso("{}: la raíz no es un objeto JSON; voz saltada".format(ruta.name), avisos)
        return None

    for campo in CAMPOS_TEXTO:
        valor = datos.get(campo)
        if campo in ("id", "nombre"):
            if not isinstance(valor, str) or not valor.strip():
                registrar_aviso("{}: campo '{}' ausente o no es texto no vacío; voz saltada".format(ruta.name, campo), avisos)
                return None
        elif not isinstance(valor, str):
            registrar_aviso("{}: campo '{}' ausente o no es texto; voz saltada".format(ruta.name, campo), avisos)
            return None

    atajo = datos.get("atajo")
    if atajo is not None and not isinstance(atajo, str):
        registrar_aviso("{}: campo 'atajo' debe ser texto o null; voz saltada".format(ruta.name), avisos)
        return None

    # Las voces IA se degradan a su cadena DSP post (espejo del escritorio);
    # se conserva tipo "IA" para que la UI web las distinga.
    campo_dsp = "dsp_post" if datos["tipo"] == "IA" else "parametros_dsp"
    dsp = datos.get(campo_dsp)
    if not isinstance(dsp, dict):
        registrar_aviso(
            "{}: falta '{}' (objeto) en una voz tipo {!r}; voz saltada".format(ruta.name, campo_dsp, datos["tipo"]),
            avisos,
        )
        return None

    parametros = {}
    for nombre_param, espec in catalogo.items():
        if nombre_param not in dsp or not _es_numero(dsp[nombre_param]):
            registrar_aviso(
                "{}: parámetro '{}' ausente o no numérico; voz saltada".format(ruta.name, nombre_param), avisos
            )
            return None
        valor = dsp[nombre_param]
        minimo, maximo = espec["min"], espec["max"]
        if valor < minimo:
            registrar_aviso(
                "{}: '{}'={} por debajo del mínimo {}; clampeado a {}".format(
                    ruta.name, nombre_param, valor, minimo, minimo
                ),
                avisos,
            )
            valor = minimo
        elif valor > maximo:
            registrar_aviso(
                "{}: '{}'={} por encima del máximo {}; clampeado a {}".format(
                    ruta.name, nombre_param, valor, maximo, maximo
                ),
                avisos,
            )
            valor = maximo
        parametros[nombre_param] = valor

    return {
        "id": datos["id"],
        "nombre": datos["nombre"],
        "tipo": datos["tipo"],
        "icono": datos["icono"],
        "color": datos["color"],
        "atajo": atajo,
        "parametros_dsp": parametros,
    }


def sincronizar(origen: Path, destino: Path, ruta_catalogo: Path) -> dict:
    """Pipeline completo. Lanza ErrorFatal solo en errores irrecuperables."""
    avisos = []
    if not origen.is_dir():
        raise ErrorFatal("el origen no existe o no es un directorio: {}".format(origen))
    catalogo = cargar_catalogo(ruta_catalogo)

    archivos = sorted(origen.glob("*.json"), key=lambda p: p.name.casefold())
    voces = []
    ids_vistos = {}
    saltadas = 0
    for ruta in archivos:
        voz = procesar_voz(ruta, catalogo, avisos)
        if voz is None:
            saltadas += 1
            continue
        if voz["id"] in ids_vistos:
            registrar_aviso(
                "{}: id duplicado {} (ya apareció en {}); se conserva la primera "
                "aparición y se salta esta voz".format(ruta.name, voz["id"], ids_vistos[voz["id"]]),
                avisos,
            )
            saltadas += 1
            continue
        ids_vistos[voz["id"]] = ruta.name
        voces.append(voz)

    voces.sort(key=lambda v: v["nombre"].casefold())

    if not any(v["nombre"] == "Neutral" for v in voces):
        raise ErrorFatal(
            'no existe ninguna voz llamada "Neutral"; la web la necesita garantizada (espejo del escritorio)'
        )

    try:
        fuente = origen.resolve().relative_to(REPO_RAIZ).as_posix()
    except ValueError:
        fuente = str(origen)

    documento = {
        "version": 1,
        "generado_por": GENERADO_POR,
        "fuente": fuente,
        "voces": [
            {
                "id": v["id"],
                "nombre": v["nombre"],
                "tipo": v["tipo"],
                "icono": v["icono"],
                "color": v["color"],
                "atajo": v["atajo"],
                "parametros_dsp": v["parametros_dsp"],
            }
            for v in voces
        ],
    }

    try:
        destino.mkdir(parents=True, exist_ok=True)
        ruta_voces = destino / "voces.json"
        with ruta_voces.open("w", encoding="utf-8", newline="\n") as fichero:
            json.dump(documento, fichero, ensure_ascii=False, indent=2)
            fichero.write("\n")
        ruta_parametros = destino / "parametros.json"
        shutil.copyfile(ruta_catalogo, ruta_parametros)
    except OSError as exc:
        raise ErrorFatal("no se pudo escribir en {}: {}".format(destino, exc)) from exc

    return {
        "origen": origen,
        "archivos": len(archivos),
        "incluidas": len(voces),
        "saltadas": saltadas,
        "avisos": avisos,
        "ruta_voces": ruta_voces,
        "ruta_parametros": ruta_parametros,
    }


def imprimir_resumen(resultado: dict) -> None:
    print("== Sincronización de voces (escritorio -> web) ==")
    print("Origen:          {} ({} archivos JSON)".format(resultado["origen"], resultado["archivos"]))
    print("Voces incluidas: {}".format(resultado["incluidas"]))
    print("Voces saltadas:  {}".format(resultado["saltadas"]))
    print("Avisos:          {}".format(len(resultado["avisos"])))
    for mensaje in resultado["avisos"]:
        print("  - " + mensaje)
    print("Salidas:")
    print("  - {}".format(resultado["ruta_voces"]))
    print("  - {}".format(resultado["ruta_parametros"]))


def autotest() -> bool:
    """Prueba de tolerancia en un directorio temporal (tempfile).

    Casos: voz válida copiada del repo + JSON corrupto + voz con un parámetro
    fuera de rango (pitch_semitonos=99). El script debe incluir las dos válidas
    (la segunda clampeada y con aviso), saltar la corrupta sin morir y dejar
    los dos archivos de salida.
    """
    voz_valida = ORIGEN_DEFECTO / "neutral.json"
    if not voz_valida.is_file():
        print("AUTOTEST FALLIDO: no existe la voz de ejemplo {}".format(voz_valida), file=sys.stderr)
        return False

    with tempfile.TemporaryDirectory(prefix="sincronizar_voces_") as temporal:
        raiz = Path(temporal)
        origen = raiz / "voces"
        destino = raiz / "web"
        origen.mkdir()

        shutil.copyfile(voz_valida, origen / "valida.json")
        (origen / "corrupta.json").write_text("{ no valido", encoding="utf-8")
        fuera = json.loads(voz_valida.read_text(encoding="utf-8"))
        fuera["id"] = "autotest-fuera-de-rango"
        fuera["nombre"] = "Fuera de Rango"
        fuera["atajo"] = "F99"
        fuera["parametros_dsp"]["pitch_semitonos"] = 99
        (origen / "fuera_rango.json").write_text(
            json.dumps(fuera, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        try:
            resultado = sincronizar(origen, destino, CATALOGO_DEFECTO)
        except ErrorFatal as exc:
            print("AUTOTEST FALLIDO: el script murió con: {}".format(exc), file=sys.stderr)
            return False

        fallos = []
        if resultado["incluidas"] != 2 or resultado["saltadas"] != 1:
            fallos.append(
                "esperaba 2 incluidas y 1 saltada, obtuve {} y {}".format(
                    resultado["incluidas"], resultado["saltadas"]
                )
            )
        try:
            doc = json.loads(resultado["ruta_voces"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fallos.append("voces.json de salida ilegible: {}".format(exc))
            doc = {"voces": []}
        nombres = [v.get("nombre") for v in doc.get("voces", [])]
        if "Neutral" not in nombres or "Fuera de Rango" not in nombres:
            fallos.append("faltan voces esperadas en la salida: {}".format(nombres))
        for voz in doc.get("voces", []):
            if voz.get("nombre") == "Fuera de Rango" and voz.get("parametros_dsp", {}).get("pitch_semitonos") != 12.0:
                fallos.append(
                    "pitch_semitonos no se clampeó a 12.0: {}".format(
                        voz.get("parametros_dsp", {}).get("pitch_semitonos")
                    )
                )
        texto_avisos = "\n".join(resultado["avisos"])
        if "corrupta.json" not in texto_avisos:
            fallos.append("no hubo aviso por el JSON corrupto")
        if "pitch_semitonos" not in texto_avisos:
            fallos.append("no hubo aviso por el parámetro fuera de rango")
        if not resultado["ruta_parametros"].is_file():
            fallos.append("no se copió parametros.json al destino")

        if fallos:
            for fallo in fallos:
                print("AUTOTEST FALLIDO: {}".format(fallo), file=sys.stderr)
            return False

        print("AUTOTEST DE TOLERANCIA: OK")
        print("  - voz válida incluida; JSON corrupto saltado sin morir; pitch_semitonos=99 clampeado a 12.0 con aviso")
        print("  - incluidas={} saltadas={} avisos={}".format(
            resultado["incluidas"], resultado["saltadas"], len(resultado["avisos"])
        ))
        return True


def resolver_catalogo(origen: Path, explicito: Path | None) -> Path:
    if explicito is not None:
        return explicito
    junto_al_origen = origen.parent / "parametros.json"
    return junto_al_origen if junto_al_origen.is_file() else CATALOGO_DEFECTO


def parsear_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza el catálogo de voces del escritorio (voz_dnd/data) hacia la web (web/src/data)."
    )
    parser.add_argument(
        "--origen", type=Path, default=ORIGEN_DEFECTO,
        help="directorio con los JSON de voz (defecto: %(default)s)",
    )
    parser.add_argument(
        "--destino", type=Path, default=DESTINO_DEFECTO,
        help="directorio de salida (defecto: %(default)s)",
    )
    parser.add_argument(
        "--catalogo", type=Path, default=None,
        help="catálogo parametros.json a usar y copiar (defecto: junto al origen si existe, si no {})".format(CATALOGO_DEFECTO),
    )
    parser.add_argument(
        "--autotest", action="store_true",
        help="ejecuta la prueba automática de tolerancia en un directorio temporal",
    )
    return parser.parse_args(argv)


def main(argv: list | None = None) -> int:
    args = parsear_args(argv)
    if args.autotest:
        return 0 if autotest() else 1
    try:
        origen = args.origen.resolve()
        destino = args.destino.resolve()
        ruta_catalogo = resolver_catalogo(origen, args.catalogo.resolve() if args.catalogo else None).resolve()
        resultado = sincronizar(origen, destino, ruta_catalogo)
    except ErrorFatal as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    imprimir_resumen(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
