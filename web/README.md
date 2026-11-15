# Versión web del Cambiador de Voz DM — `web/`

Rama `feat/web-app`. Espejo funcional de la app de escritorio (`voz_dnd/`,
rama `main`): **todo cambio funcional debe reflejarse en ambas ramas** (ver
`AGENTS.md` del raíz, sección "Sincronización entre ramas").

## Qué es

Misma app, otra plataforma: cambiador de voz en tiempo real para DM de D&D
ejecutándose en el navegador con React (Next.js 16 + Web Audio).

| Pieza | Escritorio (`voz_dnd/`) | Web (`web/`) |
|---|---|---|
| DSP | `app/domain/efectos.py` (numpy/scipy) | `public/worklets/cambiador-voz.js` (AudioWorklet, misma matemática) |
| Motor de audio | `app/engine/motor_audio.py` (sounddevice) | `src/lib/motor-audio.ts` (Web Audio: getUserMedia + AudioWorklet) |
| Catálogo de voces | `data/voces/*.json` (fuente) | `src/data/voces.json` (**generado**, ver abajo) |
| Rangos de sliders | `data/parametros.json` | `src/data/parametros.json` (copia verbatim) |
| Lectura TTS | `edge-tts` (Microsoft, en línea) | `/api/tts` (servidor, `z-ai-web-dev-sdk`) + respaldo `speechSynthesis` |
| Grabación | MP3 (pydub/ffmpeg) con cascada WAV | WebM/Opus (MP4 en Safari) vía `MediaRecorder`, post-DSP |
| Modo IA (RVC) | ONNX/PyTorch con degradación a DSP | No disponible: la voz "IA Demo" degrada a su `dsp_post` |
| Atajos | F1–F12 / Shift+F1–F6 desde `config.json` | Mismo mapa, desde el campo `atajo` del catálogo |
| Config | `data/config.json` | `localStorage` (claves `voz_dnd_web.*`) con tolerancia a corrupción |

## Ejecutar

```bash
cd web
bun install
bun run dev        # http://localhost:3000
bun run lint       # ESLint (misma config que el entorno de despliegue)
```

No requiere base de datos ni claves: el único servicio externo es el TTS del
servidor (`/api/tts`), con respaldo automático en la voz del navegador.

## Regenerar el catálogo tras cambiar voces

```bash
python3 web/scripts/sincronizar_voces.py
```

Lee `voz_dnd/data/voces/*.json` y `voz_dnd/data/parametros.json` y produce
`web/src/data/voces.json` + `web/src/data/parametros.json`. Tolerante: una voz
dañada se salta con aviso (nunca rompe), los valores fuera de rango se
acotan **con aviso**, `Neutral` está garantizada. Salida determinista.

## Estructura

```
web/
├── public/worklets/cambiador-voz.js  # DSP espejo de efectos.py (AudioWorklet)
├── scripts/sincronizar_voces.py      # generador del catálogo (regla de espejo)
├── prisma/schema.prisma              # plantilla del entorno (la app no usa BD)
├── src/
│   ├── app/                          # página única + /api/tts (route handler)
│   ├── components/voz/               # cabecera, pestañas (voces/editor/leer/ajustes), pie
│   ├── components/ui/                # shadcn/ui (New York)
│   ├── data/                         # catálogo GENERADO (no editar a mano)
│   ├── hooks/use-atajos.ts           # F1–F12 / Shift+F1–F6 desde el dato
│   ├── lib/                          # motor-audio, tts, voces, errores, wav, tipos
│   └── store/voz.ts                  # zustand (estado global)
```

## Tolerancia a fallos (7 categorías)

`src/lib/errores.ts` clasifica: permiso de micrófono, micrófono ausente,
contexto bloqueado (autoplay), AudioWorklet no soportado (modo degradado sin
DSP), fallo de TTS (respaldo navegador sin efectos), grabación vacía (no se
descarga un archivo sin datos) y datos locales corruptos (se descartan con
aviso, jamás bloquea el arranque). El worklet, ante error interno, pasa la
señal sin procesar y lo reporta: **nunca se corta el audio** (contrato RT del
escritorio).

## Diferencias honestas

- La fragmentación TTS es idéntica (≤900 chars por oraciones, reproducción
  secuencial — el fix 005 del escritorio), pero las voces del servidor son
  otras (el servicio no ofrece las voces neuronales de Microsoft).
- `speechSynthesis` no puede enrutarse por Web Audio: el respaldo lee sin
  efectos y la UI lo avisa.
- La grabación usa el códec del navegador; no hay cascada MP3→WAV porque
  `MediaRecorder` no produce archivos vacíos asíncronos (se valida tamaño 0).

## Verificación

- `bun run lint` limpio.
- DSP validado con pruebas de sanidad (bypass identidad, ganancia exacta,
  frecuencias de pitch, formante sin NaN, cadena completa acotada, cola de
  reverb).
- Flujo completo verificado en navegador: 20 voces, selección, atajos F1+,
  búsqueda sin acentos, voz personalizada persistente, lectura TTS de
  extremo a extremo, degradación limpia sin micrófono, footer pegado y
  layout responsive.
