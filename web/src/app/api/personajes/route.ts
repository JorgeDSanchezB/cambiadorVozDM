// GET /api/personajes — catálogo latino de FakeYou (voces para PNJs).
// Se cachea en el servidor 6 h; si FakeYou falla se reintenta en cada visita.

import { NextResponse } from 'next/server'
import { ErrorFakeyou, obtenerCatalogoLatin } from '@/lib/fakeyou'

export async function GET() {
  try {
    const { voces, generadoEn } = await obtenerCatalogoLatin()
    return NextResponse.json(
      { ok: true, total: voces.length, generadoEn, voces },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (e) {
    const mensaje = e instanceof ErrorFakeyou ? e.message : 'El catálogo de FakeYou no está disponible'
    return NextResponse.json({ ok: false, error: 'catalogo_no_disponible', mensaje }, { status: 502 })
  }
}
