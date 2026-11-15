"""LectorTexto: los fragmentos de un texto largo se CONCATENAN (no se suman).

Cubre el bug corregido: `sintetizar()` acumulaba los fragmentos con
`total[:len(f)] += f`, de modo que en textos >900 caracteres (2+ fragmentos)
todos sonaban simultáneamente superpuestos. Se usa un stub de edge-tts
inyectado en sys.modules: no requiere red ni el paquete real.
"""
from __future__ import annotations

import io
import sys
import types
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.lector_texto import LectorTexto, SR_EDGE

FRAG_SEG = 0.25  # duración fija del audio que produce el stub por fragmento


def _instalar_stub_edge_tts() -> None:
    """Sustituye edge_tts por un doble determinista (tono por fragmento)."""

    class FakeCommunicate:
        def __init__(self, texto: str, voz: str):
            self.texto = texto

        def stream(self):
            async def _gen():
                t = np.linspace(0, FRAG_SEG, int(SR_EDGE * FRAG_SEG),
                                endpoint=False)
                # Frecuencia distinta por fragmento: detectable si se suman.
                freq = 200.0 + (hash(self.texto) % 8) * 100.0
                audio = (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)
                buf = io.BytesIO()
                sf.write(buf, audio, SR_EDGE, format="WAV")
                yield {"type": "audio", "data": buf.getvalue()}

            return _gen()

    fake = types.ModuleType("edge_tts")
    fake.Communicate = FakeCommunicate
    sys.modules["edge_tts"] = fake


class TestFragmentosSecuenciales(unittest.TestCase):
    def setUp(self) -> None:
        self._original = sys.modules.get("edge_tts")
        _instalar_stub_edge_tts()

    def tearDown(self) -> None:
        if self._original is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = self._original

    def test_texto_largo_concatena_fragmentos(self):
        texto = ("Una frase con sentido. " * 100).strip()  # >900 chars
        n_frags = len(LectorTexto._fragmentar(texto))
        self.assertGreater(n_frags, 1, "el texto debe partirse en 2+ fragmentos")

        audio, sr = LectorTexto().sintetizar(texto)
        self.assertEqual(sr, SR_EDGE)

        esperado = n_frags * FRAG_SEG
        obtenido = audio.shape[0] / sr
        self.assertAlmostEqual(obtenido, esperado, delta=0.05,
                               msg=f"esperaba ~{esperado:.2f} s concatenando, "
                                   f"obtuve {obtenido:.2f} s "
                                   f"(¿se siguen superponiendo?)")

    def test_texto_corto_un_solo_fragmento(self):
        audio, sr = LectorTexto().sintetizar("Hola, viajero.")
        self.assertAlmostEqual(audio.shape[0] / sr, FRAG_SEG, delta=0.02)

    def test_fragmento_fallido_no_rompe_el_resto(self):
        """Si un fragmento no produce audio, el resto sigue concatenatedo."""
        original = LectorTexto.__dict__["_sintetizar_fragmento"]

        def _a_veces_falla(edge, texto, voz):
            if "sabotaje" in texto:
                return None  # simula fallo de red de UN fragmento
            return original(edge, texto, voz)

        LectorTexto._sintetizar_fragmento = staticmethod(_a_veces_falla)
        try:
            texto = ("Fragmento normal. " * 80) + "sabotaje. " + \
                    ("Otro fragmento normal. " * 20)
            audio, sr = LectorTexto().sintetizar(texto)
            frags_ok = len([f for f in LectorTexto._fragmentar(texto)
                            if "sabotaje" not in f])
            self.assertAlmostEqual(audio.shape[0] / sr,
                                   frags_ok * FRAG_SEG, delta=0.05)
        finally:
            LectorTexto._sintetizar_fragmento = original


class TestFragmentacion(unittest.TestCase):
    """Regresiones de _fragmentar (cortes por oración, límite de tamaño)."""

    def test_texto_vacio(self):
        self.assertEqual(LectorTexto._fragmentar(""), [])

    def test_no_parte_palabras(self):
        texto = "palabra " * 400  # sin puntos: una sola tirada
        frags = LectorTexto._fragmentar(texto)
        self.assertGreater(len(frags), 1)
        for f in frags:
            self.assertLessEqual(len(f), 900)
            self.assertTrue(f.split()[0].startswith("palabra"),
                            "no debe cortar por la mitad de una palabra")

    def test_respeta_oraciones(self):
        texto = "Primera oración." + " Segunda oración." * 100
        frags = LectorTexto._fragmentar(texto)
        self.assertTrue(all(f.endswith(".") for f in frags))


if __name__ == "__main__":
    unittest.main()
