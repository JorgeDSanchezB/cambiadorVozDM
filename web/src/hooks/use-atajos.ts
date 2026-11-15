// Atajos de teclado — espejo del mapa F1-F12 / Shift+F1-F6 del escritorio.
// Los atajos vienen del DATO (campo "atajo" de cada voz), no del código.

'use client'

import { useEffect } from 'react'
import { toast } from 'sonner'
import { useVozStore } from '@/store/voz'

export function useAtajosVoces(): void {
  const voces = useVozStore((s) => s.voces)
  const atajosActivos = useVozStore((s) => s.ajustes.atajos)
  const seleccionarVoz = useVozStore((s) => s.seleccionarVoz)

  useEffect(() => {
    if (!atajosActivos) return

    const alPulsar = (e: KeyboardEvent) => {
      const objetivo = e.target as HTMLElement | null
      if (
        objetivo &&
        (objetivo.tagName === 'INPUT' || objetivo.tagName === 'TEXTAREA' || objetivo.isContentEditable)
      ) {
        return
      }
      if (!/^F([1-9]|1[0-2])$/.test(e.key)) return
      // Los datos tienen un atajo repetido (F11): gana la primera voz.
      const combo = `${e.shiftKey ? 'Shift+' : ''}${e.key}`
      const voz = voces.find((v) => v.atajo === combo)
      if (!voz) return
      e.preventDefault()
      seleccionarVoz(voz.id)
      toast.success(`Voz: ${voz.nombre}`, { description: `Atajo ${combo}`, duration: 1800 })
    }

    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [voces, atajosActivos, seleccionarVoz])
}
