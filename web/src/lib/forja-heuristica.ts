// Forja heurística — propuesta de cadena DSP por reglas de oficio cuando la
// IA no está disponible (p. ej. la app instalada en un PC sin acceso al
// servicio del sandbox, o el LLM caído). Mismo contrato de respuesta que la
// forja IA: { nombre, icono, color, resumen, parametros_dsp }.
//
// Diseño honesto: es un motor de PALABRAS CLAVE con sumas y recortes contra
// el catálogo (data/parametros.json) — nunca inventa fuera de rango. La IA
// sigue siendo el camino preferido; esto es la red de seguridad.

import CATALOGO from '@/data/parametros.json'
import type { ClaveParametro, DefParametro, ParametrosDSP } from '@/lib/tipos'

export interface VozForjada {
  nombre: string
  icono: string
  color: string
  resumen: string
  parametros_dsp: ParametrosDSP
}

const catalogo = CATALOGO as unknown as Record<ClaveParametro, DefParametro>
const claves = Object.keys(catalogo) as ClaveParametro[]

interface Regla {
  etiqueta: string
  palabras: string[]
  cambios: Partial<ParametrosDSP>
  icono?: string
  color?: string
}

// Orden = prioridad para icono/color (la primera regla que matchea manda).
const REGLAS: Regla[] = [
  {
    etiqueta: 'criatura colosal y grave',
    palabras: ['dragón', 'dragon', 'dios', 'titán', 'titan', 'golem', 'gigante', 'ogro', 'minotauro', 'colosal', 'monstruo enorme', 'demonio', 'demonio'],
    cambios: { pitch_semitonos: -6, formant_shift: 0.88, gain_db: 2, eq_low_db: 3, reverb_room_size: 0.18 },
    icono: '🐉',
    color: '#5a3d2b',
  },
  {
    etiqueta: 'oscuridad siniestra',
    palabras: ['oscuro', 'oscura', 'siniestro', 'siniestra', 'malvad', 'villano', 'necro', 'muerte', 'condenad', 'demoníac', 'demoniac'],
    cambios: { pitch_semitonos: -3, eq_low_db: 2, reverb_room_size: 0.22, reverb_damping: 0.4 },
    icono: '🧙',
    color: '#4a3b5c',
  },
  {
    etiqueta: 'eco de cripta',
    palabras: ['eco', 'cripta', 'cueva', 'catedral', 'tumba', 'catacumba', 'templo', 'retumba', 'retumbe', 'sala enorme', 'mazmorra', 'reverber'],
    cambios: { reverb_room_size: 0.55, reverb_damping: 0.35, eq_low_db: 1.5 },
    icono: '🕯️',
    color: '#3f4a3a',
  },
  {
    etiqueta: 'susurro espectral',
    palabras: ['susurr', 'fantasma', 'banshee', 'espectro', 'espíritu', 'espiritu', 'etéreo', 'etereo', 'escalofri', 'gélid', 'gelid', 'apagad'],
    cambios: { gain_db: -4, reverb_room_size: 0.38, reverb_damping: 0.6, pitch_semitonos: -1, eq_high_db: -2 },
    icono: '👻',
    color: '#4c5a66',
  },
  {
    etiqueta: 'criatura pequeña y chillona',
    palabras: ['agud', 'chillón', 'chillon', 'chilla', 'goblin', 'gnomo', 'hada', 'duende', 'niñ', 'infantil', 'ratón', 'raton', 'ardilla', 'veloz', 'rápid', 'rapid'],
    cambios: { pitch_semitonos: 6, formant_shift: 1.18, gain_db: 1 },
    icono: '👺',
    color: '#6b4a2a',
  },
  {
    etiqueta: 'mecanismo arcano',
    palabras: ['robot', 'robót', 'robotic', 'mecánic', 'mecanic', 'máquina', 'maquina', 'autómata', 'automata', 'constructo', 'analog', 'estática', 'estatica'],
    cambios: { ring_mod_freq: 45, eq_mid_db: 2.5, distortion_drive: 0.08, pitch_semitonos: -2 },
    icono: '🤖',
    color: '#4a5568',
  },
  {
    etiqueta: 'metal forjado',
    palabras: ['metál', 'metal', 'armadura', 'caballer', 'acero', 'hierro', 'forjad', 'yunque'],
    cambios: { distortion_drive: 0.16, eq_high_db: 2.5, eq_mid_db: 1 },
    icono: '⚔️',
    color: '#6e6a5e',
  },
  {
    etiqueta: 'furia salvaje',
    palabras: ['salvaje', 'bestia', 'gruñ', 'grun', 'feroz', 'rabia', 'grito', 'guerrer', 'bárbar', 'barbar', 'orco', 'berserk'],
    cambios: { distortion_drive: 0.24, gain_db: 2, pitch_semitonos: -2 },
    icono: '🪓',
    color: '#7a3b2e',
  },
  {
    etiqueta: 'veterano decrépito',
    palabras: ['anciano', 'anciana', 'viejit', 'viejit', 'viejo', 'vieja', 'decrép', 'decrep', 'temblor'],
    cambios: { pitch_semitonos: -1.5, formant_shift: 1.06, gain_db: -2, eq_high_db: -1.5 },
    icono: '🧓',
    color: '#6d6154',
  },
  {
    etiqueta: 'joven y bromista',
    palabras: ['joven', 'alegre', 'jovial', 'bromista', 'bardo', 'chica', 'mujer', 'pícar', 'picar', 'travies'],
    cambios: { pitch_semitonos: 2.5, formant_shift: 1.08 },
    icono: '🎭',
    color: '#8a6d3b',
  },
  {
    etiqueta: 'frialdad cruel',
    palabras: ['frío', 'frio', 'fría', 'fria', 'cruel', 'serpiente', 'veneno', 'ácid', 'acid', 'calculador'],
    cambios: { pitch_semitonos: -2, eq_mid_db: -2, reverb_room_size: 0.15 },
    icono: '🐍',
    color: '#3d5a4c',
  },
  {
    etiqueta: 'narrador limpio',
    palabras: ['narrador', 'narradora', 'locutor', 'radio', 'cuentacuentos', 'cuenta-cuentos', 'limpio', 'neutro', 'claro'],
    cambios: { eq_mid_db: 1.5, gain_db: 1 },
    icono: '📖',
    color: '#7d6b4f',
  },
  {
    etiqueta: 'brutalidad de orco',
    palabras: ['orco', 'orc', 'troll', 'ogro'],
    cambios: { pitch_semitonos: -4, formant_shift: 0.92, distortion_drive: 0.12, eq_low_db: 2 },
    icono: '👹',
    color: '#5f4a32',
  },
]

