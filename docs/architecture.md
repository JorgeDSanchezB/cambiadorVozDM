# Arquitectura — Cambiador de Voz para DM de D&D (`voz_dnd`)

> Documento de referencia rápida del cómo funciona el sistema. Para el estado
> actual del trabajo ver [`current-state.md`](current-state.md). Para las
> decisiones de diseño ver [`decisions/`](decisions/).
>
> El código es la fuente de verdad; este documento describe la estructura y
> los contratos que los cambios deben respetar.

## Lema

**El audio en tiempo real no debe morir jamás.** Todo el diseño (capas,
degradación, tolerancia a fallos) existe para garantizar que el stream de
micrófono nunca se rompa ni bloquee, y que la app siga arrancando aunque un
JSON, un modelo o un motor estén rotos.

## Capas (una dependencia, una dirección)

```
app/
├── domain/   # puro: sin I/O ni Qt
│   ├── models.py        # IVoiceProfile, PerfilDSP, PerfilIA, ParametrosDSP/IA
│   ├── catalogo.py      # rangos desde data/parametros.json (cero hardcoding)
│   └── efectos.py       # PitchShifter, FormantShifter, Distorsion, RingMod,
│                        #   EQ RBJ 3 bandas, Reverb Schroeder, Ganancia
├── engine/   # orquestación (audio + registro)
│   ├── fabrica_cadena.py # JSON → cadena de efectos (Chain of Responsibility)
│   ├── procesador.py     # ProcesadorDSP / ProcesadorIA / ProcesadorBypass
│   ├── modulo_ia.py      # ModuloIA: detecta backend y orquesta el modelo RVC
│   ├── rvc_adapter.py    # adaptador multimotor RVC (PyTorch → ONNX → None)
│   ├── motor_audio.py    # sd.Stream full-duplex + callback RT-safe
│   ├── gestor_voces.py   # CRUD JSON + tolerancia a fallos + Neutral
│   └── gestor_grabacion.py # tap post-DSP → MP3 (pydub) con fallback WAV
└── gui/      # PyQt6
    ├── main_window.py     # barra REC/medidor + 3 pestañas + atajos
    ├── pestana_voces.py   # botones grandes desde JSON
    ├── pestana_editor.py  # sliders data-driven + preview 2 s
    ├── pestana_ajustes.py # buffer, dispositivos, MP3, atajos, estado GPU
    ├── medidor_nivel.py   # medidor pintado (polling 33 ms)
    └── widgets.py         # banner de avisos
```

- **`domain/` no conoce a `engine/` ni a `gui/`; `gui/` conoce a `engine/`
  y a `domain/`.** Mantén esa dirección de dependencia.
- `app/rutas.py` es la **única fuente de verdad** de rutas: `data/`,
  `data/voces/`, `config.json`, `parametros.json`, `logs/`. No hardcodees
  rutas en otros módulos.

## Flujo de audio (contrato de tiempo real)

```
Micrófono → sd.Stream (callback RT) → cadena de efectos → altavoces
                                        └────────────► "tap" → grabación MP3
```

1. La GUI **nunca recibe llamadas desde el hilo de audio**; consulta estado
   por polling (33 ms) y medidor (30 FPS).
2. El `MotorAudio` intercambia la **referencia** al procesador de forma
   atómica (sin locks, seguro bajo el GIL de CPython).
3. **Arrays**: los efectos esperan `(frames, 1)` float32. Un array 1-D los
   rompe. Normaliza con `reshape(-1, 1)` antes y después (ver `motor_audio.py`).
4. El callback no debe lanzar excepciones ni bloquear.

Procesadores intercambiables (`procesador.py`), todos exponen
`procesar(bloque, sr) -> np.ndarray`:

| Procesador | Uso | Notas |
|---|---|---|
| `ProcesadorBypass` | Voz Neutral / emergencia | paso recto, nunca bloquea |
| `ProcesadorDSP` | Modo base | cadena local desde `parametros_dsp` |
| `ProcesadorIA` | Modo avanzado | RVC (si listo) + cadena `dsp_post` |

## Modo IA: multimotor con degradación

`ModuloIA` no conoce las APIs de los motores. Delega en `rvc_adapter.py`, que
prueba en orden y devuelve un objeto con `.listo` y `.procesar()`:

1. **Motor PyTorch RVC** → paquete `rvc`/`rvc_python` (CUDA/ROCm/MPS).
2. **Motor ONNX RVC** → `onnxruntime` (CPU/DirectML/CUDA), portátil.
3. **Ninguno** → `None` y el modo IA degrada a DSP.

Regla de oro: **`esta_listo() == False` es un estado correcto y esperado**
cuando la máquina no tiene motor/modelo. El audio sigue sonando por la cadena
DSP sin caerse. La UI marca `degradado` con un aviso.

Cada instalación puede **inyectar su propio `adapter=`** a `ModuloIA`, con
prioridad sobre los motores embebidos. No rompas ese seam.

## Datos (data-driven)

- **`parametros.json`**: rangos/etiquetas de cada slider (única fuente de
  verdad de límites; ningún número mágico en la lógica).
- **`voces/*.json`**: una voz = un archivo. Garantía: existe la voz `neutral`.
  Se añade una voz creando un JSON (no código).
- **`config.json`**: buffer, dispositivos, carpeta de grabación, atajos
  `tecla → id_voz`.
- **Tolerancia a fallos**: JSON corrupto/faltante → omitir y avisar con banner,
  nunca bloquear el arranque.

## Grabación

`gestor_grabacion.tap(bloque)` recoge el audio **post-DSP** (lo que se oye).
Exporta MP3 vía `pydub`/`ffmpeg`; si ffmpeg falta, cae a WAV automáticamente.
Avisos de ffmpeg ausente se muestran en Ajustes/GUI.

## Convenciones de estilo

- Código en **español** (identificadores, comentarios, logs, JSON).
- Sin comentarios salvo que aporten valor real.
- Sin emojis en archivos salvo los iconos de voz (`icono` en los JSON).
