// POST /api/personajes/generar — pide una síntesis a FakeYou.
//
// Flujo: validar (texto ≤ 500, voz dentro del catálogo latino) → buscar en
// caché (la misma voz+texto no se re-sintetiza) → crear fila pendiente →
// enviar el trabajo a FakeYou (cola con enfriamiento) → devolver el id.
// El cliente consulta /api/personajes/estado?id=… hasta que esté listo.
// `sesion` opcional: token de sesión de FakeYou para más cupo.

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { ErrorFakeyou, MAX_TEXTO, enviarInferencia, esTokenLatino, leerSesion } from '@/lib/fakeyou'

const MS_PENDIENTE_REUTILIZABLE = 3 * 60 * 1000

function normalizar(texto: string): string {
  return texto.trim().replace(/\s+/g, ' ')
}

export async function POST(req: NextRequest) {
  let cuerpo: { modelToken?: unknown; tituloVoz?: unknown; texto?: unknown; sesion?: unknown }
  try {
    cuerpo = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'cuerpo_invalido' }, { status: 400 })
  }

  const modelToken = typeof cuerpo.modelToken === 'string' ? cuerpo.modelToken : ''
  const tituloVoz = typeof cuerpo.tituloVoz === 'string' ? cuerpo.tituloVoz.trim().slice(0, 200) : ''
  const texto = typeof cuerpo.texto === 'string' ? normalizar(cuerpo.texto) : ''

  if (!modelToken || !tituloVoz) {
    return NextResponse.json({ ok: false, error: 'voz_requerida' }, { status: 400 })
  }
  if (texto.length === 0) {
    return NextResponse.json({ ok: false, error: 'texto_vacio' }, { status: 400 })
  }
  if (texto.length > MAX_TEXTO) {
    return NextResponse.json(
      { ok: false, error: 'texto_largo', limite: MAX_TEXTO },
      { status: 413 },
    )
  }
  if (!(await esTokenLatino(modelToken))) {
    return NextResponse.json({ ok: false, error: 'voz_fuera_de_catalogo' }, { status: 400 })
  }

  // Caché: la misma voz con el mismo texto ya generada se devuelve directa.
  const cacheada = await db.generacionPersonaje.findFirst({
    where: { modelToken, texto, estado: 'listo' },
    orderBy: { createdAt: 'desc' },
  })
  if (cacheada) {
    return NextResponse.json({ ok: true, id: cacheada.id, estado: 'listo', cacheado: true })
  }

  // ¿Hay un envío reciente en curso para lo mismo? Se reutiliza en vez de
  // gastar más cupo de FakeYou.
  const pendiente = await db.generacionPersonaje.findFirst({
    where: {
      modelToken,
      texto,
      estado: 'pendiente',
      createdAt: { gte: new Date(Date.now() - MS_PENDIENTE_REUTILIZABLE) },
    },
    orderBy: { createdAt: 'desc' },
  })
  if (pendiente) {
    return NextResponse.json({ ok: true, id: pendiente.id, estado: 'pendiente', cacheado: true })
  }

  const fila = await db.generacionPersonaje.create({
    data: { modelToken, tituloVoz, texto, estado: 'pendiente' },
  })

  const sesion = leerSesion(req, cuerpo.sesion) ?? undefined
  try {
    const { jobToken } = await enviarInferencia(modelToken, texto, sesion)
    await db.generacionPersonaje.update({ where: { id: fila.id }, data: { jobToken } })
    return NextResponse.json({ ok: true, id: fila.id, estado: 'pendiente', cacheado: false })
  } catch (e) {
    const esLimite = e instanceof ErrorFakeyou && e.codigo === 'limite'
    const mensaje = e instanceof Error ? e.message : 'Fallo desconocido al enviar la síntesis'
    await db.generacionPersonaje.update({
      where: { id: fila.id },
      data: { estado: 'error', error: mensaje },
    })
    if (esLimite) {
      return NextResponse.json(
        {
          ok: false,
          error: 'limite_fakeyou',
          mensaje:
            'FakeYou está saturado: el cupo anónimo por IP se agotó. Espera unos minutos o conecta tu cuenta de FakeYou en Ajustes.',
        },
        { status: 429 },
      )
    }
    return NextResponse.json({ ok: false, error: 'envio_fallo', mensaje }, { status: 502 })
  }
}
