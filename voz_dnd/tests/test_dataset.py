"""Dataset de clonación: consentimiento obligatorio, WAVs y umbrales.

Headless (solo stdlib): crea WAVs de prueba con el módulo `wave` y
trabaja en un TemporaryDirectory. Cubre la fundación experimental del
modo IA RVC — el entrenamiento llegará después y consumirá esto.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.dataset import (
    MIN_SEGUNDOS_MUESTRA,
    OBJETIVO_SEGUNDOS,
    ErrorDataset,
    anadir_muestras,
    crear_sujeto,
    estado_sujeto,
    sujetos,
)


def wav_prueba(ruta: Path, segundos: float, rate: int = 16000) -> None:
    """Escribe un WAV PCM de silencio con duración exacta."""
    frames = int(segundos * rate)
    with wave.open(str(ruta), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)


class TestDatasetClonacion(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    # --------------------------- consentimiento --------------------------- #
    def test_sin_consentimiento_se_rechaza(self) -> None:
        with self.assertRaises(ErrorDataset):
            crear_sujeto("Aria la Bardo", False, self.base)

    def test_consentimiento_queda_registrado(self) -> None:
        crear_sujeto("Aria la Bardo", True, self.base)
        estado = estado_sujeto("Aria la Bardo", self.base)
        self.assertTrue(estado["consentimiento"])
        registro = json.loads(
            (self.base / "aria_la_bardo" / "accesos.json").read_text(encoding="utf-8")
        )
        self.assertTrue(registro["consentimiento_en"])

    def test_nombre_vacio_se_rechaza(self) -> None:
        with self.assertRaises(ErrorDataset):
            crear_sujeto("   ", True, self.base)

    # ------------------------------ muestras ------------------------------ #
    def test_muestras_validas_se_registran(self) -> None:
        crear_sujeto("Gorg", True, self.base)
        wav_prueba(self.base / "a.wav", 30.0)
        wav_prueba(self.base / "b.wav", 45.5)
        resultado = anadir_muestras(
            "Gorg", [self.base / "a.wav", self.base / "b.wav"], self.base
        )
        self.assertEqual(resultado["n_muestras"], 2)
        self.assertAlmostEqual(resultado["segundos"], 75.5, places=1)
        self.assertEqual(resultado["rechazados"], [])

    def test_wav_corto_y_no_wav_se_rechazan_uno_a_uno(self) -> None:
        crear_sujeto("Gorg", True, self.base)
        wav_prueba(self.base / "corto.wav", MIN_SEGUNDOS_MUESTRA / 2)
        (self.base / "cancion.mp3").write_bytes(b"no es un wav")
        resultado = anadir_muestras(
            "Gorg",
            [self.base / "corto.wav", self.base / "cancion.mp3"],
            self.base,
        )
        self.assertEqual(resultado["n_muestras"], 0)
        self.assertEqual(len(resultado["rechazados"]), 2)

    def test_wav_corrupto_no_bloquea_los_validos(self) -> None:
        crear_sujeto("Gorg", True, self.base)
        wav_prueba(self.base / "bueno.wav", 12.0)
        (self.base / "podrido.wav").write_bytes(b"RIFF mentira")
        resultado = anadir_muestras(
            "Gorg",
            [self.base / "podrido.wav", self.base / "bueno.wav"],
            self.base,
        )
        self.assertEqual(resultado["n_muestras"], 1)
        self.assertEqual(len(resultado["rechazados"]), 1)

    def test_suficiente_con_objetivo_de_3_minutos(self) -> None:
        crear_sujeto("Tale", True, self.base)
        wav_prueba(self.base / "sesion.wav", OBJETIVO_SEGUNDOS + 1.0)
        resultado = anadir_muestras("Tale", [self.base / "sesion.wav"], self.base)
        self.assertTrue(resultado["suficiente"])
        wav_prueba(self.base / "poquito.wav", 60.0)
        crear_sujeto("Tale", True, self.base)  # idempotente
        otro = estado_sujeto("Tale", self.base)
        self.assertFalse(otro["suficiente"] and otro["segundos"] < OBJETIVO_SEGUNDOS)

    # --------------------------- tolerancia ------------------------------- #
    def test_registro_corrupto_no_explota(self) -> None:
        carpeta = self.base / "raiz"
        carpeta.mkdir(parents=True)
        (carpeta / "accesos.json").write_text("{roto", encoding="utf-8")
        crear_sujeto("raiz", True, self.base)
        wav_prueba(self.base / "ok.wav", 10.0)
        resultado = anadir_muestras("raiz", [self.base / "ok.wav"], self.base)
        self.assertEqual(resultado["n_muestras"], 1)

    def test_sujetos_lista_resumen(self) -> None:
        self.assertEqual(sujetos(self.base), [])
        crear_sujeto("Duo", True, self.base)
        resumen = sujetos(self.base)
        self.assertEqual(len(resumen), 1)
        self.assertEqual(resumen[0]["nombre"], "Duo")
        self.assertFalse(resumen[0]["suficiente"])


if __name__ == "__main__":
    unittest.main()
