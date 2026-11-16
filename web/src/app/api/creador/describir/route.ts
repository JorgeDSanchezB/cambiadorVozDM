// POST /api/creador/describir — «Forja por descripción» (inspirado en el
// Voice Design de VoiceStudio): una descripción en palabras → cadena DSP
// completa + nombre/icono/color, generada con LLM (z-ai-web-dev-sdk, SOLO
// servidor). El servidor VALIDA y RECORTA cada parámetro contra los rangos
// del catálogo (data/parametros.json) antes de devolver nada: la IA nunca
// decide los límites.

import { NextRequest, NextResponse } from 'next/server'

import CATALOGO from '@/data/parametros.json'
import type { ClaveParametro, DefParametro, ParametrosDSP } from '@/lib/tipos'

const MAX_DESCRIPCION = 600
const MAX_NOMBRE = 40
const MAX_RESUMEN = 200

const catalogo = CATALOGO as unknown as Record<ClaveParametro, DefParametro>
const claves = Object.keys(catalogo) as ClaveParametro[]

const EJEMPLOS = [
  'Un hechicero oscuro con eco de cripta y voz muy grave',
  'Un goblin mercader chillón y rápido, sin reverb',
  'Un dios imponente que retumba la sala con graves de metal',
]

function construirPrompt(): string {
  const lineas = claves.map((c) => {
    const d = catalogo[c]
    return `- "${c}": ${d.etiqueta}. Rango ${d.min} a ${d.max} (neutro ${d.neutro}).`
  })
  return [
    'Eres el maestro herrero de «La Forja del DJ», una app de voces para directores de juego de rol (D&D).',
    'Tu trabajo: convertir la descripción de un personaje en una voz de cadena DSP que suene a esa descripción.',
    '',
    'Parámetros disponibles (inclúyelos TODOS, con su valor neutro si no aplican):',
    ...lineas,
    '',
    'Guía de oficio:',
    '- Tamaño y cuerpo: pitch_semitonos y formant_shift bajan para criaturas grandes u oscuras; suben para pequeñas, agudas o infantiles.',
    '- Ambientes: reverb_room_size grande para criptas, salas, catacumbas o dioses; damping alto para espacios acolchados o húmedos.',
    '- Sonidos monstruosos o metálicos: distortion_drive, ring_mod_freq (robótica) y EQ de graves.',
    '- Narradores limpios: casi todo neutro, quizá una pizca de reverb.',
    '- gain_db cala la presencia: grave y poderoso sube un poco; susurros bajan.',
    '',
    'Responde EXCLUSIVAMENTE con un JSON válido (sin markdown, sin explicaciones) con esta forma exacta:',
    '{',
    '  "nombre": "nombre corto de la voz (máx 40 caracteres, español, evocador)",',
    '  "icono": "UN solo emoji que represente al personaje",',
    '  "color": "color en hex #rrggbb acorde al personaje (tonos tierra/ámbar para el tema de la forja)",',
    '  "resumen": "una frase (máx 200 caracteres) explicando por qué suena así",',
    '  "parametros_dsp": { ...los 10 parámetros con valores numéricos dentro de rango... }',
    '}',
  ].join('\n')
}

function acotarParametros(candidato: unknown): ParametrosDSP | null {
  if (typeof candidato !== 'object' || candidato === null) return null
  const crudo = candidato as Record<string, unknown>
  const limpio = {} as ParametrosDSP
  for (const clave of claves) {
    const def = catalogo[clave]
    const valor = Number(crudo[clave])
    if (!Number.isFinite(valor)) return null
    const paso = def.paso
    const acotado = Math.min(Math.max(valor, def.min), def.max)
    const redondeado = Math.round(acotado / paso) * paso
    limpio[clave] = Number(redondeado.toFixed(4))
  }
  return limpio
}

function limpiarCercado(texto: string): string {
  const cercado = texto.match(/```(?:json)?\s*([\s\S]*?)```/i)
  return (cercado ? cercado[1] : texto).trim()
}

export async function POST(req: NextRequest) {
  let cuerpo: { descripcion?: unknown }
  try {
    cuerpo = await req.json()
  } catch {
    return NextResponse.json({ ok: false, mensaje: 'Cuerpo de la petición inválido.' }, { status: 400 })
  }

  const descripcion = typeof cuerpo.descripcion === 'string' ? cuerpo.descripcion.trim() : ''
  if (!descripcion) {
    return NextResponse.json({ ok: false, mensaje: 'Describe primero la voz que quieres forjar.' }, { status: 400 })
  }
  if (descripcion.length > MAX_DESCRIPCION) {
    return NextResponse.json(
      { ok: false, mensaje: `La descripción es demasiado larga (máximo ${MAX_DESCRIPCION} caracteres).` },
      { status: 413 },
    )
  }

  try {
    const ZAI = (await import('z-ai-web-dev-sdk')).default
    const zai = await ZAI.create()
    const respuesta = await zai.chat.completions.create({
      messages: [
        { role: 'assistant', content: construirPrompt() },
        {
          role: 'user',
          content: `Descripción de la voz: «${descripcion}»\n\nDevuelve SOLO el JSON.`,
        },
      ],
      thinking: { type: 'disabled' },
    })

    const texto = respuesta.choices[0]?.message?.content ?? ''
    let bruto: Record<string, unknown>
    try {
      bruto = JSON.parse(limpiarCercado(texto)) as Record<string, unknown>
    } catch {
      return NextResponse.json(
        { ok: false, mensaje: 'La IA respondió en un formato inesperado. Inténtalo de nuevo.' },
        { status: 502 },
      )
    }

    const parametros = acotarParametros(bruto.parametros_dsp)
    if (!parametros) {
      return NextResponse.json(
        { ok: false, mensaje: 'La IA propuso parámetros fuera del forjo. Inténtalo de nuevo.' },
        { status: 502 },
      )
    }

    const nombre = typeof bruto.nombre === 'string' && bruto.nombre.trim()
      ? bruto.nombre.trim().slice(0, MAX_NOMBRE)
      : 'Voz forjada'
    const icono = typeof bruto.icono === 'string' && bruto.icono.trim() ? bruto.icono.trim() : '★'
    const color = typeof bruto.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(bruto.color)
      ? bruto.color
      : '#8a6d3b'
    const resumen = typeof bruto.resumen === 'string' && bruto.resumen.trim()
      ? bruto.resumen.trim().slice(0, MAX_RESUMEN)
      : ''

    return NextResponse.json({ ok: true, voz: { nombre, icono, color, resumen, parametros_dsp: parametros } })
  } catch {
    return NextResponse.json(
      { ok: false, mensaje: 'La forja IA no está disponible ahora mismo. Inténtalo en unos segundos.' },
      { status: 503 },
    )
  }
}
