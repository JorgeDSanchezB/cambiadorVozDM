// Pie de página — fijo al fondo (regla de layout), recuerda la regla de
// espejo entre ramas del repo.

'use client'

import { useVozStore } from '@/store/voz'

export function PiePagina() {
  const total = useVozStore((s) => s.voces.length)
  return (
    <footer className="mt-auto border-t bg-muted/50">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-xs text-muted-foreground">
        <span>Cambiador de Voz DM · versión web (espejo de voz_dnd)</span>
        <span>
          {total} voces · rama feat/web-app · todo cambio se refleja en ambas ramas
        </span>
      </div>
    </footer>
  )
}
