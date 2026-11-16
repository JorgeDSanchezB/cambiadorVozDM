"""Packs de voces: export/import conservador con ids nuevos.

Headless: construye un GestorVoces real en un TemporaryDirectory con el
catálogo real de data/parametros.json, exporta ZIP, importa en OTRO
gestor y verifica las políticas (id nuevo, Neutral fuera, nombres
duplicados omitidos, ZIP roto → ErrorPack).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.catalogo import CatalogoParametros
from app.domain.models import ParametrosDSP, PerfilDSP
from app.engine.gestor_voces import GestorVoces
from app.engine.packs import ErrorPack, exportar_pack, importar_pack

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = CatalogoParametros.desde_json(RAIZ / "data" / "parametros.json")


class TestPacksVoces(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.carpeta_a = base / "a"
        self.carpeta_b = base / "b"
        self.gestor_a = GestorVoces(
            self.carpeta_a, CATALOGO)
        self.gestor_b = GestorVoces(
            self.carpeta_b, CATALOGO)

    def _voz(self, nombre: str, pitch: float = -3.0) -> PerfilDSP:
        return PerfilDSP(nombre=nombre,
                         parametros_dsp=ParametrosDSP(pitch_semitonos=pitch))

    # ------------------------------ export -------------------------------- #
    def test_exportar_sin_voces_propias_falla(self) -> None:
        destino = Path(self.tmp.name) / "pack.zip"
        with self.assertRaises(ErrorPack):
            exportar_pack(destino, self.gestor_a)

    def test_exportar_incluye_manifiesto_y_voces_sin_neutral(self) -> None:
        self.gestor_a.guardar(self._voz("Heraldo Sombrío"))
        destino = Path(self.tmp.name) / "packs" / "mi_pack.zip"
        resultado = exportar_pack(destino, self.gestor_a)
        self.assertEqual(resultado["total"], 1)
        self.assertTrue(destino.exists())
        with zipfile.ZipFile(destino) as paquete:
            nombres = paquete.namelist()
            self.assertIn("pack.json", nombres)
            manifiesto = json.loads(paquete.read("pack.json"))
            self.assertEqual(manifiesto["total"], 1)
            self.assertTrue(
                any(n.startswith("voces/") and n.endswith(".json")
                    for n in nombres))
            self.assertFalse(
                any("neutral" in n.lower() for n in nombres),
                "la Neutral es de seguridad y no va en packs")

    # ------------------------------ import -------------------------------- #
    def test_importar_regenera_ids_y_no_pisa_nada(self) -> None:
        self.gestor_a.guardar(self._voz("Heraldo Sombrío"))
        pack = Path(self.tmp.name) / "pack.zip"
        exportar_pack(pack, self.gestor_a)

        # El que importa YA tiene su propia voz con otro id
        propia = self._voz("Mi Voz Local")
        self.gestor_b.guardar(propia)
        id_propia = str(propia.id)

        resultado = importar_pack(pack, self.gestor_b)
        self.assertEqual(resultado["anadidas"], ["Heraldo Sombrío"])
        self.assertEqual(resultado["omitidas"], [])
        nombres = [v.nombre for v in self.gestor_b.todas()]
        self.assertIn("Heraldo Sombrío", nombres)
        self.assertIn("Mi Voz Local", nombres)
        # La voz local conserva SU id (nada se pisa)
        self.assertTrue(any(str(v.id) == id_propia for v in self.gestor_b.todas()))

    def test_importar_omite_duplicados_y_neutral(self) -> None:
        self.gestor_a.guardar(self._voz("Doble Voz"))
        pack = Path(self.tmp.name) / "pack.zip"
        exportar_pack(pack, self.gestor_a)
        self.gestor_b.guardar(self._voz("Doble Voz", pitch=2.0))
        resultado = importar_pack(pack, self.gestor_b)
        self.assertEqual(resultado["anadidas"], [])
        self.assertEqual(len(resultado["omitidas"]), 1)
        self.assertIn("ya tienes una voz", resultado["omitidas"][0])

    def test_importar_zip_roto_falla_honesto(self) -> None:
        roto = Path(self.tmp.name) / "roto.zip"
        roto.write_bytes(b"esto no es un zip")
        with self.assertRaises(ErrorPack):
            importar_pack(roto, self.gestor_b)

    def test_importar_zip_sin_manifiesto_falla(self) -> None:
        sin = Path(self.tmp.name) / "sin.json"
        with zipfile.ZipFile(sin, "w") as paquete:
            paquete.writestr("otra_cosa.txt", "hola")
        with self.assertRaises(ErrorPack):
            importar_pack(sin, self.gestor_b)


if __name__ == "__main__":
    unittest.main()
