"""GestorGrabacion: la sesión grabada jamás se pierde por fallos de exportación.

Cubre el bug corregido: una ruta de ffmpeg configurada inexistente hacía
que pydub usara esa ruta mala, la exportación MP3 lanzara
FileNotFoundError y los bloques (ya limpiados) se perdieran para siempre.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigGrabacion
from app.engine.gestor_grabacion import GestorGrabacion


def _grabar(gr: GestorGrabacion, bloques: int = 10, frames: int = 256) -> None:
    gr.iniciar()
    for _ in range(bloques):
        gr.tap(np.random.randn(frames, 1).astype(np.float32) * 0.1)


class TestRutaFfmpegInvalida(unittest.TestCase):
    """Ruta configurada inexistente: se ignora con aviso, no rompe nada."""

    def test_ruta_invalida_con_ffmpeg_en_path_exporta_mp3(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("este entorno no tiene ffmpeg en el PATH")
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=td), 48000,
                ffmpeg_ruta="/no/existe")
            _grabar(gr)
            ruta, aviso = gr.detener_y_exportar()
            self.assertIsNotNone(ruta, "la grabación no debe perderse")
            self.assertEqual(ruta.suffix, ".mp3")
            self.assertIn("no existe", aviso)  # avisa de la ruta ignorada

    def test_ruta_invalida_sin_ffmpeg_exporta_wav(self):
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=td), 48000,
                ffmpeg_ruta="/no/existe")
            _grabar(gr)
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, "ruta ignorada")):
                ruta, aviso = gr.detener_y_exportar()
            self.assertIsNotNone(ruta)
            self.assertEqual(ruta.suffix, ".wav")
            self.assertIsNotNone(aviso)

    def test_hay_ffmpeg_sanea_converter_de_pydub(self):
        """Una ruta mala NO debe quedar asignada a AudioSegment.converter."""
        from pydub import AudioSegment
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=td), 48000,
                ffmpeg_ruta="/no/existe")
            hay, _ = gr._hay_ffmpeg()
            self.assertEqual(AudioSegment.converter, "ffmpeg")
            self.assertEqual(hay, shutil.which("ffmpeg") is not None)


class TestDegradacionEnCascada(unittest.TestCase):
    """MP3 falla → WAV; WAV falla → WAV en temporal; todo falla → memoria."""

    def test_carpeta_destino_inutilizable_rescata_en_temporal(self):
        """Carpeta ocupada por un FICHERO (mkdir imposible) → temporal.

        Antes esta excepción saltaba por encima de la cascada y nunca se
        intentaba el WAV en temporal (hallazgo del árbitro, defecto menor 2).
        """
        with tempfile.TemporaryDirectory() as td:
            ocupador = Path(td) / "ocupado"
            ocupador.write_text("soy un fichero", encoding="utf-8")
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=str(ocupador)), 48000)
            _grabar(gr)
            ruta, aviso = gr.detener_y_exportar()
            self.addCleanup(ruta.unlink, missing_ok=True)  # higiene /tmp
            self.assertIsNotNone(ruta, "debe rescatar la sesión en temporal")
            self.assertEqual(ruta.suffix, ".wav")
            self.assertIn(tempfile.gettempdir(), str(ruta))
            self.assertIn("carpeta de grabación", aviso)

    def test_patron_de_nombre_roto_rescata_en_temporal(self):
        """Un patron_nombre inválido en config no puede costar la sesión."""
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=td, patron_nombre="{roto"),
                48000)
            _grabar(gr)
            ruta, aviso = gr.detener_y_exportar()
            self.addCleanup(ruta.unlink, missing_ok=True)  # higiene /tmp
            self.assertIsNotNone(ruta)
            self.assertEqual(ruta.suffix, ".wav")

    def test_fallo_mp3_cae_a_wav(self):
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            _grabar(gr)
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(True, None)), \
                 mock.patch.object(
                    GestorGrabacion, "_exportar_mp3",
                    side_effect=RuntimeError("boom mp3")):
                ruta, aviso = gr.detener_y_exportar()
            self.assertIsNotNone(ruta, "el fallo MP3 no debe perder la sesión")
            self.assertEqual(ruta.suffix, ".wav")
            self.assertIn("WAV", aviso)

    def test_fallo_wav_guarda_en_temporal(self):
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            _grabar(gr)
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, None)), \
                 mock.patch.object(
                    GestorGrabacion, "_exportar_wav",
                    side_effect=OSError("disco lleno")):
                ruta, aviso = gr.detener_y_exportar()
            self.addCleanup(ruta.unlink, missing_ok=True)  # higiene /tmp
            self.assertIsNotNone(ruta, "debe rescatar la sesión en temporal")
            self.assertEqual(ruta.suffix, ".wav")
            self.assertIn("perderla", aviso)

    def test_fallo_total_conserva_audio_para_reintentar(self):
        """Si todas las vías fallan, el audio queda en memoria (reintentable)."""
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            _grabar(gr)
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, None)), \
                 mock.patch.object(
                    GestorGrabacion, "_exportar_wav",
                    side_effect=OSError("disco lleno")), \
                 mock.patch.object(
                    GestorGrabacion, "_temporal_wav",
                    return_value=None):
                ruta, aviso = gr.detener_y_exportar()
            self.assertIsNone(ruta)
            self.assertIn("memoria", aviso)
            self.assertGreater(gr.duracion(), 0.0,
                               "los bloques deben conservarse para reintentar")
            # Reintento (ya sin fallos simulados): la sesión sale intacta.
            # (El formato depende del ffmpeg real del entorno: MP3 o WAV.)
            ruta2, _ = gr.detener_y_exportar()
            self.assertIsNotNone(ruta2)
            self.assertIn(ruta2.suffix, (".wav", ".mp3"))

    def test_actualizar_config_permite_rescatar_con_otra_carpeta(self):
        """Cambio de carpeta en Ajustes → el reintento exporta a la nueva.

        Remedio documentado en decisión 004: sin recrear el grabador, el
        audio pendiente se exporta a la carpeta recién elegida.
        """
        with tempfile.TemporaryDirectory() as td_mala, \
                tempfile.TemporaryDirectory() as td_buena:
            gr = GestorGrabacion(
                ConfigGrabacion(carpeta_destino=td_mala), 48000)
            _grabar(gr)
            # Fallo total en la carpeta original.
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, None)), \
                 mock.patch.object(
                    GestorGrabacion, "_exportar_wav",
                    side_effect=OSError("sin permisos")), \
                 mock.patch.object(
                    GestorGrabacion, "_temporal_wav",
                    return_value=None):
                ruta, _ = gr.detener_y_exportar()
            self.assertIsNone(ruta)
            self.assertGreater(gr.duracion(), 0.0)
            # El usuario cambia la carpeta en Ajustes (GUI → actualizar_config)
            # y reintenta: la sesión sale en la carpeta nueva.
            gr.actualizar_config(ConfigGrabacion(carpeta_destino=td_buena),
                                 ffmpeg_ruta="")
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, None)):
                ruta2, _ = gr.detener_y_exportar()
            self.assertIsNotNone(ruta2)
            self.assertEqual(ruta2.parent, Path(td_buena))
            self.assertEqual(gr.duracion(), 0.0)

    def test_dos_rescates_no_se_pisan(self):
        """Nombres de rescate con microsegundos: sin colisión en el mismo segundo."""
        pcm = np.zeros(16, dtype=np.int16)
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            a = gr._temporal_wav(pcm)
            b = gr._temporal_wav(pcm)
            self.assertIsNotNone(a)
            self.assertIsNotNone(b)
            self.assertNotEqual(a, b, "dos rescates inmediatos deben no coincidir")

    def test_exito_descarta_bloques(self):
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            _grabar(gr)
            with mock.patch.object(
                    GestorGrabacion, "_hay_ffmpeg",
                    return_value=(False, None)):
                ruta, _ = gr.detener_y_exportar()
            self.assertIsNotNone(ruta)
            self.assertEqual(gr.duracion(), 0.0, "tras éxito se descarta")


class TestComportamientoPreservado(unittest.TestCase):
    """Regresiones del comportamiento correcto preexistente."""

    def test_sin_audio_capturado(self):
        with tempfile.TemporaryDirectory() as td:
            gr = GestorGrabacion(ConfigGrabacion(carpeta_destino=td), 48000)
            gr.iniciar()
            ruta, aviso = gr.detener_y_exportar()
            self.assertIsNone(ruta)
            self.assertIn("No se capturó", aviso)

    def test_limite_de_duracion_auto_stop(self):
        gr = GestorGrabacion(ConfigGrabacion(), 1000)  # sr bajo: rápido
        gr.iniciar()
        gr._frames_acumulados = 7200 * 1000 - 1  # a punto del límite
        gr.tap(np.zeros((4, 1), dtype=np.float32))
        self.assertFalse(gr.activo, "el auto-stop del límite debe activarse")


if __name__ == "__main__":
    unittest.main()
