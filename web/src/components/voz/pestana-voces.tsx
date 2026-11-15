// Pestaña Voces — selector con búsqueda (espejo de la vista de botones del
// escritorio). El grid se alimenta del catálogo generado; lista larga con
// scroll propio.

'use client'

import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Search, SlidersHorizontal } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { clasificarError } from '@/lib/errores'
import { resumenParametros } from '@/lib/voces'
import { probarVoz } from '@/lib/tts'
import type { Voz } from '@/lib/tipos'
import { useVozStore } from '@/store/voz'
import { TarjetaVoz } from './tarjeta-voz'

export function PestanaVoces() {
  const voces = useVozStore((s) => s.voces)
  const vozActivaId = useVozStore((s) => s.vozActivaId)
  const seleccionarVoz = useVozStore((s) => s.seleccionarVoz)
  const borrarVozPersonalizada = useVozStore((s) => s.borrarVozPersonalizada)

  const [busqueda, setBusqueda] = useState('')
  const [probandoId, setProbandoId] = useState<string | null>(null)

  const filtradas = useMemo(() => {
    const normalizar = (s: string) =>
      s.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '')
    const q = normalizar(busqueda.trim())
    if (!q) return voces
    return voces.filter((v) => normalizar(v.nombre).includes(q))
  }, [voces, busqueda])

  const activa = voces.find((v) => v.id === vozActivaId)

  const probar = async (voz: Voz) => {
    if (probandoId) return
    setProbandoId(voz.id)
    try {
      await probarVoz(voz.parametros_dsp)
    } catch (e) {
      const err = clasificarError(e, 'tts')
      toast.error(`No se pudo probar la voz (${err.titulo})`, { description: err.remedio })
    } finally {
      setProbandoId(null)
    }
  }

  return (
    <div className="space-y-4">
      {activa && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <span aria-hidden="true" className="text-xl">{activa.icono}</span>
              Voz activa: {activa.nombre}
              {activa.atajo && <Badge variant="outline">{activa.atajo}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              {resumenParametros(activa.parametros_dsp).map((chip) => (
                <Badge key={chip.etiqueta} variant="secondary" className="font-normal">
                  {chip.etiqueta}: {chip.texto}
                </Badge>
              ))}
              {resumenParametros(activa.parametros_dsp).length === 0 && (
                <span className="text-sm text-muted-foreground">
                  Cadena neutra: la voz pasa sin efectos (paso directo).
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Ajusta los parámetros en la pestaña Editor o selecciona otra voz para cambiar en vivo.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-52">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar voz por nombre…"
            className="pl-8"
            aria-label="Buscar voz por nombre"
          />
        </div>
        <Badge variant="outline" className="gap-1">
          <SlidersHorizontal className="size-3" aria-hidden="true" />
          {filtradas.length} de {voces.length}
        </Badge>
      </div>

      <div className="rol-custom max-h-[32rem] overflow-y-auto pr-1">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtradas.map((voz) => (
            <TarjetaVoz
              key={voz.id}
              voz={voz}
              activa={voz.id === vozActivaId}
              probando={probandoId === voz.id}
              onSeleccionar={() => seleccionarVoz(voz.id)}
              onProbar={() => probar(voz)}
              onBorrar={voz.personalizada ? () => borrarVozPersonalizada(voz.id) : undefined}
            />
          ))}
        </div>
        {filtradas.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna voz coincide con la búsqueda.
          </p>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        El botón de reproducción de cada tarjeta sintetiza una frase corta con los efectos de esa voz
        (requiere conexión; el micrófono no es necesario). Atajos F1–F12 y Shift+F1–F6 según el catálogo.
      </p>
    </div>
  )
}
