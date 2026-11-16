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

// Voz base del servidor. Con el SDK solo hay 7 voces y se evaluaron con ASR
// leyendo español («Bienvenidos, aventureros, a la mazmorra del dragón»):
//   - tongtong (212 Hz, mujer): transcripción EXACTA → es la voz base.
//   - luodo (270 Hz): «Buying Vinus Adventures» → fonética inglesa, descartada.
//   - xiaochen (126 Hz, el único hombre): «Andros Andros a la Mysmora» → ininteligible.
//   - chuichui: «Bienavidos» · jam/kazi/douji (247/258/192 Hz, todas mujer):
//     pronunciación irregular. Descartadas.
// El narrador MASCULINO se forja con la cadena DSP sobre esta base (ver
// PRESET_NARRADOR_HOMBRE): la fonética española sobrevive al cambio de tono
// (verificado con ASR).
export const VOCES_SERVIDOR = [
  { id: 'tongtong', nombre: 'Narradora · mujer' },
] as const

export type IdVozServidor = (typeof VOCES_SERVIDOR)[number]['id']
export const VOZ_SERVIDOR_POR_DEFECTO: IdVozServidor = 'tongtong'

// Narrador masculino integrado: la base femenina pasada por la cadena DSP
// (tono −5 st, garganta 1.25× más grande, pecho en graves). Verificado: la
// pronunciación española se conserva. Vive aquí para que la lectura y la
// descarga WAV usen EXACTAMENTE la misma cadena.
export const PRESET_NARRADOR_HOMBRE: ParametrosDSP = {
  pitch_semitonos: -5,
  formant_shift: 1.25,
  reverb_room_size: 0,
  reverb_damping: 0.5,
  distortion_drive: 0,
  gain_db: 0,
  ring_mod_freq: 0,
  eq_low_db: 2.5,
  eq_mid_db: -1,
  eq_high_db: -1.5,
}

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
  velocidad: number
  /**
   * Cadena DSP del personaje que narra. `undefined` = voz base sin efectos
   * (narradora femenina). Si se da, la cadena de lectura toma estos
   * parámetros durante la lectura y vuelve a los de la voz activa al final.
   */
  parametros?: ParametrosDSP
  onProgreso?: (p: ProgresoLectura) => void
  senal?: AbortSignal
}

// Lee con el servidor y reproduce cada fragmento en orden y sin solaparse.
// Con `parametros`, cada fragmento pasa por la cadena del personaje elegido
// (misma matemática del worklet que «Probar voz»); sin ellos, suena la voz
// neural tal cual. Al terminar, la cadena vuelve a los parámetros de la voz
// activa para no contaminar otras previsualizaciones.
export async function leerConServidor(opciones: OpcionesLectura): Promise<void> {
  const fragmentos = fragmentarTexto(opciones.texto)
  if (fragmentos.length === 0) return
  await motor.ensureContexto()
  if (opciones.parametros) motor.fijarParametrosLectura(opciones.parametros)

  try {
    for (let i = 0; i < fragmentos.length; i++) {
      if (opciones.senal?.aborted) return
      opciones.onProgreso?.({ fase: 'sintetizando', fragmento: i + 1, total: fragmentos.length })
      const datos = await sintetizarFragmento(fragmentos[i], VOZ_SERVIDOR_POR_DEFECTO, opciones.velocidad, opciones.senal)
      if (opciones.senal?.aborted) return
      const buffer = await motor.decodificar(datos)
      opciones.onProgreso?.({ fase: 'reproduciendo', fragmento: i + 1, total: fragmentos.length })
      await motor.reproducirBuffer(buffer, Boolean(opciones.parametros))
    }
    opciones.onProgreso?.({ fase: 'fin', fragmento: fragmentos.length, total: fragmentos.length })
  } finally {
    if (opciones.parametros) motor.restaurarParametrosLectura()
  }
}

// Respaldo sin red: la voz del navegador (sin efectos DSP — el navegador no
// permite enrutar speechSynthesis por Web Audio; degradación honesta).
// getVoices() llega VACÍO la primera vez en Chrome (las voces cargan async):
// sin esta espera el utterance sale con la voz por defecto del sistema y el
// español se lee con fonética inglesa (bug reportado por el usuario).
function esperarVoces(timeoutMs = 2000): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolver) => {
    if (typeof speechSynthesis === 'undefined') return resolver([])
    const primeras = speechSynthesis.getVoices()
    if (primeras.length > 0) return resolver(primeras)
    const temporizador = setTimeout(() => resolver(speechSynthesis.getVoices()), timeoutMs)
    speechSynthesis.addEventListener(
      'voiceschanged',
      () => {
        clearTimeout(temporizador)
        resolver(speechSynthesis.getVoices())
      },
      { once: true },
    )
  })
}

export async function leerConNavegador(texto: string, senal?: AbortSignal): Promise<void> {
  return new Promise(async (resolver, rechazar) => {
    if (typeof speechSynthesis === 'undefined') {
      rechazar(clasificarError(new Error('speechSynthesis no disponible'), 'tts'))
      return
    }
    const voces = await esperarVoces()
    const utterance = new SpeechSynthesisUtterance(texto)
    // Español primero: es-ES/es-MX/es-419 antes que cualquier otro «es».
    const es =
      voces.find((v) => /^es-(ES|MX|419|AR|CL|CO)$/i.test(v.lang)) ??
      voces.find((v) => v.lang.toLowerCase().startsWith('es'))
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

// Descarga el WAV de la lectura (espejo del "guardar WAV" del escritorio):
// render offline con la cadena del personaje si se pidió, o el audio
// neural tal cual si no.
export async function descargarWavLectura(opciones: OpcionesLectura): Promise<void> {
  const fragmentos = fragmentarTexto(opciones.texto)
  if (fragmentos.length === 0) return
  const ctx = await motor.ensureContexto()

  const buffers: AudioBuffer[] = []
  for (let i = 0; i < fragmentos.length; i++) {
    if (opciones.senal?.aborted) return
    opciones.onProgreso?.({ fase: 'sintetizando', fragmento: i + 1, total: fragmentos.length })
    const datos = await sintetizarFragmento(fragmentos[i], VOZ_SERVIDOR_POR_DEFECTO, opciones.velocidad, opciones.senal)
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

  const renderizado = opciones.parametros
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
