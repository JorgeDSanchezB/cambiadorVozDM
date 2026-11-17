// GET /api/personajes/estado?id=… — estado de una generación.
// Si el trabajo de FakeYou terminó, se descarga el WAV, se guarda en la
// caché (SQLite) y se devuelve "listo". El audio se sirve desde
// /api/personajes/audio?id=… con caché inmutable.

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { ErrorFakeyou, consultarJob, descargarAudio, leerSesion } from '@/lib/fakeyou'

const MS_MAX_ESPERA_JOB = 3 * 60 * 1000

export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) {
    return NextResponse.json({ ok: false, error: 'falta_id' }, { status: 400 })
  }

  const fila = await db.generacionPersonaje.findUnique({ where: { id } })
  if (!fila) {
    return NextResponse.json({ ok: false, error: 'no_encontrado' }, { status: 404 })
  }
  if (fila.estado === 'listo') {
    return NextResponse.json({ ok: true, estado: 'listo', tituloVoz: fila.tituloVoz })
  }
  if (fila.estado === 'error') {
    return NextResponse.json(
      { ok: true, estado: 'error', mensaje: fila.error ?? 'La generación falló', tituloVoz: fila.tituloVoz },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  }
  if (!fila.jobToken) {
    return NextResponse.json(
      { ok: true, estado: 'pendiente', tituloVoz: fila.tituloVoz },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  }

  // Guardián: un trabajo no puede quedarse "pendiente" para siempre.
  if (Date.now() - fila.createdAt.getTime() > MS_MAX_ESPERA_JOB) {
    await db.generacionPersonaje.update({
      where: { id: fila.id },
      data: { estado: 'error', error: 'La síntesis tardó demasiado (FakeYou no respondió)' },
    })
    return NextResponse.json({ ok: true, estado: 'error', mensaje: 'La síntesis tardó demasiado' })
  }

  const sesion = leerSesion(req) ?? undefined
  try {
    const job = await consultarJob(fila.jobToken, sesion)

    if (job.estado === 'listo' && job.audioUrl) {
      try {
        const wav = await descargarAudio(job.audioUrl)
        await db.generacionPersonaje.update({
          where: { id: fila.id },
          data: { estado: 'listo', audioB64: wav.toString('base64') },
        })
        return NextResponse.json({ ok: true, estado: 'listo', tituloVoz: fila.tituloVoz })
      } catch (e) {
        const mensaje = e instanceof Error ? e.message : 'No se pudo guardar el audio'
        await db.generacionPersonaje.update({
          where: { id: fila.id },
          data: { estado: 'error', error: mensaje },
        })
        return NextResponse.json({ ok: true, estado: 'error', mensaje })
      }
    }

    if (job.estado === 'error') {
      await db.generacionPersonaje.update({
        where: { id: fila.id },
        data: { estado: 'error', error: job.mensaje ?? 'La síntesis falló en FakeYou' },
      })
      return NextResponse.json(
        { ok: true, estado: 'error', mensaje: job.mensaje ?? 'La síntesis falló', tituloVoz: fila.tituloVoz },
        { headers: { 'Cache-Control': 'no-store' } },
      )
    }

    // Pendiente (o fallo de red transitorio): el cliente sigue sondeando.
    return NextResponse.json(
      { ok: true, estado: 'pendiente', tituloVoz: fila.tituloVoz },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (e) {
    // Error transitorio de red al consultar: no quemamos la generación,
    // seguimos en pendiente hasta el guardián de tiempo.
    if (e instanceof ErrorFakeyou && e.codigo !== 'limite') {
      return NextResponse.json(
        { ok: true, estado: 'pendiente', tituloVoz: fila.tituloVoz },
        { headers: { 'Cache-Control': 'no-store' } },
      )
    }
    const mensaje = e instanceof Error ? e.message : 'Error consultando a FakeYou'
    await db.generacionPersonaje.update({
      where: { id: fila.id },
      data: { estado: 'error', error: mensaje },
    })
    return NextResponse.json({ ok: true, estado: 'error', mensaje, tituloVoz: fila.tituloVoz })
  }
}
