"""Autoverificación de la instalación (sin GUI): python main.py --verificar

Comprueba, en orden:
  1. Dependencias Python (numpy, scipy, sounddevice, PyQt6, pydub).
  2. ffmpeg (MP3) — con recomendación de instalación si falta.
  3. Dispositivos de audio accesibles vía PortAudio.
  4. Tolerancia a fallos: carga de voces con un JSON corrupto sembrado a propósito.
  5. Cadena DSP: tono de prueba por Goblin → se verifica el pitch, la reverb
     responde a impulsos y el EQ gana lo prometido.
"""
from __future__ import annotations

import json
import queue
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

OK = "  ✔"
MAL = "  ✖"
INFO = "  •"


def _tono(frecuencia: float, segundos: float, sr: int) -> np.ndarray:
    t = np.arange(int(sr * segundos)) / sr
    return (0.5 * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def _pico_espectral(x: np.ndarray, sr: int) -> float:
    espectro = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    frecuencia = np.fft.rfftfreq(len(x), 1.0 / sr)
    return float(frecuencia[int(np.argmax(espectro))])


def ejecutar(raiz: Path, con_gui: bool = True) -> int:
    print("\n=== AUTOVERIFICACIÓN · Cambiador de Voz D&D ===\n")
    fallos = 0

    # 1) Dependencias ------------------------------------------------------
    for modulo in ("numpy", "scipy", "sounddevice", "PyQt6", "pydub"):
        try:
            __import__(modulo)
            print(f"{OK} Paquete {modulo}")
        except ImportError:
            print(f"{MAL} Paquete {modulo} — pip install -r requirements.txt")
            fallos += 1

    # 2) ffmpeg ------------------------------------------------------------
    if shutil.which("ffmpeg") or _pydub_ffmpeg_ok():
        print(f"{OK} ffmpeg (exportación MP3 lista)")
    else:
        print(f"{MAL} ffmpeg NO encontrado → las grabaciones saldrán en WAV")
        print(f"{INFO} Instálalo con:  winget install ffmpeg")
        fallos += 1

    # 3) Dispositivos de audio --------------------------------------------
    try:
        import sounddevice as sd

        entradas = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        salidas = [d for d in sd.query_devices() if d["max_output_channels"] > 0]
        print(f"{OK} PortAudio: {len(entradas)} entradas / {len(salidas)} salidas")
        if not entradas or not salidas:
            print(f"{MAL} Se necesitan micrófono y altavoces")
            fallos += 1
    except Exception as exc:
        print(f"{MAL} PortAudio inaccesible: {exc}")
        fallos += 1

    # 4) GestorVoces con JSON corrupto (tolerancia a fallos) ---------------
    try:
        from aplicacion.gestor_voces import GestorVoces
        from infraestructura.repositorios import RepoCatalogo

        catalogo = RepoCatalogo(raiz / "data" / "parametros.json").cargar()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy(raiz / "data" / "voces" / "goblin.json", tmp_path / "goblin.json")
            (tmp_path / "rota.json").write_text("{ id: este json está roto", encoding="utf-8")
            eventos: queue.SimpleQueue = queue.SimpleQueue()
            gestor = GestorVoces(tmp_path, catalogo, eventos)
            voces = gestor.cargar_todas()
            corruptas = [
                e for e in _vaciar(eventos) if e[0] == "voz_corrupta"
            ]
            if len(voces) == 1 and corruptas and any(
                v.nombre == "Neutral" for v in voces
            ):
                print(f"{OK} JSON corrupto ignorado con aviso + Neutral garantizada")
            else:
                print(f"{MAL} Tolerancia a fallos: voces={len(voces)} corruptas={len(corruptas)}")
                fallos += 1
    except Exception as exc:
        print(f"{MAL} GestorVoces: {exc}")
        fallos += 1

    # 5) Cadena DSP real (Goblin) ------------------------------------------
    try:
        from dominio.entidades import ParametrosDSP, PerfilDSP
        from dominio.fabrica_cadena import FabricaCadena

        sr = 48000
        datos = json.loads((raiz / "data" / "voces" / "goblin.json").read_text("utf-8"))
        perfil = PerfilDSP(
            id=datos["id"], nombre=datos["nombre"], tipo="DSP",
            parametros_dsp=ParametrosDSP.desde_dict(datos["parametros_dsp"]),
        )
        cadena = FabricaCadena.construir(perfil.parametros_dsp, sr)

        # 5a) Pitch: 220 Hz → debe subir ~5.5 semitonos (≈ 309.6 Hz)
        tono = _tono(220.0, 1.2, sr)
        salida = FabricaCadena.probar_cadena(cadena, tono, sr)
        esperado = 220.0 * 2 ** (perfil.parametros_dsp.pitch_semitonos / 12.0)
        medido = _pico_espectral(salida[len(salida) // 3:], sr)
        if abs(medido - esperado) / esperado < 0.12:
            print(f"{OK} PitchShifter: 220 Hz → {medido:.1f} Hz (esperado ≈ {esperado:.1f})")
        else:
            print(f"{MAL} PitchShifter: medido {medido:.1f} Hz, esperado {esperado:.1f} Hz")
            fallos += 1
        if np.isfinite(salida).all() and np.abs(salida).max() <= 1.5:
            print(f"{OK} Cadena completa: salida finita y acotada (pico {np.abs(salida).max():.2f})")
        else:
            print(f"{MAL} Salida DSP no acotada")
            fallos += 1

        # 5b) Reverb: un impulso debe producir cola (energía posterior)
        from dominio.efectos import Reverb

        reverb = Reverb(sr, 0.5, 0.4)
        impulso = np.zeros(sr, dtype=np.float32)
        impulso[10] = 1.0
        cola = reverb.procesar(impulso, sr)
        energia_temprana = float(np.sum(cola[: int(0.02 * sr)] ** 2))
        energia_cola = float(np.sum(cola[int(0.05 * sr): int(0.4 * sr)] ** 2))
        if energia_cola > energia_temprana * 0.05 and energia_cola > 0:
            print(f"{OK} Reverb: cola presente (energía 50–400 ms > umbral)")
        else:
            print(f"{MAL} Reverb: sin cola detectable")
            fallos += 1

        # 5c) EQ low-shelf +6 dB en graves
        from dominio.efectos import BiquadEQ

        eq = BiquadEQ(sr, "low_shelf", 120.0, 6.0)
        graves = _tono(50.0, 1.0, sr)
        salidas_eq = eq.procesar(graves, sr)
        ganancia = float(np.abs(salidas_eq[len(salidas_eq) // 2:]).mean() /
                         np.abs(graves[len(graves) // 2:]).mean())
        ganancia_db = 20 * np.log10(max(ganancia, 1e-9))
        if abs(ganancia_db - 6.0) < 2.0:
            print(f"{OK} EQ graves: {ganancia_db:+.1f} dB @ 50 Hz (esperado ≈ +6)")
        else:
            print(f"{MAL} EQ graves: {ganancia_db:+.1f} dB (esperado ≈ +6)")
            fallos += 1

        # 5d) Latencia estimada de la cadena
        latencia_ms = FabricaCadena.latencia_total_muestras(cadena) / sr * 1000.0
        print(f"{INFO} Latencia algorítmica de la cadena Goblin: {latencia_ms:.1f} ms")
    except Exception as exc:
        print(f"{MAL} Cadena DSP: {exc}")
        fallos += 1

    print("\n=== RESULTADO:", "TODO CORRECTO ✅" if fallos == 0 else f"{fallos} PROBLEMA(S) ❌", "===\n")
    return 0 if fallos == 0 else 1


def _pydub_ffmpeg_ok() -> bool:
    try:
        from pydub import AudioSegment

        return bool(AudioSegment.converter)
    except Exception:
        return False


def _vaciar(cola: "queue.SimpleQueue") -> list[tuple]:
    elementos = []
    while True:
        try:
            elementos.append(cola.get_nowait())
        except queue.Empty:
            return elementos


if __name__ == "__main__":
    raise SystemExit(ejecutar(Path(__file__).resolve().parent))
