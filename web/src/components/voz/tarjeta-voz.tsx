// Tarjeta de voz — icono, color y atajo vienen del DATO (catálogo espejo).

'use client'

import { Loader2, Play, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Voz } from '@/lib/tipos'

interface Props {
  voz: Voz
  activa: boolean
  probando: boolean
  onSeleccionar: () => void
  onProbar: () => void
  onBorrar?: () => void
}

export function TarjetaVoz({ voz, activa, probando, onSeleccionar, onProbar, onBorrar }: Props) {
  return (
    <Card
      role="button"
      tabIndex={0}
      aria-pressed={activa}
      onClick={onSeleccionar}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSeleccionar()
        }
      }}
      className={cn(
        'cursor-pointer gap-0 border p-3 transition-all hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
        activa && 'border-primary/70 bg-accent/40 shadow-sm ring-1 ring-primary/30',
      )}
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="w-1.5 self-stretch rounded-full"
          style={{ backgroundColor: voz.color }}
        />
        <span aria-hidden="true" className="text-2xl leading-none select-none">
          {voz.icono}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {voz.nombre}
            {activa && <span className="sr-only">(voz activa)</span>}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-1">
            {voz.atajo && (
              <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                {voz.atajo}
              </Badge>
            )}
            {voz.tipo === 'IA' && (
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                IA · degrada a DSP
              </Badge>
            )}
            {voz.personalizada && (
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                Personal
              </Badge>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="size-8"
            disabled={probando}
            onClick={(e) => {
              e.stopPropagation()
              onProbar()
            }}
            title={`Escuchar una frase con la voz ${voz.nombre}`}
            aria-label={`Probar la voz ${voz.nombre}`}
          >
            {probando ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          </Button>
          {voz.personalizada && onBorrar && (
            <Button
              size="icon"
              variant="ghost"
              className="size-8 text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation()
                onBorrar()
              }}
              title="Eliminar voz personalizada"
              aria-label={`Eliminar la voz ${voz.nombre}`}
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}
