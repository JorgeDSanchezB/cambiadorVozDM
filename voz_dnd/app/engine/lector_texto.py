"""Servicio de lectura de texto con la voz seleccionada (Fase 6).

Flujo: texto plano → voz neural de Microsoft (edge-tts, en línea) → se
re-muestrea a la tasa de muestreo de la app → pasa por el procesador de voz
ACTIVO (ProcesadorDSP o ProcesadorIA/RVC) → resultado float32 mono listo
para guardar en WAV y/o reproducir.

El procesador lo construye la GUI con la MISMA lógica que el micrófono, de
modo que el texto suena exactamente con la voz seleccionada. Este módulo no
sabe nada de Qt: es un servicio de engine que la GUI invoca en un hilo de
trabajo (el TTS es de red y puede ser lento).
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from app.engine.procesador import ProcesadorBase

log = logging.getLogger(__name__)

# Tasa de salida de edge-tts (WebSocket de Azure, fija a 24 kHz).
SR_EDGE = 24000
# Tamaño de bloque al pasar el audio por la cadena de voz (latencia mínima).
BLOQUE_SINTESIS = 4096

# Voces neurales en español disponibles en edge-tts (seleccionable en la GUI).
VOZ_TTS_POR_DEFECTO = "es-MX-DaliaNeural"
_VOZ_TTS_GLOBAL: str = VOZ_TTS_POR_DEFECTO


def configurar_voz_tts(voz: str) -> None:
    """Configura la voz edge-tts global (p. ej. desde la pestaña Lectura)."""
    global _VOZ_TTS_GLOBAL
    _VOZ_TTS_GLOBAL = voz or VOZ_TTS_POR_DEFECTO

def _voz_tts_actual() -> str:
    return _VOZ_TTS_GLOBAL


class LectorTexto:
    """Sintetiza un texto y le aplica la voz procesada del programa.

    API sin estado: cada llamada a `renderizar` es un render nuevo, por lo
    que es seguro usarla desde un hilo de trabajo sin encolado.
    """

    # ------------------------------------------------------------------ #
    def sintetizar(self, texto: str,
                   on_progreso: Callable[[str], None] | None = None
                   ) -> tuple[np.ndarray, int]:
        """Convierte el texto en audio float32 mono (N,1).

        Devuelve (audio, sr_src) con sr_src=24000 (tasa fija de edge-tts).
        Lanza RuntimeError con mensaje útil si edge-tts falla (p. ej. sin red).
        """
        try:
            import edge_tts  # import diferido: dependencia opcional/online
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "edge-tts no está instalado. Ejecuta: pip install edge-tts") from exc

        if on_progreso:
            on_progreso("Sintetizando el texto con la voz neural…")
        fragmentos: list[np.ndarray] = []
        for i, fragmento in enumerate(self._fragmentar(texto), 1):
            audio = self._sintetizar_fragmento(
                edge_tts, fragmento, _voz_tts_actual())
            if audio is not None:
                fragmentos.append(audio)
            if on_progreso:
                on_progreso(f"Sintetizado fragmento {i}…")

        if not fragmentos:
            raise RuntimeError("El texto no produjo audio (¿está vacío?).")

        # Los fragmentos son trozos SECUENCIALES del texto: se concatenan de
        # principio a fin. (Antes se sumaban desde la muestra 0 y todos los
        # fragmentos de un texto largo sonaban a la vez.)
        total = np.concatenate(fragmentos, axis=0).astype(np.float32)
        return total, SR_EDGE

    # ------------------------------------------------------------------ #
    def aplicar_voz(self, audio: np.ndarray, sr_src: int,
                    procesador: ProcesadorBase, sr: int,
                    on_progreso: Callable[[str], None] | None = None
                    ) -> np.ndarray:
        """Pasa el audio sintetizado por la cadena de la voz seleccionada.

        Re-muestrea `audio` (de `sr_src`) a `sr` y lo procesa por bloques
        con `procesador`. Devuelve float32 mono (N,1) a la tasa `sr`.
        """
        if sr_src != sr:
            import librosa
            audio = librosa.resample(
                audio.reshape(-1), orig_sr=sr_src, target_sr=sr).astype(np.float32)
        audio = audio.reshape(-1, 1)

        if on_progreso:
            on_progreso("Aplicando la voz seleccionada…")
        salida = np.zeros((0, 1), dtype=np.float32)
        n = audio.shape[0]
        for inicio in range(0, n, BLOQUE_SINTESIS):
            bloque = audio[inicio: inicio + BLOQUE_SINTESIS]
            procesado = procesador.procesar(bloque, sr)
            procesado = np.asarray(procesado, dtype=np.float32).reshape(-1, 1)
            salida = np.concatenate([salida, procesado], axis=0)
            if on_progreso:
                on_progreso(
                    f"Procesando voz… {min(inicio + BLOQUE_SINTESIS, n)}/{n} muestras")
        return salida.astype(np.float32)

    # ------------------------------------------------------------------ #
    def renderizar(self, texto: str, procesador: ProcesadorBase, sr: int,
                   ruta_wav: Path | None = None,
                   on_progreso: Callable[[str], None] | None = None
                   ) -> np.ndarray:
        """Hace todo el pipeline y (opcional) guarda el WAV.

        Se espera llamarla desde un hilo de trabajo, nunca desde el de audio
        ni el de la GUI (el TTS es de red y el RVC puede tardar).
        """
        audio, sr_src = self.sintetizar(texto, on_progreso)
        if procesador is None:
            salida = audio.reshape(-1, 1)
            if sr_src != sr:
                import librosa
                salida = librosa.resample(
                    salida[:, 0], orig_sr=sr_src, target_sr=sr).reshape(-1, 1)
        else:
            salida = self.aplicar_voz(audio, sr_src, procesador, sr, on_progreso)
        salida = salida.reshape(-1, 1).astype(np.float32)

        if ruta_wav is not None:
            if not isinstance(ruta_wav, Path):
                ruta_wav = Path(str(ruta_wav))
            ruta_wav.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(ruta_wav), salida[:, 0], sr)
            log.info("WAV guardado: %s (%d muestras @ %d Hz)",
                     ruta_wav, salida.shape[0], sr)
        return salida

    # ---------------------------- helpers ------------------------------ #
    @staticmethod
    def _fragmentar(texto: str, max_chars: int = 900) -> list[str]:
        """Divide el texto en fragmentos que edge-tts pueda procesar de una.

        Corta por oraciones/borde de palabra para no partir frases por la
        mitad y no exceder el límite razonable de una sola síntesis.
        """
        texto = (texto or "").strip()
        if not texto:
            return []
        fragmentos: list[str] = []
        buf = ""
        for oracion in re.split(r"(?<=[.?!])\s+|\n+", texto):
            oracion = oracion.strip()
            if not oracion:
                continue
            if len(buf) + len(oracion) + 1 <= max_chars:
                buf = (buf + " " + oracion).strip()
            else:
                if buf:
                    fragmentos.append(buf)
                while len(oracion) > max_chars:
                    corte = oracion.rfind(" ", 0, max_chars)
                    if corte <= 0:
                        corte = max_chars
                    fragmentos.append(oracion[:corte].strip())
                    oracion = oracion[corte:].strip()
                buf = oracion
        if buf:
            fragmentos.append(buf)
        return fragmentos or [texto]

    @staticmethod
    def _sintetizar_fragmento(edge_tts, texto: str, voz: str) -> np.ndarray | None:
        """Sintetiza un fragmento y lo decodifica a float32 mono (N,1)."""
        comunicador = edge_tts.Communicate(texto, voz)
        piezas: list[bytes] = []

        async def _stream() -> None:
            async for chunk in comunicador.stream():
                if chunk["type"] == "audio" and chunk.get("data"):
                    piezas.append(chunk["data"])

        try:
            asyncio.run(_stream())
        except RuntimeError:
            asyncio.get_event_loop().run_until_complete(_stream())

        if not piezas:
            return None
        try:
            audio, _sr = sf.read(io.BytesIO(b"".join(piezas)), dtype="float32")
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo decodificar el audio de edge-tts: %s", exc)
            return None
        if audio.ndim > 1:
            audio = audio[:, 0]
        return audio.reshape(-1, 1).astype(np.float32)


# Voces neurales en español recomendadas para el selector de la GUI.
VOCES_TTS_SUGERIDAS: list[str] = [
    "es-MX-DaliaNeural",
    "es-MX-JorgeNeural",
    "es-MX-BeatrizNeural",
    "es-ES-ElviraNeural",
    "es-ES-AlvaroNeural",
    "es-AR-ElenaNeural",
    "es-CO-GonzaloNeural",
]
