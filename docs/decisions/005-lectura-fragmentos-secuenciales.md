# 005 — Los fragmentos de síntesis TTS son secuenciales: concatenar

- **Fecha**: rama `chore/quality-improvements` (auditoría V6)
- **Estado**: aceptado (corrige un bug funcional)

## Contexto

`LectorTexto.sintetizar()` dividía textos de más de ~900 caracteres en
fragmentos (por oración) y los acumulaba con `total[:len(f)] += f`:
**suma desde la muestra 0**, es decir, todos los fragmentos sonaban
superpuestos simultáneamente. Reproducido con stub antes del arreglo
(3 fragmentos de 0,5 s devolvían 0,5 s de audio en lugar de 1,5 s).

## Decisión

`np.concatenate(fragmentos, axis=0)`: los fragmentos son trozos
secuenciales del texto original y se unen de principio a fin.

## Alternativas descartadas

- **Insertar un pequeño silencio entre fragmentos** (costura audible):
  edge-tts ya termina cada fragmento con prosodia de cierre; añadir
  silencio haría la lectura entrecortada. Si algún día hace falta, es un
  parámetro nuevo en `ConfigUI`, no un cambio de arquitectura.

## Coste

- Ninguno medible: la concatenación es O(n) igual que la suma.
