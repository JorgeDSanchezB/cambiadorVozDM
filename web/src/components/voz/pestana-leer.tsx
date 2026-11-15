// Pestaña Leer — espejo de la pestaña de lectura del escritorio (Fase 6):
// texto (o archivo .txt) → síntesis → cadena de la voz activa → reproducción
// SECUENCIAL de fragmentos (nunca superpuestos). Con respaldo del navegador
// si el servidor de voces falla (degradación honesta, sin efectos DSP).

'use client'

import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Download, FileText, Play, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { clasificarError } from '@/lib/errores'
import { motor } from '@/lib/motor-audio'
import {
  VOCES_SERVIDOR,
  detenerLecturaNavegador,
  descargarWavLectura,
  fragmentarTexto,
  leerConNavegador,
  leerConServidor,
  type IdVozServidor,
} from '@/lib/tts'
import { useVozStore } from '@/store/voz'

export function PestanaLeer() {
  const vozActiva = useVozStore((s) => s.voces.find((v) => v.id === s.vozActivaId))
  const setLectura = useVozStore((s) => s.setLectura)

  const [texto, setTexto] = useState('')
  const [vozServidor, setVozServidor] = useState<IdVozServidor>('tongtong')
  const [velocidad, setVelocidad] = useState(1)
  const [motorTts, setMotorTts] = useState<'servidor' | 'navegador'>('servidor')
  const [conEfectos, setConEfectos] = useState(true)
  const [ocupado, setOcupado] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const totalFragmentos = useMemo(() => fragmentarTexto(texto).length, [texto])
  const lectura = useVozStore((s) => s.lectura)

  const cargarArchivo = async (archivo: File) => {
    try {
      const contenido = await archivo.text()
      setTexto(contenido)
      toast.success(`Archivo cargado: ${archivo.name}`, {
        description: `${contenido.length} caracteres, ${fragmentarTexto(contenido).length} fragmentos.`,
      })
    } catch (e) {
      const err = clasificarError(e, 'datos')
      toast.error('No se pudo leer el archivo', { description: err.remedio })
    }
  }

  const reproducir = async () => {
    if (ocupado || !texto.trim()) return
    setOcupado(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLectura({ activa: true, fase: 'sintetizando', fragmento: 0, total: totalFragmentos })

    try {
      if (motorTts === 'servidor') {
        await leerConServidor({
          texto,
          voz: vozServidor,
          velocidad,
          conEfectos,
          senal: ctrl.signal,
          onProgreso: (p) => setLectura({ fase: p.fase, fragmento: p.fragmento, total: p.total }),
        })
      } else {
        if (conEfectos) {
          toast.info('La voz del navegador no pasa por la cadena DSP', {
            description: 'El navegador no permite enrutar speechSynthesis por Web Audio. Es una limitación honesta del respaldo.',
          })
        }
        await leerConNavegador(texto, ctrl.signal)
        setLectura({ fase: 'fin', fragmento: totalFragmentos, total: totalFragmentos })
      }
    } catch (e) {
      const err = clasificarError(e, 'tts')
      if (motorTts === 'servidor' && !ctrl.signal.aborted) {
        toast.warning(`${err.titulo}. Reintentando con la voz del navegador…`, {
          description: 'El respaldo lee sin efectos DSP (limitación del navegador).',
        })
        try {
          await leerConNavegador(texto, ctrl.signal)
          setLectura({ fase: 'fin', fragmento: totalFragmentos, total: totalFragmentos })
        } catch (e2) {
          const err2 = clasificarError(e2, 'tts')
          toast.error(err2.titulo, { description: err2.remedio })
        }
      } else if (!ctrl.signal.aborted) {
        toast.error(err.titulo, { description: err.remedio })
      }
    } finally {
      abortRef.current = null
      setOcupado(false)
      setLectura({ activa: false })
    }
  }

  const detener = () => {
    abortRef.current?.abort()
    motor.detenerLectura()
    detenerLecturaNavegador()
  }

  const descargar = async () => {
    if (ocupado || !texto.trim() || !vozActiva) return
    setOcupado(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLectura({ activa: true, fase: 'sintetizando', fragmento: 0, total: totalFragmentos })
    try {
      await descargarWavLectura({
        texto,
        voz: vozServidor,
        velocidad,
        conEfectos,
        parametros: vozActiva.parametros_dsp,
        senal: ctrl.signal,
        onProgreso: (p) => setLectura({ fase: p.fase, fragmento: p.fragmento, total: p.total }),
      })
      toast.success('WAV descargado', {
        description: 'Render offline con la misma cadena DSP de la voz activa.',
      })
    } catch (e) {
      const err = clasificarError(e, 'tts')
      if (!ctrl.signal.aborted) toast.error(err.titulo, { description: err.remedio })
    } finally {
      abortRef.current = null
      setOcupado(false)
      setLectura({ activa: false })
    }
  }

  const textoFase: Record<string, string> = {
    sintetizando: 'Sintetizando fragmento',
    reproduciendo: 'Reproduciendo fragmento',
    descargando: 'Renderizando WAV con la cadena DSP…',
    fin: 'Listo',
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Texto a leer</CardTitle>
          <CardDescription>
            Escribe o carga un .txt. El texto se divide en fragmentos por oraciones y se lee en orden,
            uno detrás de otro (nunca superpuestos).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Pega aquí la narración de tu partida…"
            rows={7}
            aria-label="Texto a leer"
          />
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="cargar-txt" className="inline-flex">
              <Input
                id="cargar-txt"
                type="file"
                accept=".txt,text/plain"
                className="hidden"
                onChange={(e) => {
                  const archivo = e.target.files?.[0]
                  if (archivo) cargarArchivo(archivo)
                  e.target.value = ''
                }}
              />
              <Button variant="outline" asChild disabled={ocupado}>
                <span role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') (e.currentTarget.previousElementSibling as HTMLElement)?.click() }}>
                  <FileText className="size-4" />
                  Cargar .txt
                </span>
              </Button>
            </label>
            <span className="text-xs text-muted-foreground">
              {texto.length} caracteres · {totalFragmentos} fragmento{totalFragmentos === 1 ? '' : 's'}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Síntesis de voz</CardTitle>
          <CardDescription>
            El servidor produce la voz base y la cadena DSP de la voz activa le da el carácter.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="motor-tts">Motor de síntesis</Label>
              <Select value={motorTts} onValueChange={(v) => setMotorTts(v as 'servidor' | 'navegador')}>
                <SelectTrigger id="motor-tts">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="servidor">Servidor (voz neural, con efectos)</SelectItem>
                  <SelectItem value="navegador">Navegador (offline, sin efectos)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="voz-servidor">Voz del servidor</Label>
              <Select
                value={vozServidor}
                onValueChange={(v) => setVozServidor(v as IdVozServidor)}
                disabled={motorTts !== 'servidor'}
              >
                <SelectTrigger id="voz-servidor">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VOCES_SERVIDOR.map((v) => (
                    <SelectItem key={v.id} value={v.id}>{v.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="velocidad-tts">Velocidad</Label>
              <span className="font-mono text-sm text-muted-foreground">{velocidad.toFixed(1)}×</span>
            </div>
            <Slider
              id="velocidad-tts"
              value={[velocidad]}
              min={0.5}
              max={2}
              step={0.1}
              onValueChange={([v]) => setVelocidad(v)}
            />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="con-efectos">Aplicar la voz activa (cadena DSP)</Label>
              <p className="text-xs text-muted-foreground">
                {vozActiva
                  ? `La lectura sonará con los efectos de: ${vozActiva.nombre}.`
                  : 'Selecciona una voz en la pestaña Voces.'}
              </p>
            </div>
            <Switch
              id="con-efectos"
              checked={conEfectos}
              onCheckedChange={setConEfectos}
              disabled={motorTts !== 'servidor'}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={reproducir} disabled={ocupado || !texto.trim()}>
              <Play className="size-4" />
              Reproducir
            </Button>
            <Button variant="outline" onClick={detener} disabled={!ocupado}>
              <Square className="size-4" />
              Detener
            </Button>
            <Button
              variant="outline"
              onClick={descargar}
              disabled={ocupado || !texto.trim() || motorTts !== 'servidor'}
              title={motorTts !== 'servidor' ? 'La descarga WAV requiere el motor del servidor' : 'Descargar la lectura con la voz aplicada'}
              className="ml-auto"
            >
              <Download className="size-4" />
              Descargar WAV
            </Button>
          </div>

          {(ocupado || lectura.total > 0) && (
            <div className="space-y-1.5">
              <Progress value={lectura.total > 0 ? (lectura.fragmento / lectura.total) * 100 : 0} />
              <p className="text-xs text-muted-foreground" role="status">
                {textoFase[lectura.fase] ?? ''} {lectura.total > 0 ? `${lectura.fragmento}/${lectura.total}` : ''}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
