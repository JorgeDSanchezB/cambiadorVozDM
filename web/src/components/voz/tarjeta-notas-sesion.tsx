// Card «Notas de sesión» — dictado para el DM (idea del Dictation Widget de
// VoiceStudio): graba una nota con el micrófono, se transcribe en el
// servidor (ASR) y queda en una lista con fecha. La grabación usa un
// MediaRecorder independiente del motor DSP: el cambiador de voz sigue
// funcionando mientras dictas. Transcripción automática: puede contener
// errores (avisado honestamente en la UI).

'use client'

import { useEffect, useRef, useState } from 'react'
import { Copy, Loader2, Mic, NotebookPen, Square, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { clasificarError } from '@/lib/errores'

const CLAVE_NOTAS = 'voz_dnd_web.notas_sesion'
const MAX_NOTAS = 100
// Auto-corte de seguridad: una nota de 5 minutos ya es un capítulo entero.
const MAX_MS_NOTA = 5 * 60 * 1000

interface Nota {
  id: string
  createdAt: string
  texto: string
}

function leerNotas(): Nota[] {
  try {
    const crudo = window.localStorage.getItem(CLAVE_NOTAS)
    if (!crudo) return []
    const parseado = JSON.parse(crudo) as unknown
    if (!Array.isArray(parseado)) return []
    return parseado
      .filter(
        (n): n is Nota =>
          typeof n === 'object' &&
          n !== null &&
          typeof (n as Nota).id === 'string' &&
          typeof (n as Nota).createdAt === 'string' &&
          typeof (n as Nota).texto === 'string',
      )
      .slice(0, MAX_NOTAS)
  } catch {
    return []
  }
}

function escribirNotas(notas: Nota[]): void {
  try {
    window.localStorage.setItem(CLAVE_NOTAS, JSON.stringify(notas))
  } catch {
    /* modo privado: las notas viven solo en memoria */
  }
}

function fechaCorta(iso: string): string {
  return new Date(iso).toLocaleString('es', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function TarjetaNotasSesion() {
  const [notas, setNotas] = useState<Nota[]>([])
  const [grabando, setGrabando] = useState(false)
  const [transcribiendo, setTranscribiendo] = useState(false)
  const [segundos, setSegundos] = useState(0)
  const grabadoraRef = useRef<MediaRecorder | null>(null)
  const fragmentosRef = useRef<Blob[]>([])
  const temporizadorRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setNotas(leerNotas())
    return () => {
      // Sin residuos: si se desmonta la pestaña con la grabadora abierta,
      // se corta y se liberan los recursos del navegador.
      if (temporizadorRef.current) clearInterval(temporizadorRef.current)
      if (grabadoraRef.current && grabadoraRef.current.state === 'recording') {
        grabadoraRef.current.stop()
        grabadoraRef.current.stream.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  const persistir = (nuevas: Nota[]) => {
    setNotas(nuevas)
    escribirNotas(nuevas)
  }

  const grabar = async () => {
    try {
      const flujo = await navigator.mediaDevices.getUserMedia({ audio: true })
      fragmentosRef.current = []
      const grabadora = new MediaRecorder(flujo)
      grabadora.ondataavailable = (e) => {
        if (e.data.size > 0) fragmentosRef.current.push(e.data)
      }
      grabadora.start()
      grabadoraRef.current = grabadora
      setGrabando(true)
      setSegundos(0)
      temporizadorRef.current = setInterval(() => {
        setSegundos((s) => s + 1)
      }, 1000)
      // Auto-corte de seguridad (5 min).
      setTimeout(() => {
        if (grabadoraRef.current?.state === 'recording') {
          toast.info('Corte automático a los 5 minutos')
          detener()
        }
      }, MAX_MS_NOTA)
    } catch (e) {
      const err = clasificarError(e, 'microfono')
      toast.error(err.titulo, { description: err.remedio })
    }
  }

  const detener = () => {
    if (temporizadorRef.current) {
      clearInterval(temporizadorRef.current)
      temporizadorRef.current = null
    }
    const grabadora = grabadoraRef.current
    if (!grabadora || grabadora.state === 'inactive') {
      setGrabando(false)
      return
    }
    grabadora.addEventListener('stop', () => {
      grabadora.stream.getTracks().forEach((t) => t.stop())
      grabadoraRef.current = null
      setGrabando(false)
      void transcribir()
    })
    grabadora.stop()
  }

  const transcribir = async () => {
    const fragmentos = fragmentosRef.current
    if (fragmentos.length === 0) {
      toast.error('La grabación salió vacía', { description: 'Inténtalo de nuevo.' })
      return
    }
    setTranscribiendo(true)
    try {
      const blob = new Blob(fragmentos, { type: fragmentos[0].type || 'audio/webm' })
      const base64 = await new Promise<string>((resolver, rechazar) => {
        const lector = new FileReader()
        lector.onloadend = () => {
          const resultado = String(lector.result ?? '')
          const coma = resultado.indexOf(',')
          resolver(coma >= 0 ? resultado.slice(coma + 1) : resultado)
        }
        lector.onerror = () => rechazar(new Error('No se pudo leer la grabación'))
        lector.readAsDataURL(blob)
      })
      const resp = await fetch('/api/notas/transcribir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_base64: base64 }),
      })
      const data = (await resp.json()) as { ok?: boolean; mensaje?: string; texto?: string }
      if (!resp.ok || !data.ok || !data.texto) {
        toast.error(data.mensaje ?? 'La transcripción falló', {
          description: 'La grabación se descartó: dicta la nota de nuevo.',
        })
        return
      }
      const nueva: Nota = {
        id: `nota-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        createdAt: new Date().toISOString(),
        texto: data.texto,
      }
      persistir([nueva, ...notas])
      toast.success('Nota añadida', { description: 'Revisa el texto: la transcripción puede contener errores.' })
    } catch {
      toast.error('Fallo de red al transcribir la nota', {
        description: 'Revisa tu conexión e inténtalo de nuevo.',
      })
    } finally {
      setTranscribiendo(false)
    }
  }

  const copiar = async (nota: Nota) => {
    try {
      await navigator.clipboard.writeText(nota.texto)
      toast.success('Nota copiada al portapapeles')
    } catch {
      toast.error('El navegador no permitió copiar', { description: 'Selecciona el texto y cópialo a mano.' })
    }
  }

  const borrar = (id: string) => {
    persistir(notas.filter((n) => n.id !== id))
  }

  const vaciar = () => {
    persistir([])
    toast.success('Notas vaciadas')
  }

  const mmss = `${String(Math.floor(segundos / 60)).padStart(2, '0')}:${String(segundos % 60).padStart(2, '0')}`

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <NotebookPen className="size-4 text-muted-foreground" aria-hidden="true" />
          Notas de sesión
        </CardTitle>
        <CardDescription>
          Dicta notas mientras juegas y quedan transcritas. El cambiador de voz sigue funcionando
          mientras grabas.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {grabando ? (
            <Button variant="destructive" onClick={detener}>
              <Square className="size-4" aria-hidden="true" />
              Terminar la nota ({mmss})
            </Button>
          ) : (
            <Button onClick={() => void grabar()} disabled={transcribiendo}>
              <Mic className="size-4" aria-hidden="true" />
              Dictar una nota
            </Button>
          )}
          {transcribiendo && (
            <span className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Transcribiendo…
            </span>
          )}
          {grabando && (
            <span className="flex items-center gap-2 text-sm text-destructive" role="status">
              <span className="size-2 animate-pulse rounded-full bg-destructive" aria-hidden="true" />
              Grabando…
            </span>
          )}
        </div>

        {notas.length > 0 && (
          <>
            <ul className="rol-custom max-h-72 space-y-1.5 overflow-y-auto pr-1" aria-label="Notas de la sesión">
              {notas.map((n) => (
                <li key={n.id} className="flex items-start gap-2 rounded-md border p-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] text-muted-foreground">{fechaCorta(n.createdAt)}</p>
                    <p className="whitespace-pre-wrap text-xs">{n.texto}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label="Copiar nota"
                      onClick={() => void copiar(n)}
                    >
                      <Copy className="size-3.5" aria-hidden="true" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 text-muted-foreground hover:text-destructive"
                      aria-label="Borrar nota"
                      onClick={() => borrar(n.id)}
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={vaciar}>
                Vaciar notas
              </Button>
              <span className="self-center text-xs text-muted-foreground">{notas.length} nota(s) en este navegador</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
