// Pestaña Ajustes — dispositivo de entrada, frecuencia objetivo, monitor,
// atajos de teclado (asignación manual), cuenta de FakeYou y gestión de datos
// locales. Persistencia en localStorage con tolerancia a datos corruptos.

'use client'

import { useEffect, useState } from 'react'
import { Eye, RotateCcw, Star, Trash2 } from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { usePersonajesStore } from '@/store/personajes'
import { useVozStore } from '@/store/voz'
import { TarjetaAtajos } from '@/components/voz/tarjeta-atajos'
import { TarjetaPackVoces } from '@/components/voz/tarjeta-pack-voces'

// Cuenta de FakeYou (mudanza desde la antigua pestaña Personajes): el token
// de sesión sube el cupo de generación del elenco. Vive aquí por ser un
// ajuste, no un flujo de lectura.
function TarjetaCuentaFakeYou() {
  const init = usePersonajesStore((s) => s.init)
  const sesion = usePersonajesStore((s) => s.sesionFakeyou)
  const setSesion = usePersonajesStore((s) => s.setSesion)
  const [valor, setValor] = useState('')

  useEffect(() => {
    init()
  }, [init])

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <Star className="size-4 text-primary" aria-hidden="true" />
          Cuenta de FakeYou
          <Badge variant="secondary" className="border border-border/50 bg-secondary/60 font-mono">
            {sesion ? 'Conectada' : 'Anónima'}
          </Badge>
        </CardTitle>
        <CardDescription>
          Las voces de personajes usan FakeYou. Con una cuenta gratuita el cupo es mayor: inicia
          sesión en fakeyou.com, copia el valor de la cookie{' '}
          <code className="rounded bg-muted px-1">session</code> (DevTools ▸ Application ▸ Cookies) y
          pégalo aquí.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {sesion ? (
          <div className="flex items-center justify-between gap-2 rounded-md border p-2.5">
            <span className="flex min-w-0 items-center gap-2">
              <Star className="size-4 shrink-0 fill-amber-400 text-amber-400" aria-hidden="true" />
              <span className="truncate font-mono text-xs">{sesion.slice(0, 14)}…</span>
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setSesion(null)
                setValor('')
              }}
            >
              Desconectar
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Input
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="Pega aquí el token de sesión"
              type="password"
              aria-label="Token de sesión de FakeYou"
            />
            <Button size="sm" disabled={!valor.trim()} onClick={() => setSesion(valor)}>
              Guardar
            </Button>
          </div>
        )}
        <p className="text-[11px] text-muted-foreground">
          El token se guarda solo en este navegador y viaja únicamente al backend de esta app.
        </p>
      </CardContent>
    </Card>
  )
}

export function PestanaAjustes() {
  const ajustes = useVozStore((s) => s.ajustes)
  const dispositivos = useVozStore((s) => s.dispositivosEntrada)
  const voces = useVozStore((s) => s.voces)
  const vocesOcultas = useVozStore((s) => s.vocesOcultas)
  const setDispositivoEntrada = useVozStore((s) => s.setDispositivoEntrada)
  const setSrObjetivo = useVozStore((s) => s.setSrObjetivo)
  const setMonitor = useVozStore((s) => s.setMonitor)
  const setVolumenMonitor = useVozStore((s) => s.setVolumenMonitor)
  const actualizarDispositivos = useVozStore((s) => s.actualizarDispositivos)
  const restaurarVoz = useVozStore((s) => s.restaurarVoz)
  const restaurarVocesOcultas = useVozStore((s) => s.restaurarVocesOcultas)
  const restablecerDatos = useVozStore((s) => s.restablecerDatos)

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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="min-w-0 space-y-2">
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
            <div className="min-w-0 space-y-2">
              <Label htmlFor="sr">Frecuencia de muestreo objetivo</Label>
              <Select
                value={String(ajustes.srObjetivo)}
                onValueChange={(v) => setSrObjetivo(Number(v))}
              >
                <SelectTrigger id="sr" className="w-full">
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

      <TarjetaAtajos />

      <TarjetaPackVoces />

      <TarjetaCuentaFakeYou />

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
    </div>
  )
}
