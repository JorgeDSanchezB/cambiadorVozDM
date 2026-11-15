// Cambiador de Voz DM — versión web (rama feat/web-app, espejo de voz_dnd).
// Pestañas: Voces (cambiador en vivo), Editor, Leer (TTS) y Ajustes.

'use client'

import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { BookOpen, MicVocal, Settings2, SlidersHorizontal } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAtajosVoces } from '@/hooks/use-atajos'
import { useVozStore } from '@/store/voz'
import { AvisosDegradacion } from '@/components/voz/avisos'
import { Cabecera } from '@/components/voz/cabecera'
import { PestanaAjustes } from '@/components/voz/pestana-ajustes'
import { PestanaEditor } from '@/components/voz/pestana-editor'
import { PestanaLeer } from '@/components/voz/pestana-leer'
import { PestanaVoces } from '@/components/voz/pestana-voces'
import { PiePagina } from '@/components/voz/pie-pagina'

export default function PaginaInicio() {
  const init = useVozStore((s) => s.init)
  useEffect(() => {
    init()
  }, [init])
  useAtajosVoces()

  return (
    <div className="flex min-h-screen flex-col">
      <Cabecera />
      <AvisosDegradacion />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Tabs defaultValue="voces">
          <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:grid-cols-4">
            <TabsTrigger value="voces" className="gap-1.5">
              <MicVocal className="size-4" />
              Voces
            </TabsTrigger>
            <TabsTrigger value="editor" className="gap-1.5">
              <SlidersHorizontal className="size-4" />
              Editor
            </TabsTrigger>
            <TabsTrigger value="leer" className="gap-1.5">
              <BookOpen className="size-4" />
              Leer
            </TabsTrigger>
            <TabsTrigger value="ajustes" className="gap-1.5">
              <Settings2 className="size-4" />
              Ajustes
            </TabsTrigger>
          </TabsList>

          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="mt-4"
          >
            <TabsContent value="voces" className="mt-0">
              <PestanaVoces />
            </TabsContent>
            <TabsContent value="editor" className="mt-0">
              <PestanaEditor />
            </TabsContent>
            <TabsContent value="leer" className="mt-0">
              <PestanaLeer />
            </TabsContent>
            <TabsContent value="ajustes" className="mt-0">
              <PestanaAjustes />
            </TabsContent>
          </motion.div>
        </Tabs>
      </main>
      <PiePagina />
    </div>
  )
}
