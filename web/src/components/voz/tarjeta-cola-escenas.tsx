// Card «Cola de escenas» — narración por lotes (idea de la Batch Queue de
// VoiceStudio): varias escenas → varios WAV exportados en orden (un archivo
// por capítulo/escena). Renderiza con el motor del servidor y la cadena DSP
// de la voz elegida; con personajes FakeYou no aplica (se generan uno a uno).

'use client'

import { useEffect, useRef, useState } from 'react'
import { Download, Layers, Loader2, Plus, Square, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import { clasificarError } from '@/lib/errores'
import { renderizarLecturaAWav } from '@/lib/tts'
import { descargarBlob, marcaDeTiempo } from '@/lib/wav'
import type { ElegidaLectura } from './pestana-leer'

const CLAVE_COLA = 'voz_dnd_web.cola_escenas'
const MAX_ESCENAS = 30
const MAX_TEXTO_ESCENA = 20000

interface Escena {
  id: string
  titulo: string
  texto: string
}

type EstadoEscena = 'pendiente' | 'generando' | 'listo' | 'error'

const TEXTO_ESTADO: Record<EstadoEscena, string> = {
  pendiente: 'En la cola',
  generando: 'Renderizando…',
  listo: 'WAV descargado',
  error: 'Falló',
}

function leerCola(): Escena[] {
  try {
    const crudo = window.localStorage.getItem(CLAVE_COLA)
    if (!crudo) return []
    const parseado = JSON.parse(crudo) as unknown
    if (!Array.isArray(parseado)) return []
    return parseado
      .filter(
        (e): e is Escena =>
          typeof e === 'object' &&
          e !== null &&
          typeof (e as Escena).titulo === 'string' &&
          typeof (e as Escena).texto === 'string',
      )
      .slice(0, MAX_ESCENAS)
  } catch {
    return []
  }
}

function escribirCola(escenas: Escena[]): void {
  try {
    window.localStorage.setItem(CLAVE_COLA, JSON.stringify(escenas))
  } catch {
    /* modo privado: la cola vive solo en memoria */
  }
}

function slugTitulo(titulo: string): string {
  return titulo
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40) || 'escena'
}

interface PropsCola {
  textoActual: string
  elegida: ElegidaLectura | null
  velocidad: number
  esFakeYou: boolean
  motorNavegador: boolean
}

