// Lectura de texto con la voz seleccionada — espejo de lector_texto.py.
//
// Flujo: texto → fragmentos (≤900 chars, por oraciones) → síntesis del
// servidor (/api/tts con z-ai-web-dev-sdk, backend) → decodificación →
// reproducción SECUENCIAL a través de la cadena de la voz activa.
// (Espejo del bug corregido en el escritorio: los fragmentos se reproducen
// uno detrás de otro, jamás superpuestos.)
// Respaldo: si el servidor falla, la voz del navegador (speechSynthesis)
// lee sin efectos — degradación honesta, nunca bloquea.

import { clasificarError } from './errores'
import { motor } from './motor-audio'
import { audioBufferAWav, descargarBlob, marcaDeTiempo } from './wav'
import type { ParametrosDSP } from './tipos'

export const VOCES_SERVIDOR = [
  { id: 'tongtong', nombre: 'Tongtong · cálida' },
  { id: 'chuichui', nombre: 'Chuichui · vivaz' },
  { id: 'xiaochen', nombre: 'Xiaochen · serena' },
  { id: 'jam', nombre: 'Jam · caballeresca' },
  { id: 'kazi', nombre: 'Kazi · clara' },
  { id: 'douji', nombre: 'Douji · natural' },
  { id: 'luodo', nombre: 'Luodo · expresiva' },
] as const

export type IdVozServidor = (typeof VOCES_SERVIDOR)[number]['id']
export const VOZ_SERVIDOR_POR_DEFECTO: IdVozServidor = 'tongtong'

export const FRAGMENTO_MAX_CHARS = 900
export const FRASE_DEMO = '¡Saludos, aventureros! Esta es la voz que has elegido para tu partida.'

export type FaseLectura = 'sintetizando' | 'reproduciendo' | 'descargando' | 'fin'

export interface ProgresoLectura {
  fase: FaseLectura
  fragmento: number
  total: number
}

// Espejo de LectorTexto._fragmentar: corta por oraciones (o saltos de línea)
// y nunca parte una palabra; un texto sin cortes se divide en el último
// espacio antes del límite.
export function fragmentarTexto(texto: string, maxChars = FRAGMENTO_MAX_CHARS): string[] {
  const limpio = (texto ?? '').trim()
  if (!limpio) return []

  const oraciones: string[] = []
  for (const linea of limpio.split(/\n+/)) {
    const trozo = linea.trim()
    if (!trozo) continue
    const partes = trozo.match(/[^.!?]+[.!?]*\s*/g)
    if (partes) {
      for (const parte of partes) {
        const p = parte.trim()
        if (p) oraciones.push(p)
      }
    } else {
      oraciones.push(trozo)
    }
  }

  const fragmentos: string[] = []
  let buf = ''
  for (const oracion of oraciones) {
    if (oracion.length > maxChars) {
      if (buf) { fragmentos.push(buf); buf = '' }
      let resto = oracion
      while (resto.length > maxChars) {
        let corte = resto.lastIndexOf(' ', maxChars)
        if (corte <= 0) corte = maxChars
        fragmentos.push(resto.slice(0, corte).trim())
        resto = resto.slice(corte).trim()
      }
      if (resto) buf = resto
      continue
    }
    if (buf.length + oracion.length + 1 <= maxChars) {
      buf = buf ? `${buf} ${oracion}` : oracion
    } else {
      if (buf) fragmentos.push(buf)
      buf = oracion
    }
  }
  if (buf) fragmentos.push(buf)
  return fragmentos.length > 0 ? fragmentos : [limpio]
}

// Síntesis de UN fragmento (el API limita a 1024 chars; usamos 900).
export async function sintetizarFragmento(
  texto: string,
  voz: IdVozServidor,
  velocidad: number,
  senal?: AbortSignal,
): Promise<ArrayBuffer> {
  let resp: Response
  try {
    resp = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, voz, velocidad }),
      signal: senal,
    })
  } catch (e) {
    throw clasificarError(e, 'tts')
  }
  if (!resp.ok) {
    throw clasificarError(new Error(`HTTP ${resp.status}`), 'tts')
  }
  return resp.arrayBuffer()
}

export interface OpcionesLectura {
  texto: string
  voz: IdVozServidor
  velocidad: number
  conEfectos: boolean
  onProgreso?: (p: ProgresoLectura) => void
  senal?: AbortSignal
}

