// Card «Pack de voces» — compartir el elenco (idea de los Model Packs de
// VoiceStudio). La web exporta/importa un JSON con las voces
// personalizadas completas (ids nuevos al importar, duplicados omitidos,
// parámetros acotados). Formato HONESTO distinto del ZIP del escritorio:
// no son compatibles entre sí y la card lo dice.

'use client'

import { useRef, useState } from 'react'
import { Download, Package, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { descargarBlob } from '@/lib/wav'
import { useVozStore } from '@/store/voz'

export function TarjetaPackVoces() {
  const voces = useVozStore((s) => s.voces)
  const importarPackVoces = useVozStore((s) => s.importarPackVoces)
  const [importando, setImportando] = useState(false)
  const entradaRef = useRef<HTMLInputElement>(null)

  const personalizadas = voces.filter((v) => v.personalizada)

  const exportar = () => {
    if (personalizadas.length === 0) {
      toast.info('No hay voces personalizadas que exportar', {
        description: 'Crea voces en el Creador (o con la Forja) y vuelve.',
      })
      return
    }
    const pack = {
      version: 1,
      fuente: 'voz_dnd_web',
      exportado_en: new Date().toISOString(),
      voces: personalizadas,
    }
    const fecha = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' })
    descargarBlob(blob, `pack_voces_web_${fecha}.json`)
    toast.success(`Pack exportado: ${personalizadas.length} voz(es)`, {
      description: 'Comparte el .json con otro DM que use la versión web.',
    })
  }

  const alElegirArchivo = async (archivo: File | undefined) => {
    if (!archivo) return
    setImportando(true)
    try {
      const texto = await archivo.text()
      const crudo: unknown = JSON.parse(texto)
      importarPackVoces(crudo)
    } catch {
      toast.error('El archivo no es un JSON legible', {
        description: 'Comprueba que es un pack exportado desde la versión web.',
      })
    } finally {
      setImportando(false)
      if (entradaRef.current) entradaRef.current.value = ''
    }
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Package className="size-4 text-muted-foreground" aria-hidden="true" />
          Pack de voces
        </CardTitle>
        <CardDescription>
          Comparte tu elenco: exporta tus voces personalizadas a un .json e impórtalo en otro
          navegador. Formato honesto y distinto del ZIP del escritorio (no son compatibles entre
          sí).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={exportar}>
            <Download className="size-4" aria-hidden="true" />
            Exportar ({personalizadas.length})
          </Button>
          <label htmlFor="archivo-pack" className="inline-flex">
            <Input
              ref={entradaRef}
              id="archivo-pack"
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                void alElegirArchivo(e.target.files?.[0])
                e.target.value = ''
              }}
            />
            <Button variant="outline" asChild disabled={importando}>
              <span
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.currentTarget.previousElementSibling as HTMLElement)?.click()
                }}
              >
                <Upload className="size-4" aria-hidden="true" />
                {importando ? 'Leyendo…' : 'Importar pack'}
              </span>
            </Button>
          </label>
        </div>
        <p className="text-xs text-muted-foreground">
          Al importar: los ids se regeneran (jamás se pisan tus voces), las voces con el mismo
          nombre se omiten con aviso y los parámetros se acotan al catálogo.
        </p>
      </CardContent>
    </Card>
  )
}
