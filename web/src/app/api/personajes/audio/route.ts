// GET /api/personajes/audio?id=… — sirve el WAV cacheado de una generación.
// El contenido es inmutable (misma id, mismo audio): caché agresiva.

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) {
    return NextResponse.json({ ok: false, error: 'falta_id' }, { status: 400 })
  }

  const fila = await db.generacionPersonaje.findUnique({ where: { id } })
  if (!fila || fila.estado !== 'listo' || !fila.audioB64) {
    return NextResponse.json({ ok: false, error: 'audio_no_disponible' }, { status: 404 })
  }

  const buffer = Buffer.from(fila.audioB64, 'base64')
  return new NextResponse(new Uint8Array(buffer), {
    status: 200,
    headers: {
      'Content-Type': 'audio/wav',
      'Content-Length': String(buffer.length),
      'Cache-Control': 'public, max-age=31536000, immutable',
    },
  })
}
