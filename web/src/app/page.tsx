// La Forja de Voces — versión web del cambiador de voz del DM. Pestañas:
// Voces (cambiador en vivo), Leer (TTS + elenco de personajes FakeYou),
// Creador (estudio DSP) y Ajustes.

'use client'

import { useEffect, useState } from 'react'
import { MotionConfig, motion } from 'framer-motion'
import {
  BookOpen,
  MicVocal,
  Settings2,
  SlidersHorizontal,
  type LucideIcon,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAtajosVoces } from '@/hooks/use-atajos'
import { useVozStore } from '@/store/voz'
import { AvisosDegradacion } from '@/components/voz/avisos'
import { Cabecera } from '@/components/voz/cabecera'
import { FondoEscena } from '@/components/voz/fondo-escena'
import { Heroe } from '@/components/voz/heroe'
import { PestanaAjustes } from '@/components/voz/pestana-ajustes'
import { PestanaEditor } from '@/components/voz/pestana-editor'
import { PestanaLeer } from '@/components/voz/pestana-leer'
import { PestanaVoces } from '@/components/voz/pestana-voces'
import { PiePagina } from '@/components/voz/pie-pagina'

const PESTANAS: ReadonlyArray<{ valor: string; icono: LucideIcon; etiqueta: string }> = [
  { valor: 'voces', icono: MicVocal, etiqueta: 'Voces' },
  { valor: 'leer', icono: BookOpen, etiqueta: 'Leer' },
  { valor: 'creador', icono: SlidersHorizontal, etiqueta: 'Creador' },
  { valor: 'ajustes', icono: Settings2, etiqueta: 'Ajustes' },
]

export default function PaginaInicio() {
  const init = useVozStore((s) => s.init)
  const [pestana, setPestana] = useState('voces')

  useEffect(() => {
    init()
  }, [init])
  useAtajosVoces()

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col">
        <FondoEscena />
        <Cabecera />
        <Heroe irA={setPestana} />
        <AvisosDegradacion />
        <main id="panel" className="mx-auto w-full max-w-6xl flex-1 scroll-mt-24 px-4 py-8">
        <Tabs value={pestana} onValueChange={setPestana}>
          <TabsList
            aria-label="Secciones de la consola"
            className="grid h-auto w-full grid-cols-2 gap-1 rounded-xl border border-border/60 bg-card/40 p-1 backdrop-blur sm:grid-cols-4"
          >
            {PESTANAS.map(({ valor, icono: Icono, etiqueta }) => (
              <TabsTrigger
                key={valor}
                value={valor}
                className="relative gap-1.5 rounded-lg px-2 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none sm:text-sm"
              >
                {pestana === valor && (
                  <motion.span
                    layoutId="indicador-panel"
                    transition={{ type: 'spring', stiffness: 400, damping: 34 }}
                    className="absolute inset-0 -z-10 rounded-lg border border-primary/35 bg-gradient-to-b from-primary/15 to-primary/5 shadow-[0_0_20px_-6px] shadow-primary/40"
                  />
                )}
                <Icono className="size-4 shrink-0" aria-hidden="true" />
                {etiqueta}
              </TabsTrigger>
            ))}
          </TabsList>

          <motion.div
            key={pestana}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="mt-6"
          >
            <TabsContent value="voces" className="mt-0">
              <PestanaVoces />
            </TabsContent>
            <TabsContent value="leer" className="mt-0">
              <PestanaLeer />
            </TabsContent>
            <TabsContent value="creador" className="mt-0">
              <PestanaEditor />
            </TabsContent>
            <TabsContent value="ajustes" className="mt-0">
              <PestanaAjustes />
            </TabsContent>
          </motion.div>
        </Tabs>
        </main>
        <PiePagina />
      </div>
    </MotionConfig>
  )
}