const ARTICULOS = new Set([
  'un', 'una', 'uno', 'el', 'la', 'los', 'las', 'de', 'del', 'con', 'que', 'y',
  'muy', 'bastante', 'algo', 'se', 'su', 'sus', 'en', 'al', 'lo',
])

function normalizar(texto: string): string {
  return texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function acotar(clave: ClaveParametro, valor: number): number {
  const def = catalogo[clave]
  const acotado = Math.min(Math.max(valor, def.min), def.max)
  const redondeado = Math.round(acotado / def.paso) * def.paso
  return Number(redondeado.toFixed(4))
}

function nombreDesdeDescripcion(descripcion: string): string {
  const palabras = normalizar(descripcion)
    .replace(/[^a-z0-9ñ\s]/g, ' ')
    .split(/\s+/)
    .filter((p) => p && !ARTICULOS.has(p))
    .slice(0, 3)
  if (!palabras.length) return 'Voz forjada'
  const nombre = palabras
    .map((p) => (p === 'dnd' ? 'D&D' : p.charAt(0).toUpperCase() + p.slice(1)))
    .join(' ')
  return nombre.slice(0, 40)
}

/** Forja una voz con reglas de oficio; null si la descripción no dice nada. */
export function forjarHeuristica(descripcion: string): VozForjada | null {
  const texto = normalizar(descripcion.trim())
  if (!texto) return null

  const base = {} as ParametrosDSP
  for (const clave of claves) base[clave] = catalogo[clave].neutro

  const activas: Regla[] = []
  for (const regla of REGLAS) {
    if (regla.palabras.some((p) => texto.includes(normalizar(p)))) {
      activas.push(regla)
    }
  }
  if (!activas.length) return null

  for (const regla of activas) {
    for (const [clave, delta] of Object.entries(regla.cambios)) {
      const c = clave as ClaveParametro
      base[c] = acotar(c, Number(base[c]) + Number(delta))
    }
  }

  const principal = activas[0]
  const etiquetas = activas.slice(0, 3).map((r) => r.etiqueta).join(' + ')
  return {
    nombre: nombreDesdeDescripcion(descripcion),
    icono: principal.icono ?? '🎭',
    color: principal.color ?? '#8a6d3b',
    resumen: `Forja heurística (sin IA): ${etiquetas}. Ajusta a mano en el editor si quieres afinar.`,
    parametros_dsp: base,
  }
}
