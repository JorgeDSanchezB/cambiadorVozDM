// Catálogo de voces de la web — data-driven (cero hardcoding).
//
// El catálogo base se GENERA con web/scripts/sincronizar_voces.py desde
// voz_dnd/data/voces/*.json (regla de espejo entre ramas, ver AGENTS.md).
// Las voces personalizadas viven en localStorage (espejo funcional del
// "guardar como nueva voz" del escritorio) con tolerancia a datos corruptos.
// Las voces base que el usuario quita de su lista se guardan como ids
// ocultos (se restauran desde Ajustes): nunca se toca el catálogo generado.

import catalogoVocesJson from '@/data/voces.json'
import catalogoParametrosJson from '@/data/parametros.json'
import { errorVoz } from './errores'
import type { Ajustes, CatalogoVoces, ClaveParametro, DefParametro, ParametrosDSP, Voz } from './tipos'

export const CATALOGO_PARAMETROS = catalogoParametrosJson as unknown as Record<ClaveParametro, DefParametro>
export const CLAVES_PARAMETROS = Object.keys(CATALOGO_PARAMETROS) as ClaveParametro[]

const catalogoVoces = catalogoVocesJson as unknown as CatalogoVoces

const CLAVE_PERSONALIZADAS = 'voz_dnd_web.voces_personalizadas'
const CLAVE_AJUSTES = 'voz_dnd_web.ajustes'
const CLAVE_VOZ_ACTIVA = 'voz_dnd_web.voz_activa'
const CLAVE_OCULTAS = 'voz_dnd_web.voces_ocultas'

export const AJUSTES_POR_DEFECTO: Ajustes = {
  dispositivoEntrada: null,
  monitor: true,
  volumenMonitor: 1,
  atajos: true,
  srObjetivo: 48000,
}

function esNumero(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

// Clampea y valida los 10 parámetros contra el catálogo. Devuelve null si
// falta algún campo o hay tipos inválidos (dato corrupto → se descarta la voz).
export function validarParametros(bruto: unknown): ParametrosDSP | null {
  if (typeof bruto !== 'object' || bruto === null) return null
  const fuente = bruto as Record<string, unknown>
  const salida = {} as ParametrosDSP
  for (const clave of CLAVES_PARAMETROS) {
    const valor = fuente[clave]
    if (!esNumero(valor)) return null
    const def = CATALOGO_PARAMETROS[clave]
    salida[clave] = Math.min(Math.max(valor, def.min), def.max)
  }
  return salida
}

export function esNeutra(p: ParametrosDSP): boolean {
  return CLAVES_PARAMETROS.every((clave) => Math.abs(p[clave] - CATALOGO_PARAMETROS[clave].neutro) < 1e-3)
}

function vozDesdeDato(dato: unknown): Voz | null {
  if (typeof dato !== 'object' || dato === null) return null
  const d = dato as Record<string, unknown>
  const parametros = validarParametros(d.parametros_dsp)
  if (
    parametros === null ||
    typeof d.id !== 'string' || d.id.length === 0 ||
    typeof d.nombre !== 'string' || d.nombre.length === 0 ||
    (d.tipo !== 'DSP' && d.tipo !== 'IA')
  ) {
    return null
  }
  return {
    id: d.id,
    nombre: d.nombre,
    tipo: d.tipo,
    icono: typeof d.icono === 'string' ? d.icono : '·',
    color: typeof d.color === 'string' ? d.color : '#6b7280',
    atajo: typeof d.atajo === 'string' ? d.atajo : null,
    parametros_dsp: parametros,
  }
}

// Voces base: el catálogo generado. Ante voz inválida se salta con aviso;
// "Neutral" está garantizada (y si faltara, se fabrica desde los neutros del
// catálogo: nunca se bloquea el arranque, espejo del escritorio).
export function cargarVocesBase(): { voces: Voz[]; aviso: string | null } {
  const voces: Voz[] = []
  let aviso: string | null = null
  const vistas = new Set<string>()
  for (const dato of catalogoVoces.voces ?? []) {
    const voz = vozDesdeDato(dato)
    if (voz === null) {
      aviso = 'Alguna voz del catálogo venía dañada y fue descartada.'
      continue
    }
    if (vistas.has(voz.id)) {
      aviso = `Id de voz duplicado en el catálogo (${voz.nombre}); se conserva la primera.`
      continue
    }
    vistas.add(voz.id)
    voces.push(voz)
  }
  if (!voces.some((v) => v.nombre === 'Neutral')) {
    const neutros = {} as ParametrosDSP
    for (const clave of CLAVES_PARAMETROS) neutros[clave] = CATALOGO_PARAMETROS[clave].neutro
    voces.unshift({
      id: 'neutral-garantizada',
      nombre: 'Neutral',
      tipo: 'DSP',
      icono: '·',
      color: '#4a5d3a',
      atajo: null,
      parametros_dsp: neutros,
    })
    aviso = 'La voz Neutral no estaba en el catálogo; se generó desde los valores neutros.'
  }
  return { voces, aviso }
}

export function leerVocesPersonalizadas(): { voces: Voz[]; aviso: string | null } {
  if (typeof window === 'undefined') return { voces: [], aviso: null }
  try {
    const crudo = window.localStorage.getItem(CLAVE_PERSONALIZADAS)
    if (!crudo) return { voces: [], aviso: null }
    const lista = JSON.parse(crudo)
    if (!Array.isArray(lista)) throw new Error('formato inesperado')
    const voces: Voz[] = []
    for (const dato of lista) {
      const voz = vozDesdeDato(dato)
      if (voz) voces.push({ ...voz, personalizada: true })
    }
    const aviso = voces.length !== lista.length
      ? 'Alguna voz personalizada estaba dañada y fue descartada.'
      : null
    return { voces, aviso }
  } catch {
    return { voces: [], aviso: 'Las voces personalizadas guardadas eran ilegibles y se descartaron.' }
  }
}

export function escribirVocesPersonalizadas(voces: Voz[]): boolean {
  try {
    window.localStorage.setItem(CLAVE_PERSONALIZADAS, JSON.stringify(voces))
    return true
  } catch {
    return false
  }
}

export function leerAjustes(): { ajustes: Ajustes; aviso: string | null } {
  if (typeof window === 'undefined') return { ajustes: AJUSTES_POR_DEFECTO, aviso: null }
  try {
    const crudo = window.localStorage.getItem(CLAVE_AJUSTES)
    if (!crudo) return { ajustes: AJUSTES_POR_DEFECTO, aviso: null }
    const dato = JSON.parse(crudo) as Record<string, unknown>
    const ajustes: Ajustes = { ...AJUSTES_POR_DEFECTO }
    if (typeof dato.dispositivoEntrada === 'string') ajustes.dispositivoEntrada = dato.dispositivoEntrada
    if (dato.dispositivoEntrada === null) ajustes.dispositivoEntrada = null
    if (typeof dato.monitor === 'boolean') ajustes.monitor = dato.monitor
    if (esNumero(dato.volumenMonitor)) ajustes.volumenMonitor = Math.min(Math.max(dato.volumenMonitor, 0), 1)
    if (typeof dato.atajos === 'boolean') ajustes.atajos = dato.atajos
    if (esNumero(dato.srObjetivo) && (dato.srObjetivo === 44100 || dato.srObjetivo === 48000)) {
      ajustes.srObjetivo = dato.srObjetivo
    }
    return { ajustes, aviso: null }
  } catch {
    return { ajustes: AJUSTES_POR_DEFECTO, aviso: 'Los ajustes guardados eran ilegibles; se restauraron los base.' }
  }
}

export function escribirAjustes(ajustes: Ajustes): boolean {
  try {
    window.localStorage.setItem(CLAVE_AJUSTES, JSON.stringify(ajustes))
    return true
  } catch {
    return false
  }
}

export function leerVozActiva(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(CLAVE_VOZ_ACTIVA)
  } catch {
    return null
  }
}

