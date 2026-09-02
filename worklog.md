---
Task ID: 6
Agent: Z.ai Code (principal)
Task: Fase 6 — Código fuente completo del Cambiador de Voz en Tiempo Real para DM de D&D (Python 3.10+, PyQt6, SoundDevice, Numpy/Scipy, Pydub, JSON)

Work Log:
- Creado el proyecto completo en /home/z/my-project/voz_dnd/ (30 archivos fuente + datos, 39 en ZIP).
- Capa de Dominio: models.py (IVoiceProfile/PerfilDSP/PerfilIA + deserialización tolerante), catalogo.py (rangos desde data/parametros.json), efectos.py (PitchShifter granular, FormantShifter cepstral STFT, Distorsion tanh, RingMod, EQ RBJ 3 bandas, Reverb Schroeder 4+2, Ganancia; todos vectorizados y RT-safe).
- Capa de Aplicación: config.py (RepoConfig tolerante a fallos), fabrica_cadena.py (JSON→cadena dinámica, efectos neutros omitidos), procesador.py (DSP/IA/Bypass), modulo_ia.py (RVC opcional con detección de GPU y degradación con gracia), motor_audio.py (sd.Stream full-duplex, callback RT sin locks), gestor_voces.py (CRUD JSON + Neutral garantizada), gestor_grabacion.py (tap post-DSP → MP3 pydub con fallback WAV).
- Infraestructura GUI PyQt6: main_window.py (3 pestañas, medidor 33ms, timer REC 500ms, atajos F1-F12, exportación en hilo), pestana_voces.py (botones grandes 150x96 desde JSON), pestana_editor.py (sliders data-driven + preview 2s), pestana_ajustes.py (buffer/dispositivos/MP3/atajos/GPU), medidor_nivel.py, widgets.py (banner de avisos).
- Datos: config.json, parametros.json (10 parámetros), 4 voces (neutral/goblin/dragon/tabernero). Extra: requirements.txt, README.md completo, iniciar_voz_dnd.bat.
- Bugs reales encontrados y corregidos por la verificación: (1) ffmpeg 7.x rechaza bitrate "192kbps" → corregido a "192k"; (2) el callback pasaba arrays 1-D a efectos que esperan (frames,1) → contrato normalizado en motor_audio; (3) latencia inicial 63 ms > objetivo → reducido grano pitch a 512 (configurable) y FFT de formantes a 512 → 41 ms.
- Verificación ejecutada: py_compile OK de 21 módulos; smoke test DSP headless (carga de voces, JSON corrupto omitido, cadenas dinámicas, 20 s de audio por voz a ~4.7% de CPU de 1 núcleo, MP3 real exportado); verificación GUI offscreen con PyQt6 (ventana completa, cambio de voz por señales, preview+restauración, voz IA degradada sin cortar audio, REC→MP3, callback RT 400 bloques sin errores); pruebas acústicas (pitch +5.5/-6/+12 st verificado por energía espectral 96.6%, formantes 0.75/1.35 verificados por centroide, formante neutro = bypass exacto).

Stage Summary:
- Fase 6 COMPLETA y VERIFICADA: proyecto Python ejecutable en /home/z/my-project/voz_dnd/ y empaquetado en /home/z/my-project/voz_dnd_fase6.zip (51 KB, 39 archivos).
- Métricas finales: latencia estimada 41 ms con buffer 256 y cadena completa (objetivo <50 ms cumplido), CPU ≈4.7% de un núcleo por voz completa, tolerancia a fallos verificada (JSON corrupto, voz IA sin GPU, ffmpeg ausente→WAV).
- Limitación del sandbox: no hay micrófono/PortAudio, por lo que el stream real (sounddevice) no pudo abrirse aquí; el callback se verificó con datos sintéticos y el arranque con audio real quedará probado en el PC Windows del usuario (iniciar_voz_dnd.bat).
