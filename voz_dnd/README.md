# 🎲 Cambiador de Voz en Tiempo Real para DM de D&D

Transforma tu voz **mientras hablas** para dar vida a Goblins, Dragones y
Taberneros en tus sesiones de D&D. Funciona con cualquier micrófono
(USB, condensador, de auriculares) en **Windows 10/11**.

---

## ✨ Características

- **Latencia baja (< 50 ms con buffer 128-256)** gracias a un stream
  full-duplex y efectos DSP vectorizados (numpy/scipy).
- **Voces 100 % extensibles**: cada voz es un JSON en `data/voces/`.
  Añadir "Orco del Norte" = crear un archivo. No se recompila nada.
- **Editor en vivo**: sliders generados automáticamente desde
  `data/parametros.json`, botón "▶ Probar (2 s)" y "Guardar como nueva voz".
- **Atajos de teclado** configurables (F1=Goblin, F2=Dragón, F3=Tabernero).
- **Grabación en MP3** de la voz PROCESADA (requiere ffmpeg; si falta,
  exporta WAV automáticamente).
- **Medidor de nivel**, **timer de grabación**, **monitoreo opcional**.
- **Modo IA opcional** (clonación con RVC) con detección automática de GPU
  y degradación con gracia a DSP.
- **Tolerancia a fallos**: si un JSON de voz está corrupto se omite con un
  banner de aviso y la voz **Neutral** siempre está disponible.

---

## 🚀 Instalación (Windows 10/11)

### Opción rápida (recomendada)
1. Instala **Python 3.10+** desde https://python.org (marca "Add to PATH").
2. (Opcional, para MP3) Instala **ffmpeg**:
   `winget install Gyan.FFmpeg`  — o descárgalo de https://ffmpeg.org
3. Haz **doble clic en `iniciar_voz_dnd.bat`**. La primera vez crea el
   entorno virtual e instala las dependencias automáticamente.

### Opción manual
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

> **Importante**: usa **auriculares**. Si el micrófono "oye" tus altavoces,
> la realimentación arruinará la transformación (y tus oídos).

---

## 🖥️ Uso

| Pestaña | Qué hace |
|---|---|
| **🎤 Voces** | Botones grandes + lista desplegable. La voz activa se resalta. Indica modo (DSP/IA), estado y latencia estimada. |
| **🎚️ Editor** | Sliders (Pitch, Formantes, Reverb, Distorsión, EQ, Ring mod…). "▶ Probar" aplica 2 s de preview. "Guardar como nueva voz" crea un JSON nuevo al instante. |
| **⚙️ Ajustes** | Buffer (128/256/512/1024 → latencia), dispositivos de audio, carpeta y calidad de grabación, ruta de ffmpeg, atajos F1-F12, estado de GPU. |

- **🎤 Grabar**: guarda lo que se **oye** (voz ya transformada). El timer rojo
  muestra el tiempo transcurrido. Al detener, elige la carpeta o abre el MP3.
- **Monitoreo**: desactívalo para grabar sin escucharte.

### Latencia
| Buffer | Latencia aprox. | Recomendación |
|---|---|---|
| 128 | ~25 ms | PC potente + USB/WASAPI |
| 256 | ~31 ms | **Por defecto, seguro** |
| 512 | ~46 ms | PCs modestos |
| 1024 | ~62 ms | Máxima estabilidad |

Si notas chasquidos (dropouts), sube el buffer o revisa
`logs/app.log` (los avisos del driver aparecen en el banner).

---

## ➕ Añadir una voz nueva (Regla de la "Voz Nueva")

### Desde la GUI (sin tocar archivos)
Pestaña **Editor** → ajusta sliders → "▶ Probar" → **"💾 Guardar como nueva
voz…"** → nombre, icono y color. Listo: aparece en Voces y en Voces/D&D.

### Copiando un JSON
Crea `data/voces/orco_norte.json` copiando `goblin.json` y cambia nombre,
icono, color y valores. Pulsa "🔄 Recargar" (o reinicia). Ejemplo mínimo:

```json
{
  "nombre": "Orco del Norte",
  "tipo": "DSP",
  "icono": "🧌",
  "color": "#3b5a7a",
  "parametros_dsp": {
    "pitch_semitonos": -3.5,
    "formant_shift": 1.2,
    "distortion_drive": 0.25,
    "reverb_room_size": 0.1
  }
}
```

Los campos ausentes toman valores neutros y los fuera de rango se recortan
con aviso. Si el JSON está roto, la app lo omite con un banner y sigue
funcionando.

