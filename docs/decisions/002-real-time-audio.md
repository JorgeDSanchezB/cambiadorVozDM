# 002 — Procesadores intercambiables y audio RT nunca bloqueado

- **Fecha**: creación de `voz_dnd/`
- **Estado**: aceptado

## Contexto

El audio en tiempo real (stream full-duplex de `sounddevice`) tiene un callback
que debe ejecutarse sin locks, sin excepciones y sin trabajo pesado, o se
producen dropouts y se rompe la sesión.

## Decisión

- El callback procesa a través de un **procesador intercambiable** con contrato
  común `procesar(bloque, sr) -> np.ndarray` (`ProcesadorDSP`, `ProcesadorIA`,
  `ProcesadorBypass`).
- `MotorAudio` cambia la **referencia** al procesador de forma atómica desde el
  hilo de la GUI (seguro bajo el GIL de CPython), sin locks en el hilo de audio.
- Los efectos trabajan sobre arrays **`(frames, 1)` float32**; hay que
  normalizar con `reshape(-1, 1)` antes/después (un array 1-D rompe los efectos).
- La GUI consulta estado por polling (33 ms / 30 FPS), nunca recibe llamadas
  desde el hilo de audio.

## Consecuencias

- El stream nunca se bloquea ni lanza desde el hilo RT.
- Cualquier procesador (DSP, IA, bypass) se integra reusando el mismo contrato.
- Regla operativa: nunca hagas I/O, locks ni llamadas GUI dentro del callback.
