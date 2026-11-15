// Avisos de degradación — espejo de los banners honestos del escritorio:
// la app sigue funcionando, pero el usuario siempre sabe en qué modo.

'use client'

import { AlertTriangle, X } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useVozStore } from '@/store/voz'

export function AvisosDegradacion() {
  const degradaciones = useVozStore((s) => s.degradaciones)
  const quitar = useVozStore((s) => s.quitarDegradacion)
  if (degradaciones.length === 0) return null

  return (
    <div className="mx-auto w-full max-w-6xl space-y-2 px-4 pt-4">
      {degradaciones.map((d) => (
        <Alert key={d.id} variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Modo degradado</AlertTitle>
          <AlertDescription className="flex items-start justify-between gap-2">
            <span>{d.mensaje}</span>
            <button
              type="button"
              onClick={() => quitar(d.id)}
              className="shrink-0 rounded p-1 hover:bg-foreground/10"
              aria-label="Descartar aviso"
            >
              <X className="size-3.5" />
            </button>
          </AlertDescription>
        </Alert>
      ))}
    </div>
  )
}
