"""GestorVoces: integridad del invariante "una voz = un archivo".

Cubre los bugs corregidos:
  * Renombrar dejaba el JSON viejo con el MISMO id: al recargar, el orden
    alfabético decidía cuál ganaba y el renombre se revertía solo
    (reproducido: Zeta→Alfa volvía a ser Zeta tras recargar).
  * Dos nombres con el mismo slug ("Dragón!" y "dragón") escribían el mismo
    archivo y la segunda voz pisaba a la primera.
  * Un id duplicado en disco se cargaba en silencio (última ganadora).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.catalogo import CatalogoParametros
from app.domain.models import ParametrosDSP, PerfilDSP
from app.engine.gestor_voces import GestorVoces

RUTA_PARAMETROS = (Path(__file__).resolve().parent.parent
                   / "data" / "parametros.json")


class GestorVocesBase(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._td.name)
        self.catalogo = CatalogoParametros.desde_json(RUTA_PARAMETROS)
        self.gestor = GestorVoces(self.carpeta, self.catalogo)
        self.gestor.cargar_todas()  # crea neutral.json

    def tearDown(self) -> None:
        self._td.cleanup()

    def _nueva(self, nombre: str, pitch: float = 5.0) -> PerfilDSP:
        return PerfilDSP(nombre=nombre,
                         parametros_dsp=ParametrosDSP(pitch_semitonos=pitch))


class TestRenombrado(GestorVocesBase):
    def test_renombrar_no_deja_fantasma(self):
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        voz.nombre = "Alfa"
        self.gestor.guardar(voz)
        archivos = sorted(p.stem for p in self.carpeta.glob("*.json"))
        self.assertEqual(archivos, ["alfa", "neutral"],
                         "el JSON viejo (zeta.json) debe desaparecer")

    def test_renombrar_hacia_atras_en_alfabeto_persiste(self):
        """Caso del bug real: el nuevo nombre ordena ANTES que el viejo."""
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        voz.nombre = "Alfa"
        self.gestor.guardar(voz)

        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        por_nombre = {v.nombre: v for v in recarga.voces}
        self.assertIn("Alfa", por_nombre, "el renombre debe sobrevivir")
        self.assertNotIn("Zeta", por_nombre)
        self.assertEqual(por_nombre["Alfa"].id, voz.id)
        self.assertEqual(por_nombre["Alfa"].parametros_dsp.pitch_semitonos, 5.0)

    def test_renombrar_y_volver_al_nombre_original(self):
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        voz.nombre = "Alfa"
        self.gestor.guardar(voz)
        voz.nombre = "Zeta"
        self.gestor.guardar(voz)
        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        nombres = sorted(v.nombre for v in recarga.voces)
        self.assertEqual(nombres, ["Neutral", "Zeta"])


class TestColisionDeSlug(GestorVocesBase):
    def test_nombres_con_mismo_slug_no_se_pisan(self):
        """'Dragón!' y 'dragón' producen el slug 'dragon' para ambos."""
        a = self._nueva("Dragón!", pitch=3.0)
        b = self._nueva("dragón", pitch=-3.0)
        self.gestor.guardar(a)
        self.gestor.guardar(b)

        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        por_nombre = {v.nombre: v.parametros_dsp.pitch_semitonos
                      for v in recarga.voces}
        self.assertEqual(por_nombre.get("Dragón!"), 3.0)
        self.assertEqual(por_nombre.get("dragón"), -3.0)
        self.assertEqual(len(recarga.voces), 3)  # neutral + 2

    def test_renomear_sobre_slug_de_otra_voz_desambigua(self):
        a = self._nueva("Goblin", pitch=1.0)
        self.gestor.guardar(a)
        b = self._nueva("Bandido", pitch=2.0)
        self.gestor.guardar(b)
        b.nombre = "Goblin"  # colisión con el slug de a
        self.gestor.guardar(b)
        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        goblins = [v for v in recarga.voces if v.nombre == "Goblin"]
        self.assertEqual(len(goblins), 2, "ambas voces deben existir")


class TestIdDuplicado(GestorVocesBase):
    def test_carga_canonica_y_avisa_del_residuo(self):
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        # Simula un fantasma manual: copia con el mismo id y datos viejos.
        datos = json.loads((self.carpeta / "zeta.json").read_text(encoding="utf-8"))
        (self.carpeta / "copia_zeta.json").write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8")

        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        self.assertEqual(len([v for v in recarga.voces if v.nombre == "Zeta"]), 1)
        self.assertTrue(any("Residuo" in msg for _, msg in recarga.errores),
                        f"debe avisar del residuo: {recarga.errores}")

    def test_guardar_limpia_el_residuo(self):
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        datos = json.loads((self.carpeta / "zeta.json").read_text(encoding="utf-8"))
        (self.carpeta / "copia_zeta.json").write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8")

        g2 = GestorVoces(self.carpeta, self.catalogo)
        g2.cargar_todas()
        zeta = g2.por_id(voz.id)
        zeta.parametros_dsp = ParametrosDSP(pitch_semitonos=7.0)
        g2.guardar(zeta)

        ids = [p.name for p in self.carpeta.glob("*.json")]
        self.assertNotIn("copia_zeta.json", ids,
                         "guardar debe limpiar residuos del mismo id")


class TestComportamientoPreservado(GestorVocesBase):
    def test_neutral_regenerada_si_falta(self):
        (self.carpeta / "neutral.json").unlink()
        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        self.assertTrue(any(v.nombre == "Neutral" for v in recarga.voces))

    def test_neutral_jamas_se_elimina(self):
        self.assertFalse(self.gestor.eliminar(GestorVoces.ID_NEUTRA))

    def test_json_corrupto_se_omite_con_aviso(self):
        (self.carpeta / "rota.json").write_text("{no es json", encoding="utf-8")
        recarga = GestorVoces(self.carpeta, self.catalogo).cargar_todas()
        self.assertTrue(any("dañado" in msg for _, msg in recarga.errores))
        self.assertTrue(any(v.nombre == "Neutral" for v in recarga.voces))

    def test_eliminar_borra_el_archivo(self):
        voz = self._nueva("Efimera")
        ruta = self.gestor.guardar(voz)
        self.assertTrue(ruta.exists())
        self.assertTrue(self.gestor.eliminar(voz.id))
        self.assertFalse(ruta.exists())
        self.assertIsNone(self.gestor.por_id(voz.id))

    def test_eliminar_tras_renombrar_usa_la_ruta_real(self):
        voz = self._nueva("Zeta")
        self.gestor.guardar(voz)
        voz.nombre = "Alfa"
        self.gestor.guardar(voz)
        self.assertTrue(self.gestor.eliminar(voz.id))
        archivos = sorted(p.stem for p in self.carpeta.glob("*.json"))
        self.assertEqual(archivos, ["neutral"])


if __name__ == "__main__":
    unittest.main()
