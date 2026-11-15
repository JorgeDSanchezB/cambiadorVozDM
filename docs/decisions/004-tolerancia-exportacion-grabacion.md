# 004 — La exportación de una grabación jamás pierde la sesión

- **Fecha**: rama `chore/quality-improvements` (auditoría V6)
- **Estado**: aceptado (corrige un bug de pérdida de datos)

## Contexto

`GestorGrabacion._hay_ffmpeg()` asignaba `motor.ffmpeg_ruta` a
`AudioSegment.converter` **sin validar que existiera**. Si la ruta
configurada era inválida pero había ffmpeg en el PATH, la comprobación
respondía `True` (por `shutil.which`) mientras pydub usaba la ruta mala:
la exportación MP3 moría con `FileNotFoundError`. Como además
`_exportar()` hacía `self._bloques.clear()` **antes** de exportar, la
grabación completa se perdía. Reproducido con test (escenario A de la
auditoría) antes del arreglo.

## Decisión

Degradación en cascada con una sola regla dura: **el audio capturado solo
se descarta cuando una exportación tiene éxito**.

1. `_hay_ffmpeg()` valida la ruta configurada; si no existe la ignora con
   aviso y cae al ffmpeg del PATH (y sanea `AudioSegment.converter`).
2. MP3 → WAV → WAV en el directorio temporal del sistema.
3. Si todo falla: los bloques se conservan en memoria y el mensaje indica
   cómo reintentar (`detener_y_exportar` es idempotente para el reintento).

## Alternativas descartadas

- **Reintentar automáticamente en bucle**: puede colgar el hilo de la GUI
  ante un fallo persistente (disco lleno). Se prefiere un único intento
  por llamada con degradación.
- **Encolar bloques a disco durante la grabación** (streaming a WAV): más
  robusto ante un crash del proceso, pero añade I/O en el camino del tap
  (riesgo RT) y complejidad de rotación. Coste > beneficio para sesiones
  de ~2 h con límite `MAX_SEGUNDOS` ya existente.

## Coste

- El WAV en temporal usa espacio en el disco del sistema si la carpeta
  destino falla; se avisa con la ruta exacta.
- El reintento tras "todo falló" depende de que la GUI vuelva a llamar a
  `detener_y_exportar` (hoy: volver a grabar y detener). Limitación
  documentada, no se añade botón de reintento (anti-sobreingeniería).
