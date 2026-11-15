"""Tests del motor (headless, sin PyQt6 ni dispositivos de audio).

Ejecutar desde `voz_dnd/`:
    python -m unittest discover -s tests -v

Solo usan la librería estándar + las dependencias core del motor
(numpy/scipy), ya cubiertas por requirements.txt. Los módulos con imports
diferidos (sounddevice, PyQt6, edge-tts, pydub) se stubbean o parchean.
"""