export function TarjetaColaEscenas({ textoActual, elegida, velocidad, esFakeYou, motorNavegador }: PropsCola) {
  const [escenas, setEscenas] = useState<Escena[]>([])
  const [estados, setEstados] = useState<Record<string, EstadoEscena>>({})
  const [titulo, setTitulo] = useState('')
  const [texto, setTexto] = useState('')
  const [renderizando, setRenderizando] = useState(false)
  const [progreso, setProgreso] = useState({ actual: 0, total: 0 })
  const abortRef = useRef<AbortController | null>(null)

  // La cola persiste en este navegador (tolerante a datos corruptos).
  useEffect(() => {
    setEscenas(leerCola())
  }, [])

  const persistir = (nuevas: Escena[]) => {
    setEscenas(nuevas)
    escribirCola(nuevas)
  }

  const puedeRenderizar = !esFakeYou && !motorNavegador && elegida !== null && !renderizando

  const añadir = () => {
    if (!texto.trim()) {
      toast.error('Escribe el texto de la escena')
      return
    }
    if (escenas.length >= MAX_ESCENAS) {
      toast.error(`Máximo ${MAX_ESCENAS} escenas en la cola`)
      return
    }
    const nueva: Escena = {
      id: `escena-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      titulo: titulo.trim() || `Escena ${escenas.length + 1}`,
      texto: texto.trim(),
    }
    persistir([...escenas, nueva])
    setEstados((prev) => ({ ...prev, [nueva.id]: 'pendiente' }))
    setTitulo('')
    setTexto('')
  }

  const enviarTextoActual = () => {
    if (!textoActual.trim()) {
      toast.info('El cuadro «Texto a leer» está vacío')
      return
    }
    const nueva: Escena = {
      id: `escena-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      titulo: `Escena ${escenas.length + 1}`,
      texto: textoActual.trim(),
    }
    if (escenas.length >= MAX_ESCENAS) {
      toast.error(`Máximo ${MAX_ESCENAS} escenas en la cola`)
      return
    }
    persistir([...escenas, nueva])
    setEstados((prev) => ({ ...prev, [nueva.id]: 'pendiente' }))
    toast.success('Escena añadida a la cola', { description: `«${nueva.titulo}» desde el texto a leer.` })
  }

  const quitar = (id: string) => {
    persistir(escenas.filter((e) => e.id !== id))
    setEstados((prev) => {
      const copia = { ...prev }
      delete copia[id]
      return copia
    })
  }

  const vaciar = () => {
    persistir([])
    setEstados({})
    setProgreso({ actual: 0, total: 0 })
  }

  const descargarEscena = async (escena: Escena) => {
    if (!puedeRenderizar) return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setEstados((prev) => ({ ...prev, [escena.id]: 'generando' }))
    try {
      const blob = await renderizarLecturaAWav({
        texto: escena.texto,
        velocidad,
        parametros: elegida.tipo === 'servidor' ? elegida.parametros : undefined,
        senal: ctrl.signal,
      })
      descargarBlob(blob, `escena_${slugTitulo(escena.titulo)}_${marcaDeTiempo()}.wav`)
      setEstados((prev) => ({ ...prev, [escena.id]: 'listo' }))
      toast.success(`«${escena.titulo}» descargada`)
    } catch (e) {
      setEstados((prev) => ({ ...prev, [escena.id]: 'error' }))
      if (!ctrl.signal.aborted) {
        const err = clasificarError(e, 'tts')
        toast.error(`No se pudo renderizar «${escena.titulo}»`, { description: err.remedio })
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null
    }
  }

  const renderizarCola = async () => {
    if (!puedeRenderizar || escenas.length === 0) return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setRenderizando(true)
    setProgreso({ actual: 0, total: escenas.length })
    let falladas = 0
    try {
      for (let i = 0; i < escenas.length; i++) {
        const escena = escenas[i]
        if (ctrl.signal.aborted) break
        setProgreso({ actual: i + 1, total: escenas.length })
        setEstados((prev) => ({ ...prev, [escena.id]: 'generando' }))
        try {
          const blob = await renderizarLecturaAWav({
            texto: escena.texto,
            velocidad,
            parametros: elegida.tipo === 'servidor' ? elegida.parametros : undefined,
            senal: ctrl.signal,
          })
          descargarBlob(blob, `escena_${i + 1}_${slugTitulo(escena.titulo)}_${marcaDeTiempo()}.wav`)
          setEstados((prev) => ({ ...prev, [escena.id]: 'listo' }))
          // Espacio entre descargas: los navegadores bloquean ráfagas de
          // descargas múltiples si no hay separación.
          await new Promise((r) => setTimeout(r, 900))
        } catch (e) {
          falladas += 1
          setEstados((prev) => ({ ...prev, [escena.id]: 'error' }))
          if (ctrl.signal.aborted) break
          const err = clasificarError(e, 'tts')
          toast.warning(`«${escena.titulo}» falló`, { description: err.remedio })
        }
      }
      if (!ctrl.signal.aborted) {
        const ok = escenas.length - falladas
        toast.success(`Cola terminada: ${ok} WAV descargados${falladas ? `, ${falladas} fallaron` : ''}`)
      }
    } finally {
      setRenderizando(false)
      if (abortRef.current === ctrl) abortRef.current = null
    }
  }

  const detenerCola = () => {
    abortRef.current?.abort()
    setRenderizando(false)
    toast.info('Cola detenida', { description: 'Las escenas siguen en la lista para reintentarlas.' })
  }

  const pendientes = escenas.filter((e) => (estados[e.id] ?? 'pendiente') !== 'listo').length

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Layers className="size-4 text-muted-foreground" aria-hidden="true" />
          Cola de escenas
        </CardTitle>
        <CardDescription>
          Varios textos → un WAV por escena, con la voz elegida y su cadena de efectos.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {esFakeYou || motorNavegador ? (
          <p className="text-sm text-muted-foreground" role="status">
            {esFakeYou
              ? 'Los personajes de FakeYou se generan uno a uno: la cola necesita un narrador o una voz propia (motor del servidor).'
              : 'La cola necesita el motor del servidor: la voz del navegador no puede renderizar WAV.'}
          </p>
        ) : (
          <>
            <div className="space-y-2">
              <Label htmlFor="escena-titulo">Título de la escena</Label>
              <Input
                id="escena-titulo"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value.slice(0, 60))}
                placeholder="P. ej. Capítulo 3 — La cripta"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="escena-texto">Texto de la escena</Label>
              <Textarea
                id="escena-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value.slice(0, MAX_TEXTO_ESCENA))}
                rows={3}
                placeholder="El contenido que narrará esta escena…"
                aria-label="Texto de la escena"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={añadir} disabled={renderizando}>
                <Plus className="size-4" aria-hidden="true" />
                Añadir a la cola
              </Button>
              <Button variant="outline" onClick={enviarTextoActual} disabled={renderizando}>
                <Plus className="size-4" aria-hidden="true" />
                Enviar el texto a leer
              </Button>
            </div>
          </>
        )}

        {escenas.length > 0 && (
          <>
            <ul className="rol-custom max-h-56 space-y-1.5 overflow-y-auto pr-1" aria-label="Escenas en la cola">
              {escenas.map((escena, i) => {
                const estado = estados[escena.id] ?? 'pendiente'
                return (
                  <li key={escena.id} className="flex items-center gap-2 rounded-md border p-2">
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">{i + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">{escena.titulo}</p>
                      <p className="truncate text-xs text-muted-foreground" title={escena.texto}>
                        {escena.texto}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${
                        estado === 'listo'
                          ? 'border-primary/40 text-primary'
                          : estado === 'error'
                            ? 'border-destructive/40 text-destructive'
                            : 'border-border/60 text-muted-foreground'
                      }`}
                      role="status"
                    >
                      {estado === 'generando' && (
                        <Loader2 className="mr-1 inline size-3 animate-spin" aria-hidden="true" />
                      )}
                      {TEXTO_ESTADO[estado]}
                    </span>
                    {estado === 'listo' && puedeRenderizar && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 shrink-0"
                        aria-label={`Volver a descargar «${escena.titulo}»`}
                        onClick={() => void descargarEscena(escena)}
                      >
                        <Download className="size-3.5" aria-hidden="true" />
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label={`Quitar «${escena.titulo}» de la cola`}
                      onClick={() => quitar(escena.id)}
                      disabled={renderizando}
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </Button>
                  </li>
                )
              })}
            </ul>

            {renderizando && progreso.total > 0 && (
              <div className="space-y-1.5">
                <Progress value={(progreso.actual / progreso.total) * 100} />
                <p className="text-xs text-muted-foreground" role="status">
                  Escena {progreso.actual} de {progreso.total}…
                </p>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {renderizando ? (
                <Button variant="outline" onClick={detenerCola}>
                  <Square className="size-4" aria-hidden="true" />
                  Detener la cola
                </Button>
              ) : (
                <>
                  <Button onClick={() => void renderizarCola()} disabled={!puedeRenderizar || pendientes === 0}>
                    <Download className="size-4" aria-hidden="true" />
                    Renderizar cola ({pendientes})
                  </Button>
                  <Button variant="outline" onClick={vaciar}>
                    Vaciar
                  </Button>
                </>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
