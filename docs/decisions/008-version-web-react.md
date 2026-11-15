# ADR 008 — Versión web con React (rama `feat/web-app`)

- **Estado**: Aceptada
- **Fecha**: 2026-11-16
- **Contexto**: el usuario pidió una versión web del cambiador de voz que
  corra en el entorno de despliegue (sandbox que sirve Next.js en el puerto
  3000), manteniendo el repositorio como única fuente de verdad.

## Decisión

Crear la rama `feat/web-app` con la app web en `web/` (Next.js 16 + React +
Web Audio), espejo funcional de `voz_dnd/`, y dejar la regla de espejo
obligatoria escrita en `AGENTS.md` (raíz): todo cambio funcional se refleja
en ambas ramas; los archivos compartidos viven en rutas idénticas para que
el cherry-pick funcione.

### Por qué AudioWorklet (y no una librería de audio)

El DSP del escritorio (`efectos.py`) se portó **1:1** a
`web/public/worklets/cambiador-voz.js`: misma cadena
(Ganancia → Pitch → Formante → Distorsión → RingMod → EQ → Reverb), mismas
constantes de diseño y mismas fórmulas (incluido el desplazamiento de
formantes por liftering cepstral con STFT 512/128 y el pitch granular de dos
granos). Cero dependencias nuevas, latencia ~23 ms, y la equivalencia
matemática es auditable línea a línea — que es justo lo que exige la regla
de espejo. El worklet respeta el contrato RT del escritorio: jamás lanza,
ante error interno pasa la señal sin procesar.

### Por qué el catálogo se GENERA

`web/scripts/sincronizar_voces.py` produce `web/src/data/voces.json` desde
`voz_dnd/data/voces/*.json`. Copiar a mano invitaría a la divergencia; el
generador es determinista, tolerante (voz corrupta → aviso y se salta;
fuera de rango → acota con aviso, sin correcciones silenciosas) y garantiza
`Neutral`. La voz `IA Demo` entra con `tipo: "IA"` y su `dsp_post` como
parámetros: la web degrada a DSP, igual que el escritorio sin motor RVC.

### Por qué el TTS del servidor + respaldo del navegador

El escritorio usa `edge-tts` (requiere red). La web usa `/api/tts`
(`z-ai-web-dev-sdk`, solo backend) con las mismas garantías del fix 005:
fragmentación por oraciones ≤900 chars y reproducción **secuencial** por la
cadena de la voz activa. Si el servidor falla, `speechSynthesis` lee sin
efectos con aviso honesto (el navegador no permite enrutarlo por Web Audio).
La descarga WAV renderiza offline con el MISMO worklet.

### Persistencia

`localStorage` (claves `voz_dnd_web.*`) es el equivalente de `config.json`:
ajustes, voz activa y voces personalizadas ("guardar como nueva voz"), con
las 7 categorías de error de `src/lib/errores.ts` (datos corruptos → se
descartan con aviso, nunca bloquea).

## Consecuencias

- Dos implementaciones DSP que deben evolucionar juntas (la regla de espejo
  lo exige y lo documenta).
- Grabación en formato del navegador (WebM/Opus o MP4), no MP3; se valida
  tamaño 0 para no descargar archivos vacíos.
- El modo IA (RVC) queda fuera de la web: degrada a DSP por diseño, como el
  escritorio sin GPU.
- El entorno de despliegue (sandbox) sirve esta misma app en `/`; la copia
  de `web/` es el espejo versionado de ese árbol.
