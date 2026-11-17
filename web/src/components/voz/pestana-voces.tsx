// Pestaña Voces — selector con búsqueda (espejo de la vista de botones del
// escritorio). El grid se alimenta del catálogo generado; lista larga con
// scroll propio.

'use client'

import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Eye, EyeOff, Search, SlidersHorizontal } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { clasificarError } from '@/lib/errores'
import { probarVoz } from '@/lib/tts'
import type { Voz } from '@/lib/tipos'
import { useVozStore } from '@/store/voz'
import { TarjetaVoz } from './tarjeta-voz'

export function PestanaVoces() {
  const voces = useVozStore((s) => s.voces)
  const vocesOcultas = useVozStore((s) => s.vocesOcultas)
  const vozActivaId = useVozStore((s) => s.vozActivaId)
  const seleccionarVoz = useVozStore((s) => s.seleccionarVoz)
  const borrarVozPersonalizada = useVozStore((s) => s.borrarVozPersonalizada)
  const ocultarVoz = useVozStore((s) => s.ocultarVoz)
  const restaurarVocesOcultas = useVozStore((s) => s.restaurarVocesOcultas)

  const [busqueda, setBusqueda] = useState('')
  const [probandoId, setProbandoId] = useState<string | null>(null)

  const filtradas = useMemo(() => {
    const normalizar = (s: string) =>
      s.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '')
    const q = normalizar(busqueda.trim())
    if (!q) return voces
    return voces.filter((v) => normalizar(v.nombre).includes(q))
  }, [voces, busqueda])

  const probar = async (voz: Voz) => {
    if (probandoId) return
    setProbandoId(voz.id)
    try {
      await probarVoz(voz.parametros_dsp)
    } catch (e) {
      const err = clasificarError(e, 'tts')
      toast.error(`No se pudo probar la voz (${err.titulo})`, { description: err.remedio })
    } finally {
      setProbandoId(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* La voz activa vive en el monitor del héroe (arriba): aquí solo el
          catálogo, sin duplicar información. */}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-52 flex-1">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar voz por nombre…"
            className="border-border bg-card/70 pl-8 backdrop-blur-sm"
            aria-label="Buscar voz por nombre"
          />
        </div>
        <Badge variant="outline" className="h-9 gap-1 border-border bg-card/50 px-3">
          <SlidersHorizontal className="size-3" aria-hidden="true" />
          {filtradas.length} de {voces.length}
        </Badge>
        {vocesOcultas.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            onClick={restaurarVocesOcultas}
            title="Volver a mostrar todas las voces quitadas"
          >
            <Eye className="size-3.5" aria-hidden="true" />
            {vocesOcultas.length} oculta{vocesOcultas.length === 1 ? '' : 's'} · Restaurar
          </Button>
        )}
      </div>

      <div className="rol-custom max-h-[32rem] overflow-y-auto pr-1">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtradas.map((voz) => (
            <TarjetaVoz
              key={voz.id}
              voz={voz}
              activa={voz.id === vozActivaId}
              probando={probandoId === voz.id}
              onSeleccionar={() => seleccionarVoz(voz.id)}
              onProbar={() => probar(voz)}
              onBorrar={voz.personalizada ? () => borrarVozPersonalizada(voz.id) : undefined}
              onOcultar={!voz.personalizada ? () => ocultarVoz(voz.id) : undefined}
            />
          ))}
        </div>
        {filtradas.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna voz coincide con la búsqueda.
          </p>
        )}
      </div>
    </div>
  )
}
