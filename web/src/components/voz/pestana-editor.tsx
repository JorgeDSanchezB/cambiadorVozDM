// Pestaña Editor — espejo del editor del escritorio: sliders generados desde
// el catálogo de parámetros (data-driven, cero hardcoding), previa de 2 s y
// "guardar como nueva voz" (persiste en este navegador).

'use client'

import { useState } from 'react'
import { Play, RotateCcw, Save } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { motor } from '@/lib/motor-audio'
import { CATALOGO_PARAMETROS, CLAVES_PARAMETROS } from '@/lib/voces'
import type { ClaveParametro, ParametrosDSP } from '@/lib/tipos'
import { useVozStore } from '@/store/voz'

export function PestanaEditor() {
  const vozActivaId = useVozStore((s) => s.vozActivaId)
  // La key remonta el editor al cambiar de voz: el estado local parte de
  // los parámetros de la nueva voz sin efectos ni renders en cascada.
  return <EditorDeVoz key={vozActivaId} />
}

function EditorDeVoz() {
  const voces = useVozStore((s) => s.voces)
  const vozActivaId = useVozStore((s) => s.vozActivaId)
  const estadoMotor = useVozStore((s) => s.estadoMotor)
  const aplicarParametrosEnVivo = useVozStore((s) => s.aplicarParametrosEnVivo)
  const guardarVozPersonalizada = useVozStore((s) => s.guardarVozPersonalizada)

  const voz = voces.find((v) => v.id === vozActivaId)

  const [params, setParams] = useState<ParametrosDSP | null>(voz?.parametros_dsp ?? null)
  const [enVivo, setEnVivo] = useState(true)
  const [dialogoAbierto, setDialogoAbierto] = useState(false)
  const [nombre, setNombre] = useState('')

  if (!voz || !params) {
    return <p className="text-sm text-muted-foreground">Selecciona una voz en la pestaña Voces.</p>
  }

  const actualizar = (clave: ClaveParametro, valor: number) => {
    const def = CATALOGO_PARAMETROS[clave]
    const acotado = Math.min(Math.max(valor, def.min), def.max)
    const nuevos = { ...params, [clave]: acotado }
    setParams(nuevos)
    if (enVivo) aplicarParametrosEnVivo(nuevos)
  }

  const restablecer = () => {
    setParams({ ...voz.parametros_dsp })
    aplicarParametrosEnVivo(voz.parametros_dsp)
    toast.info('Parámetros restablecidos', { description: `Vuelven a los de la voz ${voz.nombre}.` })
  }

  const escucharPrevia = () => {
    if (estadoMotor !== 'activo' && estadoMotor !== 'pausado') {
      toast.info('Inicia el micrófono para escuchar la previa', {
        description: 'La previa reproduce 2 segundos de tu micrófono con estos parámetros.',
      })
      return
    }
    motor.previa(2000)
  }

  const guardar = () => {
    guardarVozPersonalizada(nombre, params)
    setDialogoAbierto(false)
    setNombre('')
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            Editando: <span aria-hidden="true">{voz.icono}</span> {voz.nombre}
            <Switch
              checked={enVivo}
              onCheckedChange={setEnVivo}
              aria-label="Aplicar cambios en vivo"
              className="ml-auto"
            />
            <span className="text-xs font-normal text-muted-foreground">aplicar en vivo</span>
          </CardTitle>
          <CardDescription>
            Los cambios no modifican la voz original: escucha con la previa y guárdalos como voz nueva.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {CLAVES_PARAMETROS.map((clave) => {
            const def = CATALOGO_PARAMETROS[clave]
            const valor = params[clave]
            const texto = def.paso < 1
              ? valor.toFixed(2).replace(/\.?0+$/, '')
              : String(valor)
            return (
              <div key={clave} className="space-y-2">
                <div className="flex items-baseline justify-between gap-2">
                  <Label htmlFor={`slider-${clave}`}>{def.etiqueta}</Label>
                  <span className="font-mono text-sm text-muted-foreground">
                    {texto}{def.unidad ? ` ${def.unidad}` : ''}
                  </span>
                </div>
                <Slider
                  id={`slider-${clave}`}
                  value={[valor]}
                  min={def.min}
                  max={def.max}
                  step={def.paso}
                  onValueChange={([v]) => actualizar(clave, v)}
                />
              </div>
            )
          })}

          <div className="flex flex-wrap gap-2 pt-2">
            <Button variant="outline" onClick={restablecer}>
              <RotateCcw className="size-4" />
              Restablecer
            </Button>
            <Button variant="outline" onClick={escucharPrevia}>
              <Play className="size-4" />
              Escuchar 2 s
            </Button>
            <Button onClick={() => setDialogoAbierto(true)} className="ml-auto">
              <Save className="size-4" />
              Guardar como nueva voz
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogoAbierto} onOpenChange={setDialogoAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Guardar como nueva voz</DialogTitle>
            <DialogDescription>
              Se guarda en este navegador (espejo del "guardar como nueva voz" del escritorio).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="nombre-voz">Nombre de la voz</Label>
            <Input
              id="nombre-voz"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="P. ej. Narrador Tenebroso"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && nombre.trim()) guardar()
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogoAbierto(false)}>
              Cancelar
            </Button>
            <Button onClick={guardar} disabled={!nombre.trim()}>
              Guardar voz
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
