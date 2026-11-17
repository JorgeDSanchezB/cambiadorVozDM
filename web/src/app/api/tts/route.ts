// POST /api/tts — síntesis de voz con z-ai-web-dev-sdk (SOLO backend).
// El límite del servicio son 1024 chars; el cliente fragmenta a 900.

import { NextRequest, NextResponse } from 'next/server'

const VOZES_VALIDAS = new Set(['tongtong', 'chuichui', 'xiaochen', 'jam', 'kazi', 'douji', 'luodo'])
const MAX_CHARS = 1024

export async function POST(req: NextRequest) {
  let cuerpo: { texto?: unknown; voz?: unknown; velocidad?: unknown }
  try {
    cuerpo = await req.json()
  } catch {
    return NextResponse.json({ error: 'cuerpo_invalido' }, { status: 400 })
  }

  const texto = typeof cuerpo.texto === 'string' ? cuerpo.texto.trim() : ''
  if (!texto) {
    return NextResponse.json({ error: 'texto_vacio' }, { status: 400 })
  }
  if (texto.length > MAX_CHARS) {
    return NextResponse.json({ error: 'texto_largo', limite: MAX_CHARS }, { status: 413 })
  }
  const voz = typeof cuerpo.voz === 'string' && VOZES_VALIDAS.has(cuerpo.voz) ? cuerpo.voz : 'tongtong'
  const velocidadCrudo = Number(cuerpo.velocidad)
  const velocidad = Number.isFinite(velocidadCrudo)
    ? Math.min(2, Math.max(0.5, velocidadCrudo))
    : 1

  try {
    const ZAI = (await import('z-ai-web-dev-sdk')).default
    const zai = await ZAI.create()
    const resp = await zai.audio.tts.create({
      input: texto,
      voice: voz,
      speed: velocidad,
      response_format: 'wav',
      stream: false,
    })
    const arrayBuffer = await resp.arrayBuffer()
    const buffer = Buffer.from(new Uint8Array(arrayBuffer))
    if (!buffer || buffer.length === 0) {
      return NextResponse.json({ error: 'audio_vacio' }, { status: 502 })
    }
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        'Content-Type': 'audio/wav',
        'Content-Length': String(buffer.length),
        'Cache-Control': 'no-store',
      },
    })
  } catch (e) {
    return NextResponse.json(
      { error: 'tts_fallo', detalle: e instanceof Error ? e.message : 'desconocido' },
      { status: 500 },
    )
  }
}