---

## 🧠 Modo IA (opcional): clonación de voz con RVC

El modo IA está **desactivado por defecto en la práctica** hasta que conectes
el motor. La infraestructura ya está preparada:

1. Instala (con GPU NVIDIA + CUDA):
   ```
   pip install torch --index-url https://download.pytorch.org/whl/cu121
   pip install rvc          # o el fork RVC-WebUI que prefieras
   ```
2. Crea una voz de tipo IA (p. ej. `data/voces/goku.json`):
   ```json
   {
     "nombre": "Guerrero Legendario",
     "tipo": "IA",
     "icono": "👑",
     "color": "#7a3b2e",
     "parametros_ia": {
       "modelo_rvc": "modelos/mi_voz.pth",
       "pitch_rvc": -4,
       "index_rate": 0.66,
       "usar_gpu": true
     },
     "dsp_post": { "reverb_room_size": 0.2, "eq_low_db": 2.0 }
   }
   ```
3. Conecta el adaptador en `app/engine/modulo_ia.py` — los puntos de
   integración están marcados en `inicializar()` y `procesar()` (la API
   exacta depende de la versión de RVC; por eso no se hardcodea).

Mientras el modelo carga (o si falla), la voz suena con su cadena `dsp_post`
y la UI muestra el aviso correspondiente. **El audio nunca se corta.**

---

## 🏗️ Arquitectura (resumen de las Fases 1-5)

```
app/
├── domain/     # Capa de Dominio (pura, sin I/O ni Qt)
│   ├── models.py          # IVoiceProfile, PerfilDSP, PerfilIA, ParametrosDSP
│   ├── catalogo.py        # Rangos desde data/parametros.json (cero hardcoding)
│   └── efectos.py         # PitchShifter, FormantShifter, Distorsion, Reverb…
├── engine/     # Capa de Aplicación (orquestación)
│   ├── fabrica_cadena.py  # JSON → cadena de efectos (Chain of Responsibility)
│   ├── procesador.py      # ProcesadorDSP / ProcesadorIA / Bypass
│   ├── modulo_ia.py       # RVC opcional con detección de GPU
│   ├── motor_audio.py     # sd.Stream full-duplex + callback RT-safe
│   ├── gestor_voces.py    # CRUD JSON + tolerancia a fallos + Neutral
│   └── gestor_grabacion.py# tap post-DSP → MP3 (pydub) con fallback WAV
├── gui/        # Infraestructura UI (PyQt6)
│   ├── main_window.py     # Barra REC/medidor + 3 pestañas + atajos
│   ├── pestana_voces.py   # Botones grandes desde JSON
│   ├── pestana_editor.py  # Sliders data-driven + preview 2 s
│   ├── pestana_ajustes.py # Buffer, dispositivos, MP3, atajos, GPU
│   ├── medidor_nivel.py   # Medidor pintado a mano (30 FPS por polling)
│   └── widgets.py         # Banner de avisos
└── data/
    ├── config.json        # Buffer, dispositivos, carpeta MP3, atajos
    ├── parametros.json    # Rangos de cada slider (única fuente de verdad)
    └── voces/*.json       # Una voz = un archivo
```

**Flujo de audio**: `Micrófono → sd.Stream (callback RT) → cadena de efectos
(inter cambio de referencia, sin locks) → altavoces`, con un "tap" post-DSP
que alimenta la grabación. La GUI consulta el estado por polling (33 ms) y
nunca recibe llamadas desde el hilo de audio.

---

## 🩺 Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| No se oye nada | Revisa Monitoreo ✓, dispositivo de salida en Ajustes, y que la voz Neutral funcione. |
| Chasquidos/artefactos | Sube el buffer a 512/1024; cierra apps pesadas; usa WASAPI por defecto. |
| No exporta MP3 | Falta ffmpeg → `winget install Gyan.FFmpeg` o indica la ruta en Ajustes. Exportará WAV mientras tanto. |
| "Archivo dañado y omitido" | El JSON de esa voz está roto; revísalo o bórralo. La voz Neutral sigue disponible. |
| Modo IA no activa | Mira el banner: sin PyTorch/GPU o modelo .pth no encontrado. Se degrada a DSP sin cortar el audio. |
| Realimentación (aullido) | Usa auriculares o desactiva Monitoreo. |

Registra todo en `logs/app.log` (rotativo, 1 MB × 3).

---

## 📜 Licencia de uso

Proyecto de mesa: úsalo, modifícalo y compártelo con tu grupo. ¡Que role
naturalmente! 🎲
