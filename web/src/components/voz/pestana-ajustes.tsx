// Pestaña Ajustes — espejo de config.json: dispositivo de entrada, frecuencia
// objetivo, monitor, atajos y gestión de datos locales. Persistencia en
// localStorage con tolerancia a datos corruptos.

'use client'

import { Eye, RotateCcw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { useVozStore } from '@/store/voz'

export function PestanaAjustes() {
  const ajustes = useVozStore((s) => s.ajustes)
  const dispositivos = useVozStore((s) => s.dispositivosEntrada)
  const voces = useVozStore((s) => s.voces)
  const vocesOcultas = useVozStore((s) => s.vocesOcultas)
  const setDispositivoEntrada = useVozStore((s) => s.setDispositivoEntrada)
  const setSrObjetivo = useVozStore((s) => s.setSrObjetivo)
  const setMonitor = useVozStore((s) => s.setMonitor)
  const setVolumenMonitor = useVozStore((s) => s.setVolumenMonitor)
  const setAtajos = useVozStore((s) => s.setAtajos)
  const actualizarDispositivos = useVozStore((s) => s.actualizarDispositivos)
  const restaurarVoz = useVozStore((s) => s.restaurarVoz)
  const restaurarVocesOcultas = useVozStore((s) => s.restaurarVocesOcultas)
  const restablecerDatos = useVozStore((s) => s.restablecerDatos)

  const conAtajo = voces.filter((v) => v.atajo)
  const personales = voces.filter((v) => v.personalizada)

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Audio</CardTitle>
          <CardDescription>
            Dispositivo y frecuencia para el micrófono (se aplican al iniciar; el cambio de frecuencia
            exige reiniciarlo).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="dispositivo">Micrófono de entrada</Label>
              <div className="flex gap-2">
                <Select
                  value={ajustes.dispositivoEntrada ?? 'predeterminado'}
                  onValueChange={(v) => setDispositivoEntrada(v === 'predeterminado' ? null : v)}
                >
                  <SelectTrigger id="dispositivo" className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="predeterminado">Predeterminado del sistema</SelectItem>
                    {dispositivos.map((d) => (
                      <SelectItem key={d.deviceId} value={d.deviceId}>
                        {d.label || `Dispositivo ${d.deviceId.slice(0, 8)}…`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Actualizar lista de dispositivos"
                  onClick={async () => {
                    await actualizarDispositivos()
                    toast.info(`${dispositivos.length} dispositivo(s) de entrada detectados`)
                  }}
                >
                  <RotateCcw className="size-4" />
                </Button>
              </div>
              {dispositivos.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Los nombres aparecen tras conceder permiso de micrófono.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="sr">Frecuencia de muestreo objetivo</Label>
              <Select
                value={String(ajustes.srObjetivo)}
                onValueChange={(v) => setSrObjetivo(Number(v))}
              >
                <SelectTrigger id="sr">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="48000">48 000 Hz (recomendado, espejo del escritorio)</SelectItem>
                  <SelectItem value="44100">44 100 Hz</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Separator />

          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="monitor-ajustes">Monitor de la voz</Label>
              <p className="text-xs text-muted-foreground">
                Escucha tu voz procesada en directo. Usa auriculares para evitar acoples.
              </p>
            </div>
            <Switch
              id="monitor-ajustes"
              checked={ajustes.monitor}
              onCheckedChange={setMonitor}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="volumen">Volumen del monitor</Label>
              <span className="font-mono text-sm text-muted-foreground">
                {Math.round(ajustes.volumenMonitor * 100)}%
              </span>
            </div>
            <Slider
              id="volumen"
              value={[ajustes.volumenMonitor]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={([v]) => setVolumenMonitor(v)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Atajos de teclado</CardTitle>
          <CardDescription>
            Espejo del mapa del escritorio: la asignación vive en el dato de cada voz.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="atajos-activos">Activar atajos F1–F12</Label>
              <p className="text-xs text-muted-foreground">
                Se ignoran mientras escribes en un campo de texto.
              </p>
            </div>
            <Switch id="atajos-activos" checked={ajustes.atajos} onCheckedChange={setAtajos} />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {conAtajo.map((v) => (
              <Badge key={`${v.id}-${v.atajo}`} variant="outline" className="gap-1 font-normal">
                <span className="font-mono">{v.atajo}</span>
                {v.nombre}
              </Badge>
            ))}
            {conAtajo.length === 0 && (
              <span className="text-sm text-muted-foreground">Ninguna voz tiene atajo asignado.</span>
            )}
          </div>
        </CardContent>
      </Card>

      {vocesOcultas.length > 0 && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center justify-between gap-2 text-base">
              <span>Voces ocultas ({vocesOcultas.length})</span>
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5"
                onClick={restaurarVocesOcultas}
              >
                <Eye className="size-3.5" aria-hidden="true" />
                Restaurar todas
              </Button>
            </CardTitle>
            <CardDescription>
              Voces del catálogo que quitaste de tu lista. Se restauran aquí: la lista y el catálogo
              generado nunca se tocan. La voz Neutral no se puede ocultar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="rol-custom max-h-64 space-y-1.5 overflow-y-auto pr-1">
              {vocesOcultas.map((voz) => (
                <li
                  key={voz.id}
                  className="flex items-center gap-3 rounded-md border px-3 py-2"
                >
                  <span
                    aria-hidden="true"
                    className="w-1.5 self-stretch rounded-full"
                    style={{ backgroundColor: voz.color }}
                  />
                  <span aria-hidden="true" className="text-lg leading-none select-none">
                    {voz.icono}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm">{voz.nombre}</span>
                  {voz.atajo && (
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {voz.atajo}
                    </Badge>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 gap-1.5"
                    onClick={() => restaurarVoz(voz.id)}
                    aria-label={`Restaurar la voz ${voz.nombre}`}
                  >
                    <Eye className="size-4" aria-hidden="true" />
                    Restaurar
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Datos locales</CardTitle>
          <CardDescription>
            Voces personalizadas y ajustes se guardan en este navegador (localStorage). No se envía
            nada a ningún servidor salvo el texto de las lecturas al servicio de síntesis.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Voces personalizadas guardadas: <strong>{personales.length}</strong>
            {vocesOcultas.length > 0 && (
              <>
                {' '}· Voces del catálogo ocultas: <strong>{vocesOcultas.length}</strong>
              </>
            )}
          </p>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                <Trash2 className="size-4" />
                Restablecer datos locales
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>¿Restablecer todos los datos locales?</AlertDialogTitle>
                <AlertDialogDescription>
                  Se eliminan las {personales.length} voz(es) personalizada(s), se restauran las
                  {vocesOcultas.length > 0 ? ` ${vocesOcultas.length} oculta(s)` : ' voces ocultas'} y
                  los ajustes vuelven a los valores base. El catálogo de la app no se toca.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction onClick={restablecerDatos}>Restablecer</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Sobre esta versión</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Versión web del cambiador de voz para DM de D&D: espejo funcional de la app de escritorio
            (rama <span className="font-mono text-xs">main</span> · voz_dnd) mantenida en la rama{' '}
            <span className="font-mono text-xs">feat/web-app</span>. Todo cambio se refleja en ambas ramas.
          </p>
          <p>
            Diferencias honestas: la grabación se descarga en formato del navegador (WebM/Opus, MP4 en
            Safari) en vez de MP3; el modo IA (RVC) no está disponible en web y la voz IA Demo degrada a
            su cadena DSP post, igual que el escritorio sin GPU; la síntesis usa el servicio del servidor
            con respaldo en la voz del navegador. Gestión de voces: el escritorio elimina la voz de
            data/voces/ (permanente, desde el Editor); la web, al no poder tocar el catálogo generado,
            quita la voz de tu lista y la puedes restaurar aquí en cualquier momento.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
