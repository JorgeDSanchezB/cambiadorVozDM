// Cliente de FakeYou (SOLO backend) — sección "Voces de personajes".
//
// FakeYou expone un API pública anónima: catálogo en /tts/list e inferencias
// en /tts/inference + /task/{token}. El catálogo latino se cachea en memoria
// (TTL 6 h) y las inferencias pasan por una cola con enfriamiento porque el
// cupo anónimo por IP es muy estricto ("synthetic_too_many_requests").
// Opcionalmente se acepta el token de sesión de una cuenta de FakeYou para
// tener más cupo (se reenvía como cookie `session`).

import type { NextRequest } from 'next/server'

const API = 'https://api.fakeyou.com'
const UA =
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

export const MAX_TEXTO = 500
const TTL_CATALOGO_MS = 6 * 60 * 60 * 1000
const MIN_INTERVALO_ENVIO_MS = 12_000
const MAX_BYTES_AUDIO = 20 * 1024 * 1024

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface VozPersonaje {
  token: string
  titulo: string
  creador: string
  locale: string
  grupo: string
  destacada: boolean
  prioridad: number
}

interface ModeloFakeyou {
  model_token?: string
  title?: string
  creator_username?: string
  ietf_language_tag?: string
  ietf_primary_language_subtag?: string
}

export class ErrorFakeyou extends Error {
  codigo: 'limite' | 'http' | 'red' | 'formato'
  constructor(codigo: ErrorFakeyou['codigo'], mensaje: string) {
    super(mensaje)
    this.codigo = codigo
  }
}

// ---------------------------------------------------------------------------
// Catálogo latino
// ---------------------------------------------------------------------------

// Regiones latinas explícitas: es-419 (Latinoamérica) y es-MX (México).
// Esas dos suman 193 voces hoy; a eso se suman voces etiquetadas solo "es"
// cuyo título declara explícitamente que son latinas (narrador DBZ, El Chavo
// animado, Frieza, Cell, Patricio…), que FakeYou no regionalizó.
const RE_LATIN_GENERICO = /(latino|latin\b|es-?mx|m[eé]xico)/i

// Modelos de prueba / basura sin valor para un DM: se ocultan del catálogo.
const RE_JUNK =
  /^(test|testing)\b|test model|latino test|myvoiceprueba|gfjgbiuednfjklsdf|^zunn$|^bgus$|^c3jo$|^tatk$|^tomex$|^moni2?$|^daniiee|^zzunko$|^gaalf$|^z ?8082195$/i

// Destacadas: los personajes que un DM busca primero. El orden de la lista
// define la prioridad de aparición (Homero y el narrador de DBZ arriba).
const DESTACADAS: RegExp[] = [
  /dragonball z narrador/i,
  /homero/i,
  /el chavo/i,
  /quico/i,
  /bob esponja/i,
  /patricio/i,
  /don cangrejo/i,
  /plankton/i,
  /arenita/i,
  /frieza/i,
  /cell perfecto/i,
  /peter griffin/i,
  /randy marsh|stan marsh/i,
  /bender/i,
  /burro de shrek/i,
  /[áa]lex el le[oó]n|alex the lion/i,
  /optimus prime/i,
  /morgan freeman/i,
  /pennywise/i,
  /merlina addams/i,
  /mimir/i,
  /cortana/i,
  /ironman/i,
  /ranma/i,
  /inuyasha/i,
  /seiya/i,
  /bakugo/i,
  /light yagami|lawliet/i,
  /zelda/i,
  /narrador history channel/i,
  /luisito comunica/i,
  /holasoygerman/i,
  /mrbeast/i,
  /maradona/i,
  /messi/i,
  /canelo/i,
  /martinoli/i,
  /el sorprendente hombre ara[ñn]a/i,
  /toretto/i,
  /tony soprano/i,
  /drake bell/i,
  /doki/i,
  /marge/i,
  /bart/i,
]

