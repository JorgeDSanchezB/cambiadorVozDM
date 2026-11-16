// Barra de mando — transporte del micrófono: estado, nivel, pausa/reanudar,
// monitor, grabación post-DSP y descarga. Espejo de la barra del escritorio
// con el mismo comportamiento, ahora con el lenguaje visual de la forja.

'use client'

import { useEffect, useRef } from 'react'
import { Circle, Download, Flame, Headphones, Mic, MicOff, Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { motor } from '@/lib/motor-audio'
import { useVozStore } from '@/store/voz'

function MedidorNivel() {
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  const barra = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (estadoMotor !== 'activo' && estadoMotor !== 'pausado') {
      if (barra.current) barra.current.style.width = '0%'
      return
    }
    let raf = 0
    const tic = () => {
      const db = motor.nivelDb()
      const pct = Math.max(0, Math.min(100, ((db + 60) / 60) * 100))
      if (barra.current) barra.current.style.width = `${pct}%`
      raf = requestAnimationFrame(tic)
    }
    raf = requestAnimationFrame(tic)
    return () => cancelAnimationFrame(raf)
  }, [estadoMotor])

  // Apagado no se pinta: una regla vacía sin señal parece un artefacto.
  if (estadoMotor === 'detenido' || estadoMotor === 'iniciando') return null

  return (
    <div
      aria-hidden="true"
      className="relative hidden h-2 w-28 overflow-hidden rounded-full bg-muted/80 sm:block"
      title="Nivel del micrófono (dBFS)"
    >
      <div
        ref={barra}
        className="h-full w-0 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-500 transition-[width] duration-75"
      />
      {/* Separaciones de LED sobre la barra. */}
      <div className="pointer-events-none absolute inset-0 [background:repeating-linear-gradient(90deg,transparent_0,transparent_5px,var(--background)_5px,var(--background)_7px)]" />
    </div>
  )
}

function PillEstadoMic() {
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  const config = {
    detenido: { texto: 'Micrófono apagado', punto: 'bg-muted-foreground/40', pulso: false },
    iniciando: { texto: 'Iniciando…', punto: 'bg-amber-400', pulso: true },
    pausado: { texto: 'En pausa', punto: 'bg-amber-400', pulso: false },
    activo: { texto: 'En directo', punto: 'bg-emerald-400', pulso: true },
  }[estadoMotor]
  return (
    <span className="hidden items-center gap-1.5 rounded-full border border-border/60 bg-card/60 px-2.5 py-1 text-[11px] whitespace-nowrap text-muted-foreground sm:inline-flex">
      <span className={cn('size-1.5 rounded-full', config.punto, config.pulso && 'animate-pulse')} aria-hidden="true" />
      {config.texto}
    </span>
  )
}

export function Cabecera() {
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  const iniciarMotor = useVozStore((s) => s.iniciarMotor)
  const pararMotor = useVozStore((s) => s.pararMotor)
  const alternarPausa = useVozStore((s) => s.alternarPausa)
  const monitor = useVozStore((s) => s.ajustes.monitor)
  const setMonitor = useVozStore((s) => s.setMonitor)
  const grabando = useVozStore((s) => s.grabando)
  const grabacion = useVozStore((s) => s.grabacion)
  const iniciarGrabacion = useVozStore((s) => s.iniciarGrabacion)
  const terminarGrabacion = useVozStore((s) => s.terminarGrabacion)
  const limpiarGrabacion = useVozStore((s) => s.limpiarGrabacion)

  const activo = estadoMotor === 'activo' || estadoMotor === 'pausado'

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-2.5 sm:gap-3">
        <div className="mr-auto flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 via-orange-600 to-red-800 text-amber-50 shadow-lg shadow-orange-950/50">
            <Flame className="size-5" aria-hidden="true" />
          </div>
          <div>
            {/* Marca compacta: el h1 real vive en el héroe (único h1 de la página). */}
            <p className="font-display text-sm leading-tight font-semibold tracking-wide">
              <span className="sm:hidden">Voz DM</span>
              <span className="hidden sm:inline">Cambiador de Voz DM</span>
            </p>
          </div>
        </div>

        <MedidorNivel />
        <PillEstadoMic />

        {activo ? (
          <>
            <Button
              size="sm"
              variant="secondary"
              onClick={alternarPausa}
              disabled={estadoMotor === 'iniciando'}
              title={estadoMotor === 'pausado' ? 'Reanudar micrófono' : 'Pausar micrófono'}
            >
              {estadoMotor === 'pausado' ? <Play className="size-4" /> : <Pause className="size-4" />}
              <span className="hidden sm:inline">{estadoMotor === 'pausado' ? 'Reanudar' : 'Pausar'}</span>
            </Button>
            <Button size="sm" variant="outline" onClick={pararMotor}>
              <MicOff className="size-4" />
              <span className="hidden sm:inline">Detener</span>
            </Button>
            <Button
              size="sm"
              variant={grabando ? 'destructive' : 'default'}
              onClick={() => (grabando ? terminarGrabacion() : iniciarGrabacion())}
              title={grabando ? 'Terminar y descargar grabación' : 'Grabar audio procesado (post-DSP)'}
              className={grabando ? 'animate-pulse shadow-lg shadow-red-950/60' : ''}
            >
              <Circle className={cn('size-4', grabando && 'fill-current')} />
              <span className="hidden sm:inline">{grabando ? 'Terminar' : 'Grabar'}</span>
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={iniciarMotor} disabled={estadoMotor === 'iniciando'}>
            <Mic className="size-4" />
            {estadoMotor === 'iniciando' ? (
              'Iniciando…'
            ) : (
              <>
                <span className="sm:hidden">Iniciar</span>
                <span className="hidden sm:inline">Iniciar micrófono</span>
              </>
            )}
          </Button>
        )}

        <div className="flex items-center gap-2">
          <Headphones className="size-4 text-muted-foreground" aria-hidden="true" />
          <Label htmlFor="monitor" className="hidden text-xs text-muted-foreground sm:inline">
            Monitor
          </Label>
          <Switch
            id="monitor"
            checked={monitor}
            onCheckedChange={setMonitor}
            aria-label="Activar o silenciar el monitor de la voz"
          />
        </div>

        {grabacion && (
          <Button
            size="sm"
            variant="outline"
            title={`Descargar grabación (${grabacion.extension})`}
            onClick={() => {
              const ancla = document.createElement('a')
              ancla.href = grabacion.url
              ancla.download = `voz_web_${Date.now()}.${grabacion.extension}`
              ancla.click()
              limpiarGrabacion()
            }}
          >
            <Download className="size-4" />
            <span className="hidden sm:inline">Descargar</span>
          </Button>
        )}
      </div>
    </header>
  )
}
