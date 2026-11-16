// Favoritos de personajes: GET (lista), POST (marcar) y DELETE (quitar).
// Persisten en SQLite para que las voces estrella del DM sobrevivan a
// cambios de navegador.

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { esTokenLatino } from '@/lib/fakeyou'

export async function GET() {
  const favoritos = await db.favoritoPersonaje.findMany({ orderBy: { createdAt: 'asc' } })
  return NextResponse.json(
    {
      ok: true,
      favoritos: favoritos.map((f) => ({ modelToken: f.modelToken, tituloVoz: f.tituloVoz })),
    },
    { headers: { 'Cache-Control': 'no-store' } },
  )
}

export async function POST(req: NextRequest) {
  let cuerpo: { modelToken?: unknown; tituloVoz?: unknown }
  try {
    cuerpo = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'cuerpo_invalido' }, { status: 400 })
  }

  const modelToken = typeof cuerpo.modelToken === 'string' ? cuerpo.modelToken : ''
  const tituloVoz = typeof cuerpo.tituloVoz === 'string' ? cuerpo.tituloVoz.trim().slice(0, 200) : ''
  if (!modelToken || !tituloVoz) {
    return NextResponse.json({ ok: false, error: 'datos_incompletos' }, { status: 400 })
  }
  if (!(await esTokenLatino(modelToken))) {
    return NextResponse.json({ ok: false, error: 'voz_fuera_de_catalogo' }, { status: 400 })
  }

  const favorito = await db.favoritoPersonaje.upsert({
    where: { modelToken },
    create: { modelToken, tituloVoz },
    update: { tituloVoz },
  })
  return NextResponse.json({ ok: true, modelToken: favorito.modelToken })
}

export async function DELETE(req: NextRequest) {
  const modelToken = req.nextUrl.searchParams.get('modelToken')
  if (!modelToken) {
    return NextResponse.json({ ok: false, error: 'falta_modelToken' }, { status: 400 })
  }
  await db.favoritoPersonaje.deleteMany({ where: { modelToken } })
  return NextResponse.json({ ok: true })
}
