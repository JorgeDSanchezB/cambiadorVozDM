// Fondo de escena — brasas que ascienden (canvas), resplandores de antorcha
// y grano de película. Puramente decorativo (aria-hidden), respeta
// prefers-reduced-motion (marco estático, sin bucle) y se pausa cuando la
// pestaña no está visible.

'use client'

import { useEffect, useRef } from 'react'

interface Brasa {
  x: number
  y: number
  r: number
  vy: number // px/s hacia arriba
  vx: number
  baseA: number
  fase: number
  velFase: number
  tono: number // matiz (naranja→ámbar)
}

const DPR_MAX = 2

export function FondoEscena() {
  const lienzoRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const lienzo = lienzoRef.current
    if (!lienzo) return
    const ctx = lienzo.getContext('2d')
    if (!ctx) return

    const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let ancho = 0
    let alto = 0
    let brasas: Brasa[] = []

    const crearBrasa = (desdeAbajo = false): Brasa => ({
      x: Math.random() * ancho,
      // Nacen concentradas abajo (corriente térmica de la forja): así el
      // enjambre tiene dirección incluso en una captura estática.
      y: desdeAbajo ? alto + 10 : alto * (1 - Math.random() ** 1.8),
      r: 1.6 + Math.random() * 2.8,
      vy: 9 + Math.random() * 20,
      vx: (Math.random() - 0.5) * 9,
      baseA: 0.3 + Math.random() * 0.4,
      fase: Math.random() * Math.PI * 2,
      velFase: 0.8 + Math.random() * 1.8,
      tono: 22 + Math.random() * 26,
    })

    const pintarBrasa = (b: Brasa, alfa: number, conGlow: boolean) => {
      ctx.beginPath()
      ctx.fillStyle = `hsla(${b.tono}, 94%, 64%, ${alfa.toFixed(3)})`
      if (conGlow) {
        ctx.shadowColor = `hsla(${b.tono}, 96%, 58%, ${(alfa * 0.9).toFixed(3)})`
        ctx.shadowBlur = 14
      }
      ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2)
      ctx.fill()
    }

    const dibujarEstatico = () => {
      ctx.clearRect(0, 0, ancho, alto)
      for (const b of brasas) pintarBrasa(b, b.baseA * 0.5, false)
      ctx.shadowBlur = 0
    }

    const ajustar = () => {
      // Se recalcula en cada ajuste: al mover la ventana a otro monitor el
      // devicePixelRatio puede cambiar y el lienzo quedaría borroso.
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_MAX)
      ancho = window.innerWidth
      alto = window.innerHeight
      lienzo.width = Math.round(ancho * dpr)
      lienzo.height = Math.round(alto * dpr)
      lienzo.style.width = `${ancho}px`
      lienzo.style.height = `${alto}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const objetivo = Math.max(12, Math.min(30, Math.round((ancho * alto) / 56000)))
      brasas = Array.from({ length: objetivo }, () => crearBrasa())
      if (reducido) dibujarEstatico()
    }

    let tPrevia = performance.now()
    const cuadro = (t: number) => {
      raf = requestAnimationFrame(cuadro)
      if (document.hidden) {
        tPrevia = t
        return
      }
      const dt = Math.min(0.05, (t - tPrevia) / 1000)
      tPrevia = t
      ctx.clearRect(0, 0, ancho, alto)
      for (const b of brasas) {
        b.y -= b.vy * dt
        b.x += b.vx * dt + Math.sin(b.fase) * 0.35
        b.fase += b.velFase * dt
        if (b.y < -12 || b.x < -24 || b.x > ancho + 24) {
          Object.assign(b, crearBrasa(true))
          continue
        }
        // Se desvanecen al ganar altura, como brasas reales: a partir del
        // 55 % de la pantalla casi no hay señal (el enjambre vive abajo).
        const vida = Math.min(1, b.y / (alto * 0.55))
        const alfa = b.baseA * vida * (0.72 + 0.28 * Math.sin(b.fase * 2))
        pintarBrasa(b, alfa, true)
      }
      ctx.shadowBlur = 0
    }

    ajustar()
    if (!reducido) raf = requestAnimationFrame(cuadro)

    window.addEventListener('resize', ajustar)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', ajustar)
    }
  }, [])

  return (
    <>
      {/* Escena: base, antorchas, brasas y viñeta. Siempre detrás (-z-10). */}
      <div aria-hidden="true" className="fixed inset-0 -z-10 overflow-hidden bg-background">
        <div className="llama-antorcha absolute -top-44 -left-36 size-[36rem] rounded-full bg-[radial-gradient(circle,oklch(0.55_0.13_62/0.15),transparent_65%)] blur-2xl" />
        <div className="llama-antorcha-2 absolute top-1/3 -right-44 size-[32rem] rounded-full bg-[radial-gradient(circle,oklch(0.5_0.1_45/0.11),transparent_65%)] blur-2xl" />
        <div className="absolute -bottom-52 left-1/4 size-[38rem] rounded-full bg-[radial-gradient(circle,oklch(0.45_0.08_70/0.08),transparent_65%)] blur-2xl" />
        <canvas ref={lienzoRef} className="absolute inset-0" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_52%,oklch(0.1_0.012_55/0.55))]" />
      </div>
      {/* Grano de película sobre la escena (bajo cabecera y diálogos). */}
      <div aria-hidden="true" className="grano pointer-events-none fixed inset-0 z-[5] opacity-[0.05]" />
    </>
  )
}
