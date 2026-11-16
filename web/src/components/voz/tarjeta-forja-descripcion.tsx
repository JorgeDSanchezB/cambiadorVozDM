// Card «Forja por descripción» — inspirado en el Voice Design de VoiceStudio:
// describes la voz con palabras, la IA del servidor propone la cadena DSP
// completa y queda lista para guardar (con validación de rangos en el
// servidor: la IA nunca decide los límites).

'use client'

import { useState } from 'react'
import { Hammer, Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { resumenParametros } from '@/lib/voces'
import type { ParametrosDSP } from '@/lib/tipos'
import { useVozStore } from '@/store/voz'

const MAX_DESCRIPCION = 600

interface VozForjada {
  nombre: string
  icono: string
  color: string
  resumen: string
  parametros_dsp: ParametrosDSP
}

export function TarjetaForjaDescripcion() {
  const guardarVozPersonalizada = useVozStore((s) => s.guardarVozPersonalizada)

  const [descripcion, setDescripcion] = useState('')
  const [forjando, setForjando] = useState(false)
  const [forjada, setForjada] = useState<VozForjada | null>(null)

  const puedeForjar = descripcion.trim().length > 0 && !forjando

  const forjar = async () => {
    const limpia = descripcion.trim()
    if (!limpia) return
    setForjando(true)
    setForjada(null)
    try {
      const resp = await fetch('/api/creador/describir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ descripcion: limpia }),
      })
      const data = (await resp.json()) as { ok?: boolean; mensaje?: string; voz?: VozForjada }
      if (!resp.ok || !data.ok || !data.voz) {
        toast.error(data.mensaje ?? 'La forja IA falló', {
          description: 'Inténtalo de nuevo en unos segundos.',
        })
        return
      }
      setForjada(data.voz)
    } catch {
      toast.error('Fallo de red al hablar con la forja IA', {
        description: 'Revisa tu conexión e inténtalo de nuevo.',
      })
    } finally {
      setForjando(false)
    }
  }

  const guardar = () => {
    if (!forjada) return
    guardarVozPersonalizada(forjada.nombre, forjada.parametros_dsp, {
      icono: forjada.icono,
      color: forjada.color,
    })
    setForjada(null)
    setDescripcion('')
  }

  const chips = forjada ? resumenParametros(forjada.parametros_dsp) : []

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Hammer className="size-4 text-primary" aria-hidden="true" />
          Forja por descripción
        </CardTitle>
        <CardDescription>
          Describe la voz con palabras (p. ej. «hechicero oscuro con eco de cripta») y la IA forja
          la cadena completa. Luego puedes afinarla en el editor de abajo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value.slice(0, MAX_DESCRIPCION))}
          rows={3}
          maxLength={MAX_DESCRIPCION}
          placeholder="P. ej. una banshee gélida que susurra y su voz se congela al final de cada frase…"
          aria-label="Descripción de la voz a forjar"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void forjar()} disabled={!puedeForjar}>
            {forjando ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            {forjando ? 'Forjando…' : 'Forjar voz con la IA'}
          </Button>
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {forjando ? 'El martillo golpea el yunque…' : `${descripcion.length}/${MAX_DESCRIPCION}`}
          </span>
        </div>

        {forjada && (
          <div
            className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-4"
            aria-label="Voz forjada propuesta"
          >
            <div className="flex items-center gap-3">
              <span
                className="flex size-10 shrink-0 items-center justify-center rounded-full text-xl"
                style={{ backgroundColor: `${forjada.color}33` }}
                aria-hidden="true"
              >
                {forjada.icono}
              </span>
              <div className="min-w-0">
                <p className="truncate font-display text-lg leading-tight">{forjada.nombre}</p>
                {forjada.resumen && (
                  <p className="text-xs text-muted-foreground">{forjada.resumen}</p>
                )}
              </div>
            </div>

            {chips.length > 0 && (
              <ul className="flex flex-wrap gap-1.5" aria-label="Parámetros propuestos">
                {chips.map((c) => (
                  <li
                    key={c.etiqueta}
                    className="rounded-full border border-border/60 bg-background/60 px-2.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {c.etiqueta}: <span className="font-mono text-foreground">{c.texto}</span>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex flex-wrap gap-2">
              <Button onClick={guardar}>Guardar voz en la forja</Button>
              <Button variant="outline" onClick={() => setForjada(null)}>
                Descartar
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
