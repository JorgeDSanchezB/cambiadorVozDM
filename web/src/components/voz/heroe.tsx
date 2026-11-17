// Héroe — carta de presentación de la consola: marca, propuesta y el
// «monitor de forja» con la voz activa y su ecualizador. Los botones llevan
// a las pestañas (el estado lo controla la página).

'use client'

import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { Drama, Flame, Keyboard, Mic, MicVocal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePersonajesStore } from '@/store/personajes'
import { useVozStore } from '@/store/voz'
import { Ecualizador } from './ecualizador'

interface Props {
  irA: (pestana: string) => void
}

function PillEstadoForja() {
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  const config = {
    detenido: { texto: 'Forja en reposo', punto: 'bg-muted-foreground/40' },
    iniciando: { texto: 'Encendiendo…', punto: 'bg-amber-400 animate-pulse' },
    pausado: { texto: 'En pausa', punto: 'bg-amber-400' },
    activo: { texto: 'En directo', punto: 'bg-emerald-400 animate-pulse' },
  }[estadoMotor]
  // En reposo no se pinta: la barra superior ya indica el estado y el pie
  // de la tarjeta explica cómo encender. Sin duplicar píldoras.
  if (estadoMotor === 'detenido') return null
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-card/60 px-2.5 py-1 text-[11px] text-muted-foreground">
      <span className={cn('size-1.5 rounded-full', config.punto)} aria-hidden="true" />
      {config.texto}
    </span>
  )
}

