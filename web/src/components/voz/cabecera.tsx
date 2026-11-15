// Barra superior — espejo de la barra del escritorio: estado del micrófono,
// pausa/reanudar, monitor, medidor de nivel y grabación post-DSP.

'use client'

import { useEffect, useRef } from 'react'
import { Circle, Download, Headphones, Mic, MicOff, Pause, Play, Volume2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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

  return (
    <div
      aria-hidden="true"
      className="hidden h-2 w-24 overflow-hidden rounded-full bg-muted sm:block"
      title="Medidor de nivel (dBFS)"
    >
      <div ref={barra} className="h-full w-0 rounded-full bg-primary" />
    </div>
  )
}

function EstadoMic() {
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  if (estadoMotor === 'detenido') {
    return <Badge variant="outline" className="gap-1.5 text-muted-foreground"><span className="size-1.5 rounded-full bg-muted-foreground/50" />Micrófono detenido</Badge>
  }
  if (estadoMotor === 'iniciando') {
    return <Badge variant="outline" className="gap-1.5"><span className="size-1.5 animate-pulse rounded-full bg-amber-500" />Iniciando…</Badge>
  }
  if (estadoMotor === 'pausado') {
    return <Badge variant="outline" className="gap-1.5"><span className="size-1.5 rounded-full bg-amber-500" />En pausa</Badge>
  }
  return <Badge variant="outline" className="gap-1.5"><span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />Micrófono activo</Badge>
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
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3 sm:gap-3">
        <div className="mr-auto flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Volume2 className="size-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-base leading-tight font-semibold">Cambiador de Voz DM</h1>
            <p className="text-xs text-muted-foreground">Versión web · espejo de voz_dnd</p>
          </div>
        </div>

        <MedidorNivel />
        <EstadoMic />

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
            >
              <Circle className={`size-4 ${grabando ? 'animate-pulse fill-current' : ''}`} />
              <span className="hidden sm:inline">{grabando ? 'Terminar' : 'Grabar'}</span>
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={iniciarMotor} disabled={estadoMotor === 'iniciando'}>
            <Mic className="size-4" />
            {estadoMotor === 'iniciando' ? 'Iniciando…' : 'Iniciar micrófono'}
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