// Lee con el servidor y reproduce cada fragmento por la cadena de la voz
// activa, en orden y sin solaparse.
export async function leerConServidor(opciones: OpcionesLectura): Promise<void> {
  const fragmentos = fragmentarTexto(opciones.texto)
  if (fragmentos.length === 0) return
  await motor.ensureContexto()

  for (let i = 0; i < fragmentos.length; i++) {
    if (opciones.senal?.aborted) return
    opciones.onProgreso?.({ fase: 'sintetizando', fragmento: i + 1, total: fragmentos.length })
    const datos = await sintetizarFragmento(fragmentos[i], opciones.voz, opciones.velocidad, opciones.senal)
    if (opciones.senal?.aborted) return
    const buffer = await motor.decodificar(datos)
    opciones.onProgreso?.({ fase: 'reproduciendo', fragmento: i + 1, total: fragmentos.length })
    await motor.reproducirBuffer(buffer, opciones.conEfectos)
  }
  opciones.onProgreso?.({ fase: 'fin', fragmento: fragmentos.length, total: fragmentos.length })
}

// Respaldo sin red: la voz del navegador (sin efectos DSP — el navegador no
// permite enrutar speechSynthesis por Web Audio; degradación honesta).
export function leerConNavegador(texto: string, senal?: AbortSignal): Promise<void> {
  return new Promise((resolver, rechazar) => {
    if (typeof speechSynthesis === 'undefined') {
      rechazar(clasificarError(new Error('speechSynthesis no disponible'), 'tts'))
      return
    }
    const utterance = new SpeechSynthesisUtterance(texto)
    const voces = speechSynthesis.getVoices()
    const es = voces.find((v) => v.lang.toLowerCase().startsWith('es'))
    if (es) utterance.voice = es
    utterance.lang = es?.lang ?? 'es-ES'
    const alAbortar = () => {
      speechSynthesis.cancel()
      resolver()
    }
    senal?.addEventListener('abort', alAbortar, { once: true })
    utterance.onend = () => {
      senal?.removeEventListener('abort', alAbortar)
      resolver()
    }
    utterance.onerror = (ev) => {
      senal?.removeEventListener('abort', alAbortar)
      rechazar(clasificarError(new Error(ev.error), 'tts'))
    }
    speechSynthesis.cancel()
    speechSynthesis.speak(utterance)
  })
}

export function detenerLecturaNavegador(): void {
  if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel()
}

// Descarga el WAV de la lectura con la voz aplicada (espejo del "guardar
// WAV" del escritorio): render offline con la MISMA cadena del worklet.
export async function descargarWavLectura(opciones: OpcionesLectura & {
  parametros: ParametrosDSP
}): Promise<void> {
  const fragmentos = fragmentarTexto(opciones.texto)
  if (fragmentos.length === 0) return
  const ctx = await motor.ensureContexto()

  const buffers: AudioBuffer[] = []
  for (let i = 0; i < fragmentos.length; i++) {
    if (opciones.senal?.aborted) return
    opciones.onProgreso?.({ fase: 'sintetizando', fragmento: i + 1, total: fragmentos.length })
    const datos = await sintetizarFragmento(fragmentos[i], opciones.voz, opciones.velocidad, opciones.senal)
    buffers.push(await ctx.decodeAudioData(datos))
  }

  opciones.onProgreso?.({ fase: 'descargando', fragmento: fragmentos.length, total: fragmentos.length })
  // Concatenación secuencial (espejo del fix 005: nunca superponer).
  const sr = buffers[0].sampleRate
  const total = buffers.reduce((n, b) => n + b.length, 0)
  const plano = new Float32Array(total)
  let pos = 0
  for (const b of buffers) {
    plano.set(b.getChannelData(0), pos)
    pos += b.length
  }
  const combinado = ctx.createBuffer(1, total, sr)
  combinado.copyToChannel(plano, 0)

  const renderizado = opciones.conEfectos
    ? await motor.renderizarOffline(combinado, opciones.parametros)
    : combinado
  const blob = audioBufferAWav(renderizado)
  descargarBlob(blob, `lectura_${marcaDeTiempo()}.wav`)
  opciones.onProgreso?.({ fase: 'fin', fragmento: fragmentos.length, total: fragmentos.length })
}

// "Probar voz" de las tarjetas: frase corta por la cadena con los parámetros
// de ESA voz, sin cambiar la voz activa.
export async function probarVoz(params: ParametrosDSP, senal?: AbortSignal): Promise<void> {
  await motor.ensureContexto()
  motor.fijarParametrosLectura(params)
  try {
    const datos = await sintetizarFragmento(FRASE_DEMO, VOZ_SERVIDOR_POR_DEFECTO, 1, senal)
    const buffer = await motor.decodificar(datos)
    await motor.reproducirBuffer(buffer, true)
  } finally {
    // restaurar los parámetros de la voz activa en la cadena de lectura
    motor.restaurarParametrosLectura()
  }
}
