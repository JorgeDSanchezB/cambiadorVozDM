// POST /api/notas/transcribir — dictado de «Notas de sesión» (idea del
// Dictation Widget de VoiceStudio): audio grabado en el navegador
// (MediaRecorder, webm/opus) → transcripción con ASR
// (z-ai-web-dev-sdk, SOLO servidor). Devuelve el texto tal cual: la UI
// avisa de que la transcripción automática puede contener errores.

import { NextRequest, NextResponse } from 'next/server'

// ~20 MB de audio en base64 (base64 infla x1.37: ~14 MB de audio real,
// minutos de nota). El dictado es para notas, no para entrevistas.
const MAX_BASE64 = 20_000_000

export async function POST(req: NextRequest) {
  let cuerpo: { file_base64?: unknown }
  try {
    cuerpo = await req.json()
  } catch {
    return NextResponse.json({ ok: false, mensaje: 'Cuerpo de la petición inválido.' }, { status: 400 })
  }

  const base64 = typeof cuerpo.file_base64 === 'string' ? cuerpo.file_base64 : ''
  if (!base64) {
    return NextResponse.json({ ok: false, mensaje: 'No llegó ningún audio.' }, { status: 400 })
  }
  if (base64.length > MAX_BASE64) {
    return NextResponse.json(
      { ok: false, mensaje: 'La nota es demasiado larga. Divídela en notas más cortas.' },
      { status: 413 },
    )
  }

  try {
    const ZAI = (await import('z-ai-web-dev-sdk')).default
    const zai = await ZAI.create()
    const respuesta = await zai.audio.asr.create({ file_base64: base64 })
    const texto = (respuesta.text ?? '').trim()
    if (!texto) {
      return NextResponse.json(
        { ok: false, mensaje: 'No se reconoció voz en la grabación. Inténtalo de nuevo, cerca del micrófono.' },
        { status: 502 },
      )
    }
    return NextResponse.json({ ok: true, texto })
  } catch {
    return NextResponse.json(
      { ok: false, mensaje: 'El dictado no está disponible ahora mismo. Inténtalo en unos segundos.' },
      { status: 503 },
    )
  }
}
