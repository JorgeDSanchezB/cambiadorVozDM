// GET /api/personajes/historial — últimas generaciones (con su estado).
// DELETE ?id=… — borra una entrada del historial (y su audio cacheado).

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

const LIMITE = 40

export async function GET() {
  const filas = await db.generacionPersonaje.findMany({
    orderBy: { createdAt: 'desc' },
    take: LIMITE,
    select: {
      id: true,
      tituloVoz: true,
      texto: true,
      estado: true,
      error: true,
      createdAt: true,
    },
  })
  return NextResponse.json(
    {
      ok: true,
      historial: filas.map((f) => ({
        id: f.id,
        tituloVoz: f.tituloVoz,
        texto: f.texto.length > 140 ? `${f.texto.slice(0, 140)}…` : f.texto,
        estado: f.estado,
        error: f.error,
        createdAt: f.createdAt.toISOString(),
      })),
    },
    { headers: { 'Cache-Control': 'no-store' } },
  )
}

export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) {
    return NextResponse.json({ ok: false, error: 'falta_id' }, { status: 400 })
  }
  await db.generacionPersonaje.deleteMany({ where: { id } })
  return NextResponse.json({ ok: true })
}
