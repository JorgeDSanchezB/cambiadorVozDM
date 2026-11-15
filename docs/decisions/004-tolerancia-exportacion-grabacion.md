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
2. Carpeta destino o patrón de nombre rotos → directo a la vía 3.
3. MP3 → WAV → WAV en el directorio temporal del sistema (un MP3 que
   falla a medias no deja residuo junto al WAV de rescate).
4. Si todo falla: los bloques se conservan en memoria y la ventana de
   grabación ofrece **«Reintentar exportación»** (el reintento es
   alcanzable desde la GUI; pulsar «Grabar» de nuevo descartaría el audio
   rescatado, y el diálogo lo avisa).

## Alternativas descartadas

- **Reintentar automáticamente en bucle**: puede colgar el hilo de la GUI
  ante un fallo persistente (disco lleno). Se prefiere un único intento
  por llamada con degradación y reintento manual explícito.
- **Encolar bloques a disco durante la grabación** (streaming a WAV): más
  robusto ante un crash del proceso, pero añade I/O en el camino del tap
  (riesgo RT) y complejidad de rotación. Coste > beneficio para sesiones
  de ~2 h con límite `MAX_SEGUNDOS` ya existente.

## Coste

- El WAV en temporal usa espacio en el disco del sistema si la carpeta
  destino falla; se avisa con la ruta exacta.
- El reintento en memoria solo vive mientras el proceso no se cierre ni
  se vuelva a grabar. Mientras exista audio pendiente, un cambio de
  ajustes de AUDIO se rechaza con error claro (`aplicar_config_audio`
  no recrea el grabador) y el cierre de la app ofrece exportarlo; un
  cambio de carpeta/calidad/ffmpeg en Ajustes SÍ se propaga al grabador
  vivo (`actualizar_config`) para que el remedio documentado —cambiar la
  carpeta y reintentar— funcione de verdad.
- Un cambio de carpeta durante una grabación ACTIVA cambia el destino
  del export a mitad de sesión (antes no surtía efecto hasta reiniciar):
  los bloques acumulados no se tocan y la sesión completa se exporta a
  la carpeta nueva (verificado por el árbitro); se considera aceptable.
