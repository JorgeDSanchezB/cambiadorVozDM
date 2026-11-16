// Tarjeta «Atajos de teclado» de Ajustes — asignación MANUAL. Cada voz muestra
// su tecla actual (la del catálogo es solo una sugerencia inicial); al pulsarla
// la app entra en modo captura: la próxima F1–F12 (con o sin Shift) queda
// asignada a esa voz. Esc cancela, Borrar quita el atajo. Si la tecla estaba en
// otra voz, pasa a la nueva y la antigua queda libre (con aviso). Todo persiste
// en este navegador. Las voces que el usuario cree aparecen aquí solas, listas
// para asignar; el mapa completo tiene 24 teclas (F1–F12 y Shift+F1–F12).

'use client'

import { useEffect } from 'react'
import { Keyboard, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { normalizarAtajo } from '@/lib/voces'
import { useVozStore } from '@/store/voz'

// Mapa completo de teclas: F1–F12 más sus variantes con Shift.
const TECLAS_TOTALES = 24

export function TarjetaAtajos() {
  const voces = useVozStore((s) => s.voces)
  const vocesOcultas = useVozStore((s) => s.vocesOcultas)
  const atajosGuardados = useVozStore((s) => s.atajosGuardados)
  const capturandoId = useVozStore((s) => s.capturandoAtajoId)
  const atajosActivos = useVozStore((s) => s.ajustes.atajos)
  const setAtajos = useVozStore((s) => s.setAtajos)
  const iniciarCapturaAtajo = useVozStore((s) => s.iniciarCapturaAtajo)
  const asignarAtajo = useVozStore((s) => s.asignarAtajo)
  const restaurarAtajosSugeridos = useVozStore((s) => s.restaurarAtajosSugeridos)

  const hayCambios =
    Object.keys(atajosGuardados).length > 0 || voces.some((v) => v.personalizada && v.atajo)

  // Capacidad: las teclas son de propiedad exclusiva y también cuentan las de
  // las voces ocultas (las conservan para cuando se restauren).
  const teclasUsadas = new Set(
    [...voces, ...vocesOcultas].map((v) => v.atajo).filter((t): t is string => Boolean(t)),
  )
  const teclasLibres = TECLAS_TOTALES - teclasUsadas.size

  // Captura de tecla: mientras una voz espera, esta ventana escucha en fase de
  // captura (antes que la navegación por teclado del navegador) y el gancho
  // global de atajos queda silenciado vía capturandoAtajoId.
  useEffect(() => {
    if (!capturandoId) return

    const alCapturar = (e: KeyboardEvent) => {
      if (e.repeat) return
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        iniciarCapturaAtajo(null)
        return
      }
      if (e.key === 'Backspace' || e.key === 'Delete') {
        asignarAtajo(capturandoId, null)
        return
      }
      const combo = normalizarAtajo(e.key, e.shiftKey)
      if (combo) asignarAtajo(capturandoId, combo)
      // Otras teclas (letras, Enter…) se ignoran: la pista debajo lo explica.
    }

    // Clic fuera del chip en captura → cancelar.
    const alPulsarAfuera = (e: PointerEvent) => {
      const el = e.target as HTMLElement | null
      if (!el?.closest('[data-captura-atajo]')) iniciarCapturaAtajo(null)
    }

    window.addEventListener('keydown', alCapturar, true)
    window.addEventListener('pointerdown', alPulsarAfuera, true)
    return () => {
      window.removeEventListener('keydown', alCapturar, true)
      window.removeEventListener('pointerdown', alPulsarAfuera, true)
    }
  }, [capturandoId, asignarAtajo, iniciarCapturaAtajo])

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Keyboard className="size-4 text-primary" aria-hidden="true" />
          Atajos de teclado
        </CardTitle>
        <CardDescription>
          Toca el atajo de una voz y pulsa la tecla que quieras darle (F1–F12, con o sin Shift). La
          asignación que trae cada voz de fábrica es solo una sugerencia inicial: cámbiala todas las
          veces que quieras. Las voces que crees en el Creador aparecen aquí solas, listas para
          asignar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <Label htmlFor="atajos-activos">Activar atajos</Label>
            <p className="text-xs text-muted-foreground">
              Se ignoran mientras escribes en un campo de texto.
            </p>
          </div>
          <Switch id="atajos-activos" checked={atajosActivos} onCheckedChange={setAtajos} />
        </div>

        <p className="text-xs text-muted-foreground" aria-live="polite">
          {teclasLibres > 0 ? (
            <>
              <strong className="font-mono text-foreground">{teclasLibres}</strong>{' '}
              de {TECLAS_TOTALES} teclas libres · F1–F12 y Shift+F1–F12
            </>
          ) : (
            <>
              Mapa completo ({TECLAS_TOTALES} teclas ocupadas): para dar una tecla a otra voz, primero
              quítasela a la que la tenga.
            </>
          )}
        </p>

        <ul
          className="rol-custom max-h-80 space-y-1.5 overflow-y-auto pr-1"
          aria-label="Asignación de atajos por voz"
        >
          {voces.map((v) => {
            const enCaptura = v.id === capturandoId
            return (
              <li key={v.id} className="flex items-center gap-3 rounded-md border px-3 py-2">
                <span
                  aria-hidden="true"
                  className="w-1.5 self-stretch rounded-full"
                  style={{ backgroundColor: v.color }}
                />
                <span aria-hidden="true" className="text-lg leading-none select-none">
                  {v.icono}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">{v.nombre}</span>
                {enCaptura ? (
                  <kbd
                    data-captura-atajo
                    className="animate-pulse rounded-md border border-primary/50 bg-primary/10 px-3 py-1.5 font-mono text-xs text-primary"
                  >
                    Pulsa una tecla…
                  </kbd>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className={`h-8 min-w-24 justify-center font-mono text-xs tabular-nums ${
                      v.atajo ? '' : 'border-dashed text-muted-foreground'
                    }`}
                    onClick={() => iniciarCapturaAtajo(v.id)}
                    aria-label={`Asignar tecla a la voz ${v.nombre}${
                      v.atajo ? ` (actual: ${v.atajo})` : ' (sin atajo)'
                    }`}
                  >
                    {v.atajo ?? 'Sin atajo'}
                  </Button>
                )}
              </li>
            )
          })}
        </ul>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p aria-live="polite" className="min-w-0 flex-1 text-xs text-muted-foreground">
            {capturandoId
              ? 'Pulsa F1–F12 (con o sin Shift) · Esc cancela · Borrar quita el atajo'
              : 'Los cambios se guardan en este navegador. Si una tecla ya estaba en otra voz, cambia de dueña.'}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            disabled={!hayCambios || capturandoId !== null}
            onClick={restaurarAtajosSugeridos}
          >
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Restaurar sugerencia inicial
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