export function Heroe({ irA }: Props) {
  const voces = useVozStore((s) => s.voces)
  const vozActiva = useVozStore((s) => s.voces.find((v) => v.id === s.vozActivaId))
  const estadoMotor = useVozStore((s) => s.estadoMotor)

  const totalPersonajes = usePersonajesStore((s) => s.total)
  const initPersonajes = usePersonajesStore((s) => s.init)
  const cargarCatalogo = usePersonajesStore((s) => s.cargarCatalogo)

  useEffect(() => {
    initPersonajes()
    if (usePersonajesStore.getState().voces.length === 0) void cargarCatalogo()
  }, [initPersonajes, cargarCatalogo])

  const micActivo = estadoMotor === 'activo'

  const irConScroll = (pestana: string) => {
    irA(pestana)
    const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document.getElementById('panel')?.scrollIntoView({
      behavior: reducido ? 'auto' : 'smooth',
      block: 'start',
    })
  }

  return (
    <section className="relative isolate overflow-hidden">
      <div className="relative mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-12 sm:py-16 lg:grid-cols-[1.15fr_0.85fr] lg:py-20">
        {/* Marca de agua: la palabra de la casa, gigante y hueca, detrás del
            contenido y desvanecida hacia el borde para que el corte sea
            intencional (máscara de degradado), no un recorte accidental. */}
        <span
          aria-hidden="true"
          className="font-display pointer-events-none absolute top-2 -right-8 -z-10 hidden text-[10rem] leading-none font-bold tracking-[0.08em] text-transparent select-none lg:block"
          style={{
            WebkitTextStroke: '1.5px oklch(0.76 0.16 72 / 0.2)',
            maskImage: 'linear-gradient(to right, black 20%, transparent 72%)',
            WebkitMaskImage: 'linear-gradient(to right, black 20%, transparent 72%)',
          }}
        >
          FORJA
        </span>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: 'easeOut' }}
        >
          <Badge
            variant="outline"
            className="gap-1.5 rounded-full border-primary/35 bg-primary/10 px-3 py-1 text-[11px] font-medium tracking-[0.2em] text-primary uppercase"
          >
            <Flame className="size-3" aria-hidden="true" />
            Consola del Dungeon Master
          </Badge>
          <h1 className="mt-5 font-display text-4xl leading-[1.1] text-foreground sm:text-5xl lg:text-[3.4rem]">
            Cambiador de voz
            <br />
            <span className="bg-gradient-to-br from-amber-200 via-amber-400 to-orange-600 bg-clip-text text-transparent">
              para tu mesa
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">
            {voces.length} voces forjadas para improvisar en vivo, un editor DSP milimétrico y un
            elenco latino de personajes —del narrador de Dragon Ball a El Chavo— para dar voz a
            tus PNJs sin perder el hilo de la partida.
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-2.5">
            <Button size="lg" onClick={() => irConScroll('voces')} className="gap-2">
              <MicVocal className="size-4" aria-hidden="true" />
              Explorar voces
            </Button>
            <Button size="lg" variant="outline" onClick={() => irConScroll('leer')} className="gap-2">
              <Drama className="size-4" aria-hidden="true" />
              Elenco de personajes
            </Button>
          </div>

          <dl className="mt-9 grid grid-cols-2 gap-x-6 gap-y-3 sm:flex sm:flex-wrap sm:gap-x-8">
            <div className="flex items-center gap-2 text-sm">
              <Mic className="size-4 text-primary/80" aria-hidden="true" />
              <dt className="sr-only">Voces DSP</dt>
              <dd className="text-muted-foreground">
                <strong className="font-semibold text-foreground">{voces.length}</strong> voces DSP
              </dd>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Drama className="size-4 text-primary/80" aria-hidden="true" />
              <dt className="sr-only">Personajes</dt>
              <dd className="text-muted-foreground">
                <strong className="font-semibold text-foreground">
                  {totalPersonajes > 0 ? totalPersonajes : '···'}
                </strong>{' '}
                personajes<span className="hidden sm:inline"> latinos</span>
              </dd>
            </div>
            <div className="col-span-2 flex items-center gap-2 text-sm sm:col-span-1">
              <Keyboard className="size-4 text-primary/80" aria-hidden="true" />
              <dt className="sr-only">Atajos</dt>
              <dd className="text-muted-foreground">
                atajos <strong className="font-semibold text-foreground">F1–F12</strong> listos
              </dd>
            </div>
          </dl>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.15, ease: 'easeOut' }}
          className="relative"
        >
          <div
            aria-hidden="true"
            className="absolute -inset-8 -z-10 rounded-[2.5rem] bg-[radial-gradient(circle_at_60%_40%,oklch(0.6_0.14_65/0.14),transparent_70%)] blur-2xl"
          />
          <div className="rounded-2xl border border-border/70 bg-card/70 p-5 shadow-2xl shadow-black/40 backdrop-blur-md sm:p-6">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-medium tracking-[0.2em] text-muted-foreground uppercase">
                Voz en uso
              </span>
              <PillEstadoForja />
            </div>

            <div className="mt-4 flex items-center gap-3.5">
              {vozActiva ? (
                <>
                  <span
                    aria-hidden="true"
                    className="flex size-14 shrink-0 items-center justify-center rounded-2xl text-2xl leading-none select-none"
                    style={{
                      backgroundColor: `${vozActiva.color}22`,
                      boxShadow: `inset 0 0 0 1px ${vozActiva.color}44, 0 8px 24px -12px ${vozActiva.color}`,
                    }}
                  >
                    {vozActiva.icono}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-display text-xl font-semibold text-foreground">
                      {vozActiva.nombre}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {vozActiva.parametros_dsp.pitch_semitonos > 0
                        ? 'Tono agudo · '
                        : vozActiva.parametros_dsp.pitch_semitonos < 0
                          ? 'Tono grave · '
                          : 'Tono natural · '}
                      cadena DSP en vivo
                    </p>
                  </div>
                  {vozActiva.atajo && (
                    <kbd className="ml-auto hidden shrink-0 rounded-md border border-border/70 bg-muted/60 px-2 py-1 font-mono text-[11px] text-muted-foreground sm:block">
                      {vozActiva.atajo}
                    </kbd>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Cargando el catálogo de voces…
                </p>
              )}
            </div>

            <Ecualizador activa={micActivo} className="mt-7 h-14" />

            <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
              {micActivo
                ? 'Habla: cada voz cambia tu timbre en tiempo real mientras la barra cobra vida.'
                : 'Enciende el micrófono en la barra de arriba y la forja se enciende contigo.'}
            </p>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