export function escribirVozActiva(id: string): void {
  try {
    window.localStorage.setItem(CLAVE_VOZ_ACTIVA, id)
  } catch {
    /* sin persistencia: no bloquea */
  }
}

// Ids de voces base quitadas de la lista (restaurables). Tolerante a datos
// corruptos: lo que no sea un array de strings se ignora con aviso; si el
// dato es ilegible, se restauran todas (mejor una voz de más que una de menos).
export function leerIdsVocesOcultas(): { ids: string[]; aviso: string | null } {
  if (typeof window === 'undefined') return { ids: [], aviso: null }
  try {
    const crudo = window.localStorage.getItem(CLAVE_OCULTAS)
    if (!crudo) return { ids: [], aviso: null }
    const dato = JSON.parse(crudo)
    if (!Array.isArray(dato)) throw new Error('formato inesperado')
    const ids = dato.filter((x): x is string => typeof x === 'string')
    const aviso = ids.length !== dato.length
      ? 'La lista de voces quitadas venía dañada; se ignoraron las entradas inválidas.'
      : null
    return { ids, aviso }
  } catch {
    return { ids: [], aviso: 'La lista de voces quitadas era ilegible; se restauraron todas.' }
  }
}

export function escribirIdsVocesOcultas(ids: string[]): boolean {
  try {
    window.localStorage.setItem(CLAVE_OCULTAS, JSON.stringify(ids))
    return true
  } catch {
    return false
  }
}

const PALETA_PERSONAL = ['#8a6d3b', '#7a5c3e', '#5f7a4a', '#8a4a5f', '#6b5b8a', '#a0673b']

export function crearVozPersonalizada(nombre: string, parametros: ParametrosDSP): Voz {
  const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `personal-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const color = PALETA_PERSONAL[Math.floor(Math.random() * PALETA_PERSONAL.length)]
  return {
    id,
    nombre: nombre.trim() || 'Voz sin nombre',
    tipo: 'DSP',
    icono: '★',
    color,
    atajo: null,
    parametros_dsp: parametros,
    personalizada: true,
  }
}

// Descripción corta de los parámetros no neutros (chips de la UI).
export function resumenParametros(p: ParametrosDSP): { etiqueta: string; texto: string }[] {
  const chips: { etiqueta: string; texto: string }[] = []
  for (const clave of CLAVES_PARAMETROS) {
    const def = CATALOGO_PARAMETROS[clave]
    if (Math.abs(p[clave] - def.neutro) < 1e-3) continue
    const valor = def.paso < 1 ? p[clave].toFixed(2).replace(/\.?0+$/, '') : String(p[clave])
    chips.push({ etiqueta: def.etiqueta, texto: `${valor}${def.unidad ? ` ${def.unidad}` : ''}` })
  }
  return chips
}

export { errorVoz }
