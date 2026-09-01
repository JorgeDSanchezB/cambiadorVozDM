# 🎲 Cambiador de Voz en Tiempo Real para Dungeon Masters

Aplicación de escritorio **Windows 10/11** (también funciona en Linux/macOS con
PortAudio) que transforma tu micrófono en tiempo real para dar vida a tus NPCs
en sesiones de D&D: Goblin, Dragón, Tabernero… o las que inventes.

- **Latencia** configurables de ~25 a ~50 ms (buffer 128–1024 muestras).
- **Modo DSP**: pitch, formantes, distorsión, ring-mod, EQ de 3 bandas y reverb
  construidos dinámicamente desde JSON.
- **Modo IA (opcional)**: clonación de voz vía RVC con detección automática de
  GPU y fallback a DSP.
- **Grabación de la sesión** en MP3 (o WAV si falta ffmpeg).
- **Cero hardcoding**: todas las voces viven en `data/voces/*.json`.

---

## 1. Requisitos

| Requisito | Detalle |
|---|---|
| Python | 3.10 o superior ([python.org](https://www.python.org/downloads/windows/) — marca *Add to PATH*) |
| ffmpeg | Para exportar MP3: `winget install ffmpeg` (o `choco install ffmpeg`) |
| Micrófono | Cualquiera (USB, condensador, auriculares) |
| GPU (opcional) | NVIDIA + PyTorch CUDA, solo para el Modo IA |

## 2. Instalación (Windows)

```powershell
cd cambiador-voz-dnd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
winget install ffmpeg        # si no lo tienes (reinicia la terminal después)
python main.py --verificar   # autochequeo recomendado
python main.py               # ¡a jugar!
```

Linux/macOS: igual con `python3 -m venv` y `pip3`.

## 3. Uso en mesa (cheat-sheet)

| Acción | Cómo |
|---|---|
| Cambiar a Goblin / Dragón / Tabernero | Botón grande en **🎤 Voces** o **F1 / F2 / F3** |
| Volver a tu voz (pánico) | **Esc** (voz Neutral) o **F12** |
| Crear una voz nueva | **🎚️ Editor** → mueve sliders → **▶ Probar** → **📤 Guardar como NUEVA voz** |
| Ajustar latencia | **⚙️ Ajustes** → buffer 128 (PC potente) o 512 (portátil justito) |
| Grabar la sesión | **⏺ Grabar** en 🎤 Voces → **⏹ Detener** → MP3 en tu carpeta |
| Añadir voz a mano | Copia cualquier JSON de `data/voces/`, cambia `id`, `nombre` y valores → botón **Recargar** |

## 4. Estructura del proyecto

```
cambiador-voz-dnd/
├── main.py                    # punto de entrada
├── verificar_instalacion.py   # autochequeo (DSP, ffmpeg, dispositivos)
├── requirements.txt
├── data/
│   ├── config.json            # buffer, dispositivos, carpeta MP3, atajos
│   ├── parametros.json        # catálogo de rangos (Fábrica + Editor lo comparten)
│   └── voces/*.json           # UNA voz por archivo (Neutral, Goblin, Dragón…)
├── dominio/                   # entidades + efectos DSP + fábrica de cadenas
├── aplicacion/                # motor de audio, gestor de voces, grabación, IA
├── infraestructura/           # repositorios JSON + GUI PyQt6
├── modelos/                   # (opcional) plugin RVC + modelos .pth
├── logs/                      # app.log rotativo
└── grabaciones/               # destino por defecto de los MP3
```

## 5. Formato de una voz (`data/voces/*.json`)

```json
{
  "id": "un-uuid-unico-para-esta-voz",
  "nombre": "Orco del Norte",
  "tipo": "DSP",
  "icono": "👹",
  "color": "#4b5563",
  "parametros_dsp": {
    "pitch_semitonos": -3.0,
    "formant_shift": 0.85,
    "gain_db": 1.0,
    "distortion_drive": 0.15,
    "ring_mod_freq": 0.0,
    "eq_low_db": 3.0,
    "eq_mid_db": 0.0,
    "eq_high_db": -2.0,
    "reverb_room_size": 0.1,
    "reverb_damping": 0.5
  }
}
```

Para voces IA usa `"tipo": "IA"` con `parametros_ia` (ver `modelos/LEEME.md`).

## 6. Solución de problemas

| Síntoma | Solución |
|---|---|
| "ffmpeg no encontrado" | `winget install ffmpeg` y reinicia la terminal; mientras tanto la app graba WAV. |
| Sonido entrecortado (overrun) | Sube el buffer a 512/1024 en Ajustes, o cierra apps pesadas. |
| No se oye la voz transformada | Activa "Monitor" en 🎤 Voces y **usa auriculares** para evitar feedback. |
| Latencia alta en IA | Es inherente al modelo (~150–300 ms). Para NPC rápidos usa DSP. |
| Un JSON de voz roto | La app lo ignora, muestra un banner rojo y sigue con la voz Neutral. |
| Ventana borrosa en Windows | Ya está resuelto (High-DPI activado en `main.py`). |

## 7. Privacidad

Todo el audio se procesa **en tu PC**. No hay red, telemetría ni nube (salvo que
actives un modelo IA que tú mismo instales).
