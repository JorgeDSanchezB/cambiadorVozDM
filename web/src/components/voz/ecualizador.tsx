// Ecualizador decorativo — barras CSS puras con la paleta de brasa. En
// reposo respiran lentas; con `activa` (micrófono en marcha) se aceleran y
// crecen. Con prefers-reduced-motion quedan fijas (ver globals.css).

'use client'

import { cn } from '@/lib/utils'

interface Props {
  activa?: boolean
  barras?: number
  className?: string
  etiqueta?: string
}

export function Ecualizador({ activa = false, barras = 24, className, etiqueta }: Props) {
  return (
    <div
      role="img"
      aria-label={
        etiqueta ?? (activa ? 'Barras de la consola en marcha' : 'Barras de la consola en reposo')
      }
      className={cn('flex h-16 items-end justify-between gap-[3px]', activa && 'eq-viva', className)}
    >
      {Array.from({ length: barras }).map((_, i) => (
        <span
          key={i}
          className="barra-eq w-full max-w-[6px] flex-1 origin-bottom rounded-full bg-gradient-to-t from-primary/25 via-primary/80 to-amber-200/90"
          style={{
            // Silueta de onda: alturas base variadas (techo ~90 %) para que
            // ni en reposo parezca una regla y los pices respiren.
            height: `${34 + 54 * Math.abs(Math.sin((i / barras) * Math.PI * 2.5))}%`,
            animationDelay: `${(-0.11 * i - 0.3).toFixed(2)}s`,
          }}
        />
      ))}
    </div>
  )
}