// Agrupación por franquicia/temática (se evalúa en orden; la primera que
// casa gana). Sin coincidencia → "Otros".
const GRUPOS: Array<{ nombre: string; re: RegExp }> = [
  { nombre: 'Los Simpson', re: /simpson|homero|marge|bart|lisa|burns|skinner|flanders/i },
  { nombre: 'El Chavo', re: /chavo|quico|chilindrina|jirafales|bruja del 71|don ram[oó]n|chespirito|chapul[ií]n/i },
  { nombre: 'Dragon Ball', re: /dragon ?ball|goku|vegeta|freezer|frieza|cell|piccolo|sayayin|broly|\bbuu\b|bulma/i },
  { nombre: 'Bob Esponja', re: /bob esponja|patricio|plankton|don cangrejo|arenita|calamardo|bikini/i },
  { nombre: 'Futurama', re: /futurama|bender|fry|leela|farnsworth|zoidberg/i },
  { nombre: 'South Park', re: /south park|randy marsh|stan marsh|cartman|kyle|kenny/i },
  { nombre: 'Caricaturas', re: /my little pony|fluttershy|sunset shimmer|shrek|alex the lion|[áa]lex el le|madagascar|backyardigan|doki|grillo green|cricket green|shezow|pantera rosa|conroy cat|zowl|sa'marion|monster|gordo querido|guy hamdon/i },
  { nombre: 'Anime', re: /ranma|akane|inuyasha|seiya|pegaso|caballeros del zodi|hunter x hunter|chrollo|death note|light yagami|lawliet|bakugo|naruto|one piece|luffy|zoro|shingeki|eren|levi|alucard|hellsing|tobi tenma|astro ?boy/i },
  { nombre: 'Videojuegos', re: /overwatch|junkrat|valorant|sage|neon|league of legends|ashe|lux\b|halo|cortana|god of war|mimir|starcraft|raynor|tychus|zelda|botw|minecraft|gta|toretto|fast and furious|transformers|optimus prime|ironman|crash|sonic/i },
  { nombre: 'Cine y TV', re: /morgan freeman|pennywise|soprano|drake bell|zoey 101|oso ted|family guy|griffin|el sorprendente|hombre ara[ñn]a|spider ?man|juez|tres patines/i },
  { nombre: 'Deportes', re: /f[uú]tbol|relator|comentarista|cronista|maradona|messi|agüero|canelo|niembro|closs|latorre|paoli|sutcliffe|martinoli|palma|deport|espn|fox sports|tnt sports/i },
  { nombre: 'Narradores y locutores', re: /narrador|locutor|documental|audiolibro|noticiero|cronista/i },
  { nombre: 'Streamers y youtubers', re: /streamer|youtuber|luisito|holasoygerman|germán|mrbeast|mariana|guarnizo|quackity|coscu|spreen|robleis|mhoni|doomentio|lonrot|pepe el mago|zico|pipepino|mixerables|emmahavok|cosmopolis|hardstop|amigo f[eé]lix|amigo suelto/i },
  { nombre: 'Música', re: /cantante|fito p[aá]ez|pedro aznar|spinetta|eva ayll[oó]n|su[aá]rez v[eé]rtiz|galeano|les luthiers|facundo cabral|cri ?cri|kika edgar/i },
  { nombre: 'Política y reales', re: /presidente|fidel castro|peña nieto/i },
]

function clasificar(titulo: string): { grupo: string; destacada: boolean; prioridad: number } {
  let destacada = false
  let prioridad = DESTACADAS.length
  for (let i = 0; i < DESTACADAS.length; i++) {
    if (DESTACADAS[i].test(titulo)) {
      destacada = true
      prioridad = i
      break
    }
  }
  const grupo = GRUPOS.find((g) => g.re.test(titulo))?.nombre ?? 'Otros'
  return { grupo, destacada, prioridad }
}

interface CacheCatalogo {
  voces: VozPersonaje[]
  tokens: Set<string>
  generadoEn: string
  expira: number
}

let cacheCatalogo: CacheCatalogo | null = null

function cabeceras(sesion?: string): Record<string, string> {
  const h: Record<string, string> = {
    'User-Agent': UA,
    Accept: 'application/json',
  }
  if (sesion) h.Cookie = `session=${sesion}`
  return h
}

// Catálogo latino completo de FakeYou (cacheado 6 h en memoria del servidor).
export async function obtenerCatalogoLatin(forzar = false): Promise<CacheCatalogo> {
  if (!forzar && cacheCatalogo && cacheCatalogo.expira > Date.now()) return cacheCatalogo

  let resp: Response
  try {
    resp = await fetch(`${API}/tts/list`, {
      headers: cabeceras(),
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    })
  } catch {
    if (cacheCatalogo) return cacheCatalogo // degradación: catálogo viejo mejor que nada
    throw new ErrorFakeyou('red', 'No se pudo conectar con FakeYou para descargar el catálogo')
  }
  if (!resp.ok) {
    if (cacheCatalogo) return cacheCatalogo
    throw new ErrorFakeyou('http', `FakeYou respondió ${resp.status} al pedir el catálogo`)
  }

  const data = (await resp.json()) as { models?: ModeloFakeyou[] }
  const modelos = Array.isArray(data.models) ? data.models : []

  const voces: VozPersonaje[] = []
  for (const m of modelos) {
    const token = m.model_token
    const titulo = (m.title ?? '').trim()
    if (!token || !titulo) continue
    const subtag = m.ietf_primary_language_subtag ?? ''
    if (subtag !== 'es') continue
    const locale = m.ietf_language_tag ?? 'es'
    const esLatino =
      locale === 'es-419' ||
      locale === 'es-MX' ||
      (locale === 'es' && RE_LATIN_GENERICO.test(titulo))
    if (!esLatino) continue
    if (RE_JUNK.test(titulo)) continue
    const { grupo, destacada, prioridad } = clasificar(titulo)
    voces.push({
      token,
      titulo,
      creador: m.creator_username ?? 'desconocido',
      locale,
      grupo,
      destacada,
      prioridad,
    })
  }

  // Destacadas primero (por prioridad), luego alfabético por grupo.
  voces.sort((a, b) => {
    if (a.destacada !== b.destacada) return a.destacada ? -1 : 1
    if (a.destacada && b.destacada && a.prioridad !== b.prioridad) return a.prioridad - b.prioridad
    const ga = GRUPOS.findIndex((g) => g.nombre === a.grupo)
    const gb = GRUPOS.findIndex((g) => g.nombre === b.grupo)
    if (ga !== gb) return ga - gb
    return a.titulo.localeCompare(b.titulo, 'es')
  })

  cacheCatalogo = {
    voces,
    tokens: new Set(voces.map((v) => v.token)),
    generadoEn: new Date().toISOString(),
    expira: Date.now() + TTL_CATALOGO_MS,
  }
  return cacheCatalogo
}

// ¿El token pertenece al catálogo latino? (lista blanca: evita usar este
// servidor como proxy abierto de las 3000+ voces de FakeYou).
export async function esTokenLatino(token: string): Promise<boolean> {
  const catalogo = await obtenerCatalogoLatin()
  return catalogo.tokens.has(token)
}

// ---------------------------------------------------------------------------
// Cola de envío con enfriamiento (el cupo anónimo es muy justo)
// ---------------------------------------------------------------------------

let ultimoEnvioMs = 0
let cola: Promise<unknown> = Promise.resolve()

function dormir(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

// Serializa los envíos a FakeYou: como mucho uno cada MIN_INTERVALO_ENVIO_MS.
// Las esperas no abortan la petición del usuario, solo la retrasan.
async function conCola<T>(tarea: () => Promise<T>): Promise<T> {
  const ejecutar = async (): Promise<T> => {
    const espera = ultimoEnvioMs + MIN_INTERVALO_ENVIO_MS - Date.now()
    if (espera > 0) await dormir(espera)
    ultimoEnvioMs = Date.now()
    return tarea()
  }
  const resultado = cola.then(ejecutar, ejecutar)
  cola = resultado.then(
    () => undefined,
    () => undefined,
  )
  return resultado
}

// ---------------------------------------------------------------------------
// Inferencia y polling de tareas
// ---------------------------------------------------------------------------

export interface RespuestaInferencia {
  jobToken: string
}

export async function enviarInferencia(
  modelToken: string,
  texto: string,
  sesion?: string,
): Promise<RespuestaInferencia> {
  return conCola(async () => {
    let resp: Response
    try {
      resp = await fetch(`${API}/tts/inference`, {
        method: 'POST',
        headers: { ...cabeceras(sesion), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tts_model_token: modelToken,
          uuid_id: crypto.randomUUID(),
          inference_text: texto,
        }),
        signal: AbortSignal.timeout(30_000),
      })
    } catch {
      throw new ErrorFakeyou('red', 'No se pudo conectar con FakeYou para enviar la síntesis')
    }
    if (!resp.ok) throw new ErrorFakeyou('http', `FakeYou respondió ${resp.status} al crear la síntesis`)

    let data: { success?: boolean; inference_job_token?: unknown }
    try {
      data = (await resp.json()) as typeof data
    } catch {
      throw new ErrorFakeyou('formato', 'FakeYou devolvió una respuesta ilegible al crear la síntesis')
    }

    const token = data.inference_job_token
    if (typeof token !== 'string' || !token) {
      throw new ErrorFakeyou('formato', 'FakeYou no devolvió el identificador de la síntesis')
    }
    if (token.startsWith('synthetic_')) {
      if (token.includes('too_many_requests')) {
        throw new ErrorFakeyou(
          'limite',
          'FakeYou está saturado: el cupo anónimo por IP se agotó. Espera unos minutos o conecta tu cuenta de FakeYou.',
        )
      }
      throw new ErrorFakeyou('limite', `FakeYou rechazó la petición (${token})`)
    }
    return { jobToken: token }
  })
}

export interface EstadoJob {
  estado: 'pendiente' | 'listo' | 'error'
  audioUrl?: string
  mensaje?: string
}

export async function consultarJob(jobToken: string, sesion?: string): Promise<EstadoJob> {
  let resp: Response
  try {
    resp = await fetch(`${API}/task/${encodeURIComponent(jobToken)}`, {
      headers: cabeceras(sesion),
      cache: 'no-store',
      signal: AbortSignal.timeout(20_000),
    })
  } catch {
    throw new ErrorFakeyou('red', 'No se pudo consultar el estado de la síntesis')
  }
  if (!resp.ok) throw new ErrorFakeyou('http', `FakeYou respondió ${resp.status} al consultar la síntesis`)

  let data: {
    success?: boolean
    status?: { status?: string }
    content?: {
      maybe_public_audio_wav?: string
      maybe_public_audio_path?: string
      maybe_client_error_message?: string | null
    }
  }
  try {
    data = (await resp.json()) as typeof data
  } catch {
    throw new ErrorFakeyou('formato', 'FakeYou devolvió una respuesta ilegible del estado')
  }

  const estado = data.status?.status
  if (estado === 'complete') {
    const crudo = data.content?.maybe_public_audio_wav
    const ruta = data.content?.maybe_public_audio_path
    let audioUrl: string | null = null
    if (typeof crudo === 'string' && /^https?:\/\//.test(crudo)) audioUrl = crudo
    else if (typeof crudo === 'string' && crudo) audioUrl = `https://storage.googleapis.com/vocodes-public/${crudo}`
    else if (typeof ruta === 'string' && ruta) audioUrl = `https://storage.googleapis.com/vocodes-public/${ruta}`
    if (!audioUrl) return { estado: 'error', mensaje: 'La síntesis terminó sin audio' }
    return { estado: 'listo', audioUrl }
  }
  if (estado === 'failure' || estado === 'cancelled' || estado === 'dead') {
    return {
      estado: 'error',
      mensaje: data.content?.maybe_client_error_message || `La síntesis falló (${estado})`,
    }
  }
  return { estado: 'pendiente' }
}

// Descarga el WAV listo y lo devuelve como Buffer (máx. 20 MB).
export async function descargarAudio(url: string): Promise<Buffer> {
  let resp: Response
  try {
    resp = await fetch(url, { signal: AbortSignal.timeout(60_000) })
  } catch {
    throw new ErrorFakeyou('red', 'No se pudo descargar el audio generado')
  }
  if (!resp.ok) throw new ErrorFakeyou('http', `La descarga del audio falló (${resp.status})`)
  const buffer = Buffer.from(await resp.arrayBuffer())
  if (buffer.length === 0) throw new ErrorFakeyou('formato', 'El audio descargado está vacío')
  if (buffer.length > MAX_BYTES_AUDIO) throw new ErrorFakeyou('formato', 'El audio descargado supera el límite')
  return buffer
}

// ---------------------------------------------------------------------------
// Utilidades compartidas por las rutas
// ---------------------------------------------------------------------------

export function leerSesion(req: NextRequest, cuerpoSesion?: unknown): string | null {
  const delCuerpo = typeof cuerpoSesion === 'string' ? cuerpoSesion.trim() : ''
  if (delCuerpo) return delCuerpo
  const cookie = req.cookies.get('session')?.value
  return cookie ? cookie : null
}
