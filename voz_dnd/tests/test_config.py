"""RepoConfig/ConfigApp: tolerancia a fallos de config.json sin silencios.

Cubre:
  * Defaults al crear / respaldo del corrupto / recorte de buffer y sr.
  * Corrección aplicada: un tema inválido ahora AVISA (antes se cambiaba
    a 'oscuro' en silencio, ocultando un error de configuración).
  * Tripwire anti-duplicación de constantes (Regla de Cero Hardcoding):
    los límites de audio viven SOLO en app/config.py y el overhead de
    driver SOLO en app/engine/motor_audio.py.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import (
    BUFFERS_VALIDOS,
    SAMPLE_RATES_VALIDOS,
    TEMAS_VALIDOS,
    RepoConfig,
)

RAIZ = Path(__file__).resolve().parent.parent


class TestRepoConfig(unittest.TestCase):
    def _con_config(self, contenido: str):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ruta = Path(td.name) / "config.json"
        ruta.write_text(contenido, encoding="utf-8")
        return RepoConfig(ruta).cargar()

    def test_no_existia_devuelve_defaults_con_aviso(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        cfg, avisos = RepoConfig(Path(td.name) / "config.json").cargar()
        self.assertEqual(cfg.audio.buffer_size, 256)
        self.assertEqual(len(avisos), 1)

    def test_corrupto_respaldado_y_defaults(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        ruta = Path(td.name) / "config.json"
        ruta.write_text("{roto", encoding="utf-8")
        cfg, avisos = RepoConfig(ruta).cargar()
        self.assertEqual(cfg.audio.buffer_size, 256)
        self.assertTrue(any("corrupto" in a for a in avisos))
        self.assertTrue((Path(td.name) / "config.corrupto.json").exists())

    def test_buffer_invalido_recorta_con_aviso(self):
        cfg, avisos = self._con_config('{"audio": {"buffer_size": 999}}')
        self.assertEqual(cfg.audio.buffer_size, 256)
        self.assertTrue(any("Buffer" in a for a in avisos))

    def test_sample_rate_invalido_recorta_con_aviso(self):
        cfg, avisos = self._con_config('{"audio": {"sample_rate": 44101}}')
        self.assertEqual(cfg.audio.sample_rate, 48000)
        self.assertTrue(any("Sample rate" in a for a in avisos))

    def test_tema_invalido_ahora_avisa(self):
        cfg, avisos = self._con_config('{"ui": {"tema": "neon"}}')
        self.assertEqual(cfg.ui.tema, "oscuro")
        self.assertTrue(any("Tema" in a for a in avisos),
                        "el tema inválido debe avisar, no corregirse en silencio")

    def test_tema_valido_no_avisa(self):
        cfg, avisos = self._con_config('{"ui": {"tema": "claro"}}')
        self.assertEqual(cfg.ui.tema, "claro")
        self.assertFalse([a for a in avisos if "Tema" in a])

    def test_atajos_invalidos_se_ignoran_con_aviso(self):
        cfg, avisos = self._con_config('{"atajos": ["F1", "F2"]}')
        self.assertEqual(cfg.atajos, {})
        self.assertTrue(any("atajos" in a for a in avisos))

    def test_claves_desconocidas_no_rompen(self):
        cfg, avisos = self._con_config('{"futuro": {"algo": 1}}')
        self.assertEqual(cfg.audio.buffer_size, 256)  # defaults intactos


class TestConstantesSinDuplicar(unittest.TestCase):
    """Tripwire: cada límite vive en UNA sola fuente (cero hardcoding).

    El fallback `or 256` de pestana_ajustes es el valor por defecto del
    combo (vacío imposible), no una segunda definición del límite.
    """

    def test_limited_de_audio_solo_en_config(self):
        fuentes_gui = list((RAIZ / "app" / "gui").glob("*.py"))
        self.assertTrue(fuentes_gui)
        for fuente in fuentes_gui:
            texto = fuente.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"^MUESTREOS\s*=", texto, re.M),
                f"{fuente.name} vuelve a definir constantes de audio")

    def test_overhead_driver_solo_en_motor(self):
        for fuente in (RAIZ / "app").rglob("*.py"):
            if fuente.name == "motor_audio.py":
                continue
            texto = fuente.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"^OVERHEAD_DRIVER_MS\s*=\s*\d", texto, re.M),
                f"{fuente} duplica el overhead de driver (fuente única: "
                f"app/engine/motor_audio.py)")

    def test_temas_validos_coinciden_con_tema_py(self):
        from app.gui import tema  # noqa: F401 — importa sin Qt (solo dataclass)
        self.assertEqual(
            set(TEMAS_VALIDOS),
            {tema.NOMBRE_OSCURO, tema.NOMBRE_CLARO},
            "TEMAS_VALIDOS y los presets de app/gui/tema.py deben coincidir")


if __name__ == "__main__":
    unittest.main()
