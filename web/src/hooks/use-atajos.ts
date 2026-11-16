// Atajos de teclado — la tecla de cada voz se dispara en cualquier página.
// Los atajos vienen del DATO (campo "atajo" de cada voz) y el usuario puede
// reasignarlos a voluntad en Ajustes (la del catálogo es solo sugerencia).

'use client'

import { useEffect } from 'react'
import { toast } from 'sonner'
import { normalizarAtajo } from '@/lib/voces'
import { useVozStore } from '@/store/voz'

export function useAtajosVoces(): void {
  const voces = useVozStore((s) => s.voces)
  const atajosActivos = useVozStore((s) => s.ajustes.atajos)
  const capturandoAtajo = useVozStore((s) => s.capturandoAtajoId)
  const seleccionarVoz = useVozStore((s) => s.seleccionarVoz)

  useEffect(() => {
    if (!atajosActivos || capturandoAtajo) return

    const alPulsar = (e: KeyboardEvent) => {
      const objetivo = e.target as HTMLElement | null
      if (
        objetivo &&
        (objetivo.tagName === 'INPUT' || objetivo.tagName === 'TEXTAREA' || objetivo.isContentEditable)
      ) {
        return
      }
      const combo = normalizarAtajo(e.key, e.shiftKey)
      if (!combo) return
      const voz = voces.find((v) => v.atajo === combo)
      if (!voz) return
      e.preventDefault()
      seleccionarVoz(voz.id)
      toast.success(`Voz: ${voz.nombre}`, { description: `Atajo ${combo}`, duration: 1800 })
    }

    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [voces, atajosActivos, capturandoAtajo, seleccionarVoz])
}
