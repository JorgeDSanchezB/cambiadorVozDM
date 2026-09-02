"""Catálogo de parámetros leído de data/parametros.json (cero hardcoding).

Es la ÚNICA fuente de verdad de los rangos: la usa
  - la Fábrica de cadenas (decidir qué efectos instanciar),
  - el GestorVoces (recortar valores fuera de rango),
  - el Editor de la GUI (generar sliders automáticamente).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app.domain.models import ParametrosDSP

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DefParametro:
    clave: str
    etiqueta: str
    minimo: float
    maximo: float
    paso: float
    neutro: float
    unidad: str = ""


class CatalogoParametros:
    def __init__(self, definiciones: list[DefParametro]):
        if not definiciones:
            raise ValueError("Catálogo de parámetros vacío.")
        self._defs = definiciones
        self._por_clave: dict[str, DefParametro] = {d.clave: d for d in definiciones}

    @classmethod
    def desde_json(cls, ruta: Path) -> "CatalogoParametros":
        with open(ruta, encoding="utf-8") as fichero:
            datos = json.load(fichero)
        definiciones: list[DefParametro] = []
        for clave, d in datos.items():
            definiciones.append(DefParametro(
                clave=clave,
                etiqueta=str(d.get("etiqueta", clave)),
                minimo=float(d["min"]),
                maximo=float(d["max"]),
                paso=float(d.get("paso", 0.01)),
                neutro=float(d.get("neutro", 0.0)),
                unidad=str(d.get("unidad", "")),
            ))
        return cls(definiciones)

    def def_de(self, clave: str) -> DefParametro:
        return self._por_clave[clave]

    def todos(self) -> list[DefParametro]:
        return list(self._defs)

    def abrazar(self, p: ParametrosDSP) -> tuple[ParametrosDSP, list[str]]:
        """Recorta valores fuera de rango. Devuelve (params_recortados, avisos)."""
        avisos: list[str] = []
        valores: dict[str, float] = {}
        for f in fields(ParametrosDSP):
            v = float(getattr(p, f.name))
            dparam = self._por_clave.get(f.name)
            if dparam is None:
                valores[f.name] = v
                continue
            if v < dparam.minimo or v > dparam.maximo:
                v = min(max(v, dparam.minimo), dparam.maximo)
                avisos.append(f"'{f.name}' recortado a {v} (fuera de rango).")
            valores[f.name] = v
        return ParametrosDSP(**valores), avisos

    def es_neutra(self, p: ParametrosDSP) -> bool:
        """True si todos los parámetros están en su valor neutro."""
        for f in fields(ParametrosDSP):
            dparam = self._por_clave.get(f.name)
            if dparam is None:
                continue
            if abs(getattr(p, f.name) - dparam.neutro) > 1e-6:
                return False
        return True
