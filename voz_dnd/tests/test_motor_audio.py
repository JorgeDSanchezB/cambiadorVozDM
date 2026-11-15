"""MotorAudio (headless): invariante "el audio nunca se pierde" en caliente.

Cubre el caso corregido: cambiar ajustes de audio (buffer/dispositivos)
con una grabación en curso recreaba el GestorGrabacion y el audio
acumulado quedaba huérfano (pérdida silenciosa de la sesión). Ahora
aplicar_config_audio() lo rechaza con error claro.

También congela el contrato del callback RT (formas, bypass, monitoreo)
sin necesitar dispositivos de audio reales.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigApp, ConfigGrabacion
from app.engine.gestor_grabacion import GestorGrabacion
from app.engine.motor_audio import MotorAudio
from app.engine.procesador import ProcesadorBypass


def _bloque(frames: int = 256) -> np.ndarray:
    return (np.random.randn(frames, 1) * 0.1).astype(np.float32)


class TestCambioConfigEnCaliente(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cfg = ConfigApp()          # sin stream: entorno headless
        # Higiene: NUNCA exportar a la carpeta real del usuario
        # (~/Music/SesionesDnD); los tests usan su propio temporal.
        self.cfg.grabacion.carpeta_destino = self._td.name
        self.motor = MotorAudio(self.cfg, ProcesadorBypass())

    def test_grabacion_activa_bloquea_el_cambio(self):
        self.motor.grabador.iniciar()
        for _ in range(5):
            self.motor.grabador.tap(_bloque())
        duracion_antes = self.motor.grabador.duracion()

        with self.assertRaises(RuntimeError) as ctx:
            self.motor.aplicar_config_audio(ConfigApp())
        self.assertIn("grabación en curso", str(ctx.exception))
        self.assertTrue(self.motor.grabador.activo,
                        "la grabación debe seguir activa e intacta")
        self.assertAlmostEqual(self.motor.grabador.duracion(), duracion_antes)
        # El audio sigue intacto: el export posterior recupera la sesión.
        with mock.patch.object(GestorGrabacion, "_hay_ffmpeg",
                               return_value=(False, None)):
            ruta, _ = self.motor.grabador.detener_y_exportar()
        self.assertIsNotNone(ruta)

    def test_audio_pendiente_de_exportar_bloquea_el_cambio(self):
        """Tras un fallo total de export, el audio preservado también se protege.

        Hallazgo del árbitro (ronda 2): el guard solo miraba `activo`, y
        recrear el grabador descartaba el audio pendiente en silencio.
        """
        self.motor.grabador.iniciar()
        for _ in range(5):
            self.motor.grabador.tap(_bloque())
        with mock.patch.object(GestorGrabacion, "_hay_ffmpeg",
                               return_value=(False, None)), \
             mock.patch.object(GestorGrabacion, "_exportar_wav",
                               side_effect=OSError("disco lleno")), \
             mock.patch.object(GestorGrabacion, "_temporal_wav",
                               return_value=None):
            ruta, _ = self.motor.grabador.detener_y_exportar()
        self.assertIsNone(ruta)
        self.assertFalse(self.motor.grabador.activo)
        self.assertGreater(self.motor.grabador.duracion(), 0.0,
                           "el audio pendiente debe existir tras el fallo")

        with self.assertRaises(RuntimeError) as ctx:
            self.motor.aplicar_config_audio(ConfigApp())
        self.assertIn("pendiente de exportar", str(ctx.exception))
        self.assertGreater(self.motor.grabador.duracion(), 0.0,
                           "el guard debe impedir que se descarte el audio")

        # ...pero un cambio de carpeta/calidad SÍ llega (remedio de 004):
        self.motor.grabador.actualizar_config(
            ConfigGrabacion(carpeta_destino=tempfile.gettempdir()),
            ffmpeg_ruta="")
        with mock.patch.object(GestorGrabacion, "_hay_ffmpeg",
                               return_value=(False, None)):
            ruta2, _ = self.motor.grabador.detener_y_exportar()
        self.assertIsNotNone(ruta2, "el remedio documentado debe funcionar")
        self.addCleanup(ruta2.unlink, missing_ok=True)

    def test_sin_grabacion_el_cambio_aplica(self):
        nueva = ConfigApp()
        nueva.audio.buffer_size = 512
        self.motor.aplicar_config_audio(nueva)  # no debe lanzar
        self.assertEqual(self.motor.sr, nueva.audio.sample_rate)


class TestContratoCallback(unittest.TestCase):
    """El callback RT nunca lanza y respeta formas (frames,1)."""

    def setUp(self) -> None:
        self.motor = MotorAudio(ConfigApp(), ProcesadorBypass())

    def _llamar_callback(self, frames: int) -> np.ndarray:
        indata = _bloque(frames)
        outdata = np.zeros((frames, 1), dtype=np.float32)
        self.motor._callback(indata, outdata, frames, None, None)
        return outdata

    def test_bypass_pasa_el_audio(self):
        indata = _bloque(128)
        outdata = np.zeros((128, 1), dtype=np.float32)
        self.motor._callback(indata, outdata, 128, None, None)
        self.assertTrue(np.allclose(outdata, indata),
                        "Bypass debe ser paso recto")

    def test_monitoreo_apagado_silencia(self):
        self.motor.monitoreo = False
        outdata = self._llamar_callback(128)
        self.assertTrue(np.allclose(outdata, 0.0))

    def test_reproduccion_dominia_al_microfono(self):
        audio = _bloque(1000)
        self.motor.reproducir(audio)
        outdata = self._llamar_callback(256)
        self.assertTrue(np.allclose(outdata[:, 0], audio[:256, 0]))
        self.assertTrue(self.motor.reproduciendo)
        self.motor.detener_reproduccion()
        self.assertFalse(self.motor.reproduciendo)

    def test_reproduccion_parcial_rellena_con_silencio(self):
        audio = _bloque(100)
        self.motor.reproducir(audio)
        outdata = self._llamar_callback(256)
        self.assertTrue(np.allclose(outdata[:100, 0], audio[:, 0]))
        self.assertTrue(np.allclose(outdata[100:, 0], 0.0))
        self.assertFalse(self.motor.reproduciendo)

    def test_status_de_driver_no_rompe(self):
        indata = _bloque(64)
        outdata = np.zeros((64, 1), dtype=np.float32)
        self.motor._callback(indata, outdata, 64, None, "input overflow")
        errores = self.motor.extraer_errores()
        self.assertTrue(any("overflow" in e for e in errores))


if __name__ == "__main__":
    unittest.main()
