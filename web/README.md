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
| Lectura TTS | `edge-tts` (Microsoft, en línea) | `/api/tts` (servidor, `z-ai-web-dev-sdk`) + respaldo `speechSynthesis`; elenco de personajes FakeYou (`/api/personajes/*`, cola con caché y límites) |
| Grabación | MP3 (pydub/ffmpeg) con cascada WAV | WebM/Opus (MP4 en Safari) vía `MediaRecorder`, post-DSP |
| Modo IA (RVC) | ONNX/PyTorch con degradación a DSP | No disponible: la voz "IA Demo" degradaba a su `dsp_post` (voz eliminada del catálogo a petición del usuario) |
| Atajos | F1–F12 / Shift+F1–F6 desde `config.json` | **Asignación manual** en Ajustes › Atajos (captura de tecla por voz; la del catálogo es solo sugerencia inicial; overrides en `localStorage`, tecla de propiedad exclusiva, «Restaurar sugerencia inicial») |
| Config | `data/config.json` | `localStorage` (claves `voz_dnd_web.*`) con tolerancia a corrupción |
| Quitar voces | Editor › "Eliminar" (borra el JSON de `data/voces/`, permanente; Neutral protegida) | Ojo tachado en la tarjeta: **oculta** la voz base de la lista (id en `localStorage`, restaurable en Ajustes › Voces ocultas; Neutral protegida); las personalizadas se eliminan con deshacer |
| Favoritos / historial de personajes | — | Prisma + SQLite (`prisma/schema.prisma`: `FavoritoPersonaje`, `GeneracionPersonaje`), vía `/api/personajes/*` |

## Ejecutar

```bash
cd web
bun install
bun run dev        # http://localhost:3000
bun run lint       # ESLint (misma config que el entorno de despliegue)
```

No requiere claves externas en el cliente. El servidor usa `z-ai-web-dev-sdk`
(TTS) y Prisma + SQLite (`db/custom.db`, se crea con `bun run db:push`) para
favoritos e historial del elenco FakeYou.

## Pestañas

**Voces → Leer → Creador → Ajustes** (la pestaña DSP se llama «Creador» y
va después de Leer, petición del usuario; la antigua «Personajes» se fusionó
con Leer). Reglas de producto no negociables en `web/AGENTS.md`.

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
├── prisma/schema.prisma              # FavoritoPersonaje + GeneracionPersonaje (SQLite)
├── AGENTS.md                         # reglas de producto de la web (no regresionar)
├── src/
│   ├── app/                          # página única + /api/tts + /api/personajes/*
│   │   └── fonts/                    # Cinzel woff2 local (font-display)
│   ├── components/voz/               # cabecera, héroe, fondo, pestañas (voces/leer/creador/ajustes), tarjeta-atajos
│   ├── components/ui/                # shadcn/ui (New York)
│   ├── data/                         # catálogo GENERADO (no editar a mano)
│   ├── hooks/use-atajos.ts           # disparo global de atajos (silenciado en captura)
│   ├── lib/                          # motor-audio, tts, voces, fakeyou, db, errores, wav, tipos
│   └── store/                        # voz.ts + personajes.ts (zustand)
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
- Flujo completo verificado en navegador: 17 voces, selección, atajos con
  captura manual y conflicto, búsqueda sin acentos, voz personalizada
  persistente (asignable a atajo), lectura TTS de extremo a extremo, elenco
  FakeYou (favoritos, historial, cuenta en Ajustes), degradación limpia sin
  micrófono, footer pegado y layout responsive.
