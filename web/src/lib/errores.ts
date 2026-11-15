// Tolerancia a fallos — 7 categorías diferenciadas (espejo de la cultura de
// errores honestos del escritorio: cada fallo con su remedio, sin máscaras).

export type CategoriaError =
  | 'mic_permiso'
  | 'mic_ausente'
  | 'contexto_bloqueado'
  | 'worklet_no_soportado'
  | 'tts_fallo'
  | 'grabacion_vacia'
  | 'datos_corruptos'
  | 'desconocido'

export interface DetalleError {
  categoria: CategoriaError
  titulo: string
  detalle: string
  remedio: string
}

const MENSAJES: Record<CategoriaError, { titulo: string; remedio: string }> = {
  mic_permiso: {
    titulo: 'Permiso de micrófono denegado',
    remedio: 'Permite el micrófono en el candado de la barra de direcciones y vuelve a iniciar.',
  },
  mic_ausente: {
    titulo: 'No hay micrófono disponible',
    remedio: 'Conecta un micrófono (o revisa el dispositivo elegido en Ajustes) e inténtalo de nuevo.',
  },
  contexto_bloqueado: {
    titulo: 'El audio está bloqueado por el navegador',
    remedio: 'Pulsa cualquier botón de la app para reactivar el audio (política de reproducción automática).',
  },
  worklet_no_soportado: {
    titulo: 'Este navegador no soporta AudioWorklet',
    remedio: 'Usa un navegador moderno (Chrome, Edge, Firefox o Safari recientes). La app seguirá sin efectos DSP.',
  },
  tts_fallo: {
    titulo: 'La síntesis de voz del servidor falló',
    remedio: 'Se usará la voz del navegador como respaldo (sin efectos DSP). Revisa tu conexión.',
  },
  grabacion_vacia: {
    titulo: 'La grabación quedó vacía',
    remedio: 'No se descargó ningún archivo: graba de nuevo con el micrófono activo y espera al menos un segundo.',
  },
  datos_corruptos: {
    titulo: 'Datos locales dañados',
    remedio: 'Se descartaron los datos inválidos y se mantuvo la configuración base.',
  },
  desconocido: {
    titulo: 'Error inesperado',
    remedio: 'Reintenta la operación; si persiste, recarga la página.',
  },
}

export class ErrorVozApp extends Error {
  readonly categoria: CategoriaError
  readonly titulo: string
  readonly detalle: string
  readonly remedio: string

  constructor(categoria: CategoriaError, detalle = '') {
    const base = MENSAJES[categoria]
    super(`${base.titulo}${detalle ? `: ${detalle}` : ''}`)
    this.categoria = categoria
    this.titulo = base.titulo
    this.detalle = detalle
    this.remedio = base.remedio
  }
}

export function errorVoz(categoria: CategoriaError, detalle = ''): ErrorVozApp {
  return new ErrorVozApp(categoria, detalle)
}

// Clasifica cualquier excepción en una de las categorías. `contexto` ayuda a
// desambiguar (p. ej. NotSupportedError significa cosas distintas según dónde).
export function clasificarError(
  e: unknown,
  contexto: 'microfono' | 'audio' | 'tts' | 'grabacion' | 'datos' = 'desconocido',
): ErrorVozApp {
  if (e instanceof ErrorVozApp) return e

  const nombre = e instanceof DOMException ? e.name : ''
  const mensaje = e instanceof Error ? e.message : String(e ?? '')

  if (nombre === 'NotAllowedError' || nombre === 'SecurityError') {
    return new ErrorVozApp(contexto === 'tts' ? 'tts_fallo' : 'mic_permiso', mensaje)
  }
  if (nombre === 'NotFoundError' || nombre === 'OverconstrainedError') {
    return new ErrorVozApp('mic_ausente', mensaje)
  }
  if (nombre === 'NotSupportedError') {
    return new ErrorVozApp(
      contexto === 'microfono' ? 'mic_ausente' : 'worklet_no_soportado',
      mensaje,
    )
  }
  if (contexto === 'tts' || /fetch|network|red/i.test(mensaje)) {
    return new ErrorVozApp('tts_fallo', mensaje)
  }
  if (contexto === 'datos' || /JSON|parse|localStorage/i.test(mensaje)) {
    return new ErrorVozApp('datos_corruptos', mensaje)
  }
  return new ErrorVozApp('desconocido', mensaje)
}
