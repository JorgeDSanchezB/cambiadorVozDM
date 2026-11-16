// Pestaña Leer — texto (o archivo .txt) → síntesis → reproducción SECUENCIAL
// de fragmentos (nunca superpuestos).
//
// Modelo mental único (arreglo de la confusión reportada): UNA decisión
// «¿Quién lee?». En ella conviven:
//   - Narradores integrados (mujer / hombre forjado con DSP) y las voces del
//     catálogo propio → motor del servidor + cadena DSP opcional.
//   - El elenco de personajes (FakeYou) → al elegir uno, el motor pasa a ser
//     FakeYou (cola del servidor, sin DSP ni velocidad) y comparte el mismo
//     texto, progreso, reproductor e historial.
//
// Respaldo del navegador si el servidor de voces falla (degradación honesta,
// sin efectos DSP).

'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle,
  Check,
  ChevronsUpDown,
  Download,
  FileText,
  History,
  Loader2,
  Play,
  Square,
  Star,
  Trash2,
} from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Textarea } from '@/components/ui/textarea'
import { clasificarError } from '@/lib/errores'
import { motor } from '@/lib/motor-audio'
import {
  PRESET_NARRADOR_HOMBRE,
  detenerLecturaNavegador,
  descargarWavLectura,
  fragmentarTexto,
  leerConNavegador,
  leerConServidor,
} from '@/lib/tts'
import type { ParametrosDSP } from '@/lib/tipos'
import { usePersonajesStore, type VozPersonaje } from '@/store/personajes'
import { useVozStore } from '@/store/voz'
import { TarjetaColaEscenas } from '@/components/voz/tarjeta-cola-escenas'
import { TarjetaNotasSesion } from '@/components/voz/tarjeta-notas-sesion'

const MAX_TEXTO_FAKEYOU = 500

function quitarAcentos(s: string): string {
  return s.normalize('NFD').replace(/\p{Diacritic}/gu, '')
}

function slug(nombre: string): string {
  return quitarAcentos(nombre)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40)
}

function fechaCorta(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('es', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export type ElegidaLectura =
  | { tipo: 'servidor'; nombre: string; parametros?: ParametrosDSP }
  | { tipo: 'fakeyou'; voz: VozPersonaje }

export function PestanaLeer() {
  const voces = useVozStore((s) => s.voces)
  const vozActivaId = useVozStore((s) => s.vozActivaId)
  const vozActiva = useVozStore((s) => s.voces.find((v) => v.id === s.vozActivaId))
  const setLectura = useVozStore((s) => s.setLectura)
  const lectura = useVozStore((s) => s.lectura)

  // Elenco (FakeYou): catálogo, favoritos, generación e historial. La
  // selección vive aquí («¿Quién lee?») y se sincroniza con el store para
  // que la cola de generación sepa a quién pedirle la voz.
  const initPersonajes = usePersonajesStore((s) => s.init)
  const vocesPersonajes = usePersonajesStore((s) => s.voces)
  const cargandoCatalogo = usePersonajesStore((s) => s.cargandoCatalogo)
  const errorCatalogo = usePersonajesStore((s) => s.errorCatalogo)
  const cargarCatalogo = usePersonajesStore((s) => s.cargarCatalogo)
  const cargarFavoritos = usePersonajesStore((s) => s.cargarFavoritos)
  const cargarHistorial = usePersonajesStore((s) => s.cargarHistorial)
  const favoritas = usePersonajesStore((s) => s.favoritas)
  const alternarFavorito = usePersonajesStore((s) => s.alternarFavorito)
  const seleccionarVoz = usePersonajesStore((s) => s.seleccionarVoz)
  const generacion = usePersonajesStore((s) => s.generacion)
  const generar = usePersonajesStore((s) => s.generar)
  const cancelarGeneracion = usePersonajesStore((s) => s.cancelarGeneracion)
  const audioId = usePersonajesStore((s) => s.audioId)
  const setAudioId = usePersonajesStore((s) => s.setAudioId)
  const historial = usePersonajesStore((s) => s.historial)
  const borrarHistorial = usePersonajesStore((s) => s.borrarHistorial)

  const [texto, setTexto] = useState('')
  // 'mujer' (por defecto), 'hombre' y 'activa' son los valores integrados;
  // un id de voz = esa voz del catálogo propio; «fy:token» = elenco FakeYou.
  const [quienLee, setQuienLee] = useState<string>('mujer')
  const [selectorAbierto, setSelectorAbierto] = useState(false)
  const [velocidad, setVelocidad] = useState(1)
  const [motorTts, setMotorTts] = useState<'servidor' | 'navegador'>('servidor')
  const [ocupado, setOcupado] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    initPersonajes()
    if (usePersonajesStore.getState().voces.length === 0) void cargarCatalogo()
    void cargarFavoritos()
    void cargarHistorial()
  }, [initPersonajes, cargarCatalogo, cargarFavoritos, cargarHistorial])

  const tokenFakeYou = quienLee.startsWith('fy:') ? quienLee.slice(3) : null
  const esFakeYou = tokenFakeYou !== null

  const vozFakeYouElegida = useMemo(
    () => (tokenFakeYou ? vocesPersonajes.find((v) => v.token === tokenFakeYou) ?? null : null),
    [tokenFakeYou, vocesPersonajes],
  )

  // Quién narra. Una sola cadena DSP, jamás dos combinadas; el elenco
  // FakeYou no pasa por DSP (la voz llega sintetizada completa).
  const elegida = useMemo<ElegidaLectura | null>(() => {
    if (esFakeYou) return vozFakeYouElegida ? { tipo: 'fakeyou', voz: vozFakeYouElegida } : null
    if (quienLee === 'mujer') return { tipo: 'servidor', nombre: 'la narradora' }
    if (quienLee === 'hombre')
      return { tipo: 'servidor', nombre: 'el narrador', parametros: PRESET_NARRADOR_HOMBRE }
    if (quienLee === 'activa') {
      return vozActiva
        ? { tipo: 'servidor', nombre: vozActiva.nombre, parametros: vozActiva.parametros_dsp }
        : null
    }
    const v = voces.find((x) => x.id === quienLee)
    return v ? { tipo: 'servidor', nombre: v.nombre, parametros: v.parametros_dsp } : null
  }, [esFakeYou, vozFakeYouElegida, quienLee, vozActiva, voces])

  const etiquetaQuienLee = useMemo(() => {
    if (esFakeYou) return vozFakeYouElegida?.titulo ?? 'Personaje'
    if (quienLee === 'mujer') return 'Narradora · mujer'
    if (quienLee === 'hombre') return 'Narrador · hombre'
    if (quienLee === 'activa') return vozActiva ? `Voz activa · ${vozActiva.nombre}` : 'Voz activa'
    const v = voces.find((x) => x.id === quienLee)
    return v ? `${v.icono} ${v.nombre}` : 'Elige quién lee'
  }, [esFakeYou, vozFakeYouElegida, quienLee, vozActiva, voces])

  const ayudaQuienLee = useMemo(() => {
    if (!elegida) return 'Elige quién lee.'
    if (elegida.tipo === 'fakeyou') {
      return `Leerá ${elegida.voz.titulo}: voz de personaje sintetizada por FakeYou.`
    }
    if (quienLee === 'mujer') {
      return 'Leerá la narradora: voz femenina con pronunciación española, sin efectos.'
    }
    if (quienLee === 'hombre') {
      return 'Leerá el narrador: la misma voz forjada con DSP (tono grave y garganta más grande) para sonar a hombre.'
    }
    return `Leerá ${elegida.nombre}: la narración llevará su cadena de efectos, igual que al probar la voz.`
  }, [elegida, quienLee])

  const vocesFyFavoritas = useMemo(
    () => vocesPersonajes.filter((v) => favoritas.includes(v.token)),
    [vocesPersonajes, favoritas],
  )
  const vocesFyResto = useMemo(
    () => vocesPersonajes.filter((v) => !favoritas.includes(v.token)),
    [vocesPersonajes, favoritas],
  )

  const totalFragmentos = useMemo(() => fragmentarTexto(texto).length, [texto])

  const ocupadoFakeYou = generacion.fase === 'enviando' || generacion.fase === 'pendiente'
  const ocupadoTotal = ocupado || ocupadoFakeYou
  const urlAudio = audioId ? `/api/personajes/audio?id=${encodeURIComponent(audioId)}` : null
  const tituloAudio = historial.find((h) => h.id === audioId)?.tituloVoz ?? generacion.tituloVoz

  const elegir = (valor: string) => {
    setQuienLee(valor)
    setSelectorAbierto(false)
    if (valor.startsWith('fy:')) {
      seleccionarVoz(valor.slice(3))
      if (texto.length > MAX_TEXTO_FAKEYOU) {
        setTexto(texto.slice(0, MAX_TEXTO_FAKEYOU))
        toast.info('El texto se recortó a 500 caracteres', {
          description: 'Es el límite por generación de FakeYou.',
        })
      }
    } else {
      seleccionarVoz(null)
    }
  }

  const cambiarTexto = (valor: string) => {
    setTexto(esFakeYou ? valor.slice(0, MAX_TEXTO_FAKEYOU) : valor)
  }

  const cargarArchivo = async (archivo: File) => {
    try {
      const contenido = await archivo.text()
      cambiarTexto(contenido)
      toast.success(`Archivo cargado: ${archivo.name}`, {
        description: `${contenido.length} caracteres, ${fragmentarTexto(contenido).length} fragmentos.`,
      })
    } catch (e) {
      const err = clasificarError(e, 'datos')
      toast.error('No se pudo leer el archivo', { description: err.remedio })
    }
  }

  const reproducir = async () => {
    if (ocupadoTotal || !texto.trim() || !elegida) return

    // Elenco FakeYou: la cola del store hace el envío y la encuesta; el
    // audio aparece en el reproductor cuando la voz está lista.
    if (esFakeYou) {
      void generar(texto)
      return
    }

    setOcupado(true)
    setAudioId(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLectura({ activa: true, fase: 'sintetizando', fragmento: 0, total: totalFragmentos })

    try {
      if (motorTts === 'servidor') {
        await leerConServidor({
          texto,
          velocidad,
          parametros: elegida.tipo === 'servidor' ? elegida.parametros : undefined,
          senal: ctrl.signal,
          onProgreso: (p) => setLectura({ fase: p.fase, fragmento: p.fragmento, total: p.total }),
        })
      } else {
        if (elegida.tipo === 'servidor' && elegida.parametros) {
          toast.info('La voz del navegador no aplica efectos de personaje', {
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
    if (esFakeYou) {
      cancelarGeneracion()
      return
    }
    abortRef.current?.abort()
    motor.detenerLectura()
    detenerLecturaNavegador()
  }

  const descargarAudioActual = () => {
    if (!audioId) return
    const ancla = document.createElement('a')
    ancla.href = `/api/personajes/audio?id=${encodeURIComponent(audioId)}`
    ancla.download = `personaje_${slug(tituloAudio ?? 'voz')}.wav`
    ancla.click()
  }

  const descargar = async () => {
    if (esFakeYou) {
      descargarAudioActual()
      return
    }
    if (ocupado || !texto.trim() || !elegida) return
    setOcupado(true)
    setAudioId(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLectura({ activa: true, fase: 'sintetizando', fragmento: 0, total: totalFragmentos })
    try {
      await descargarWavLectura({
        texto,
        velocidad,
        parametros: elegida.tipo === 'servidor' ? elegida.parametros : undefined,
        senal: ctrl.signal,
        onProgreso: (p) => setLectura({ fase: p.fase, fragmento: p.fragmento, total: p.total }),
      })
      toast.success('WAV descargado', {
        description:
          elegida.tipo === 'servidor' && elegida.parametros
            ? `Render offline con la cadena de ${elegida.nombre}.`
            : 'Render offline de la narradora, sin efectos.',
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

  const puedeDescargar = esFakeYou
    ? Boolean(urlAudio)
    : !ocupadoTotal && Boolean(texto.trim()) && motorTts === 'servidor'

  const tituloDescargar = esFakeYou
    ? urlAudio
      ? 'Descarga el audio del personaje'
      : 'Genera primero la voz del personaje'
    : motorTts !== 'servidor'
      ? 'La descarga WAV requiere el motor del servidor'
      : elegida?.tipo === 'servidor' && elegida.parametros
        ? 'Descarga el WAV con la cadena del narrador elegido'
        : 'Descarga el WAV de la narradora'

  const textoFase: Record<string, string> = {
    sintetizando: 'Sintetizando fragmento',
    reproduciendo: 'Reproduciendo fragmento',
    descargando: 'Renderizando WAV…',
    fin: 'Listo',
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Texto a leer</CardTitle>
          <CardDescription>Escribe o carga un .txt.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={texto}
            onChange={(e) => cambiarTexto(e.target.value)}
            rows={7}
            maxLength={esFakeYou ? MAX_TEXTO_FAKEYOU : undefined}
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
              <Button variant="outline" asChild disabled={ocupadoTotal}>
                <span role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') (e.currentTarget.previousElementSibling as HTMLElement)?.click() }}>
                  <FileText className="size-4" />
                  Cargar .txt
                </span>
              </Button>
            </label>
            <span className="text-xs text-muted-foreground">
              {esFakeYou ? (
                <span className={texto.length >= MAX_TEXTO_FAKEYOU ? 'text-amber-400' : ''}>
                  {texto.length}/{MAX_TEXTO_FAKEYOU}
                </span>
              ) : (
                <>
                  {texto.length} caracteres · {totalFragmentos} fragmento{totalFragmentos === 1 ? '' : 's'}
                </>
              )}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Favoritos</CardTitle>
          <CardDescription>
            Tus voces marcadas con la estrella: un clic y quedan elegidas para leer.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {cargandoCatalogo && vocesPersonajes.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Cargando tus favoritas…
            </p>
          ) : errorCatalogo && vocesPersonajes.length === 0 ? (
            <div className="flex flex-wrap items-center gap-3">
              <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
                <AlertTriangle className="size-4" aria-hidden="true" />
                El elenco no está disponible ahora mismo.
              </p>
              <Button size="sm" variant="outline" onClick={() => void cargarCatalogo()}>
                Reintentar
              </Button>
            </div>
          ) : vocesFyFavoritas.length === 0 ? (
            <p className="flex items-start gap-2 text-sm text-muted-foreground">
              <Star className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Aún no tienes favoritas: elige un personaje en «¿Quién lee?» y márcalo con la estrella.
            </p>
          ) : (
            <ul
              className="rol-custom flex max-h-40 flex-wrap content-start gap-2 overflow-y-auto pr-1"
              aria-label="Voces favoritas"
            >
              {vocesFyFavoritas.map((v) => {
                const esLaElegida = tokenFakeYou === v.token
                return (
                  <li key={v.token}>
                    <Button
                      variant={esLaElegida ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => elegir(`fy:${v.token}`)}
                      aria-pressed={esLaElegida}
                      className={esLaElegida ? 'ring-1 ring-primary/60' : undefined}
                    >
                      <Star
                        className="size-3.5 shrink-0 fill-amber-400 text-amber-400"
                        aria-hidden="true"
                      />
                      <span className="max-w-52 truncate">{v.titulo}</span>
                      {esLaElegida && <Check className="size-4 text-primary" aria-hidden="true" />}
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Síntesis de voz</CardTitle>
          <CardDescription>
            Narradores con pronunciación española, tus voces y todo el elenco de personajes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="quien-lee">¿Quién lee?</Label>
            <Popover open={selectorAbierto} onOpenChange={setSelectorAbierto}>
              <PopoverTrigger asChild>
                <Button
                  id="quien-lee"
                  variant="outline"
                  role="combobox"
                  aria-expanded={selectorAbierto}
                  aria-label="Elegir quién lee"
                  className="w-full justify-between font-normal"
                >
                  <span className="truncate">{etiquetaQuienLee}</span>
                  <ChevronsUpDown className="size-4 shrink-0 opacity-50" aria-hidden="true" />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                align="start"
                className="p-0"
                style={{ width: 'var(--radix-popover-trigger-width)' }}
              >
                <Command
                  filter={(valor, busqueda) => {
                    const limpio = quitarAcentos(valor.toLowerCase())
                    const consulta = quitarAcentos(busqueda.trim().toLowerCase())
                    return consulta && limpio.includes(consulta) ? 1 : 0
                  }}
                >
                  <CommandInput placeholder="Buscar narrador o personaje…" aria-label="Buscar narrador o personaje" />
                  <CommandList className="rol-custom max-h-80">
                    <CommandEmpty>Ninguna voz coincide con la búsqueda.</CommandEmpty>

                    <CommandGroup heading="Narradores">
                      <CommandItem value="narradora mujer" onSelect={() => elegir('mujer')}>
                        Narradora · mujer
                        {quienLee === 'mujer' && (
                          <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                        )}
                      </CommandItem>
                      <CommandItem value="narrador hombre" onSelect={() => elegir('hombre')}>
                        Narrador · hombre
                        {quienLee === 'hombre' && (
                          <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                        )}
                      </CommandItem>
                    </CommandGroup>

                    <CommandGroup heading="Tus voces">
                      <CommandItem value="voz activa" onSelect={() => elegir('activa')}>
                        {vozActiva ? `Voz activa · ${vozActiva.nombre}` : 'Voz activa'}
                        {quienLee === 'activa' && (
                          <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                        )}
                      </CommandItem>
                      {voces
                        .filter((v) => v.id !== vozActivaId)
                        .map((v) => (
                          <CommandItem key={v.id} value={v.nombre} onSelect={() => elegir(v.id)}>
                            {`${v.icono} ${v.nombre}`}
                            {quienLee === v.id && (
                              <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                            )}
                          </CommandItem>
                        ))}
                    </CommandGroup>

                    {vocesFyFavoritas.length > 0 && (
                      <CommandGroup heading="★ Favoritas">
                        {vocesFyFavoritas.map((v) => (
                          <CommandItem
                            key={v.token}
                            value={`${v.titulo} ${v.grupo}`}
                            onSelect={() => elegir(`fy:${v.token}`)}
                          >
                            <Star
                              className="size-3.5 shrink-0 fill-amber-400 text-amber-400"
                              aria-hidden="true"
                            />
                            <span className="truncate">{v.titulo}</span>
                            {tokenFakeYou === v.token && (
                              <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                            )}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    )}

                    <CommandGroup heading="Personajes">
                      {cargandoCatalogo && vocesPersonajes.length === 0 ? (
                        <p className="px-2 py-1.5 text-xs text-muted-foreground" role="status">
                          Cargando el elenco…
                        </p>
                      ) : errorCatalogo && vocesPersonajes.length === 0 ? (
                        <CommandItem
                          value="reintentar catalogo"
                          onSelect={() => void cargarCatalogo()}
                        >
                          <AlertTriangle className="size-4" aria-hidden="true" />
                          No se pudo cargar. Reintentar
                        </CommandItem>
                      ) : (
                        vocesFyResto.map((v) => (
                          <CommandItem
                            key={v.token}
                            value={`${v.titulo} ${v.grupo}`}
                            onSelect={() => elegir(`fy:${v.token}`)}
                          >
                            <span className="truncate">{v.titulo}</span>
                            {tokenFakeYou === v.token && (
                              <Check className="ml-auto size-4 text-primary" aria-hidden="true" />
                            )}
                          </CommandItem>
                        ))
                      )}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <div className="flex items-start gap-2">
              <p className="flex-1 text-xs text-muted-foreground" role="status">
                {ayudaQuienLee}
              </p>
              {vozFakeYouElegida && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 shrink-0"
                  aria-label={
                    favoritas.includes(vozFakeYouElegida.token)
                      ? `Quitar ${vozFakeYouElegida.titulo} de favoritas`
                      : `Añadir ${vozFakeYouElegida.titulo} a favoritas`
                  }
                  onClick={() => void alternarFavorito(vozFakeYouElegida)}
                >
                  <Star
                    className={
                      favoritas.includes(vozFakeYouElegida.token)
                        ? 'size-4 fill-amber-400 text-amber-400'
                        : 'size-4'
                    }
                    aria-hidden="true"
                  />
                </Button>
              )}
            </div>
          </div>

          {esFakeYou ? (
            <p className="text-xs text-muted-foreground">
              FakeYou sintetiza la frase completa: sin control de velocidad ni efectos. Suele tardar
              entre 15 s y 1 min.
            </p>
          ) : (
            <>
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

              <div className="space-y-2">
                <Label htmlFor="motor-tts">Motor</Label>
                <Select value={motorTts} onValueChange={(v) => setMotorTts(v as 'servidor' | 'navegador')}>
                  <SelectTrigger id="motor-tts" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="servidor">Voz neural del servidor · recomendada</SelectItem>
                    <SelectItem value="navegador">Voz del navegador · respaldo sin efectos</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void reproducir()} disabled={ocupadoTotal || !texto.trim() || !elegida}>
              {esFakeYou && ocupadoFakeYou ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Play className="size-4" aria-hidden="true" />
              )}
              {esFakeYou ? (ocupadoFakeYou ? 'Sintetizando…' : 'Generar voz') : 'Reproducir'}
            </Button>
            <Button variant="outline" onClick={detener} disabled={!ocupadoTotal}>
              <Square className="size-4" aria-hidden="true" />
              Detener
            </Button>
            <Button
              variant="outline"
              onClick={() => void descargar()}
              disabled={!puedeDescargar}
              title={tituloDescargar}
              className="ml-auto"
            >
              <Download className="size-4" aria-hidden="true" />
              Descargar WAV
            </Button>
          </div>

          {esFakeYou && ocupadoFakeYou && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {generacion.fase === 'enviando'
                ? 'Enviando el trabajo a FakeYou…'
                : 'Sintetizando en FakeYou. Suele tardar entre 15 s y 1 min…'}
            </p>
          )}

          {esFakeYou && generacion.fase === 'error' && (
            <Alert variant="destructive">
              <AlertTriangle className="size-4" aria-hidden="true" />
              <AlertTitle>La generación falló</AlertTitle>
              <AlertDescription>{generacion.mensaje}</AlertDescription>
            </Alert>
          )}

          {!esFakeYou && (ocupado || lectura.total > 0) && (
            <div className="space-y-1.5">
              <Progress value={lectura.total > 0 ? (lectura.fragmento / lectura.total) * 100 : 0} />
              <p className="text-xs text-muted-foreground" role="status">
                {textoFase[lectura.fase] ?? ''} {lectura.total > 0 ? `${lectura.fragmento}/${lectura.total}` : ''}
              </p>
            </div>
          )}

          {urlAudio && (
            <div className="space-y-1.5">
              <audio key={audioId ?? undefined} controls src={urlAudio} autoPlay className="h-10 w-full" preload="none">
                Tu navegador no puede reproducir audio.
              </audio>
              <p className="text-xs text-muted-foreground">
                {tituloAudio ? `Voz de ${tituloAudio}` : 'Audio generado'}
                {generacion.cacheado && generacion.id === audioId && ' · salió de la caché (sin gastar cupo)'}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Siempre visible: la propia tarjeta explica sus límites
          (FakeYou/navegador no pueden renderizar WAV por escena). */}
      <TarjetaColaEscenas
        textoActual={texto}
        elegida={elegida}
        velocidad={velocidad}
        esFakeYou={esFakeYou}
        motorNavegador={motorTts === 'navegador'}
      />

      <TarjetaNotasSesion />

      {historial.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <History className="size-4 text-muted-foreground" aria-hidden="true" />
              Generaciones recientes
            </CardTitle>
            <CardDescription>Cada audio queda guardado: reescúchalo o descárgalo.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="rol-custom max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {historial.map((h) => (
                <li
                  key={h.id}
                  className={`flex items-center gap-2 rounded-md border p-2 ${h.id === audioId ? 'border-primary/50 bg-accent/40' : ''}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium">{h.tituloVoz}</p>
                    <p className="truncate text-xs text-muted-foreground" title={h.texto}>
                      {h.estado === 'error' ? `⚠ ${h.error ?? 'falló'}` : h.texto}
                    </p>
                    <p className="text-[10px] text-muted-foreground">{fechaCorta(h.createdAt)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {h.estado === 'listo' && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        aria-label={`Reproducir: ${h.tituloVoz}`}
                        onClick={() => setAudioId(h.id)}
                      >
                        <Play className="size-3.5" aria-hidden="true" />
                      </Button>
                    )}
                    {h.estado === 'listo' && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        aria-label={`Descargar audio de ${h.tituloVoz}`}
                        onClick={() => {
                          const ancla = document.createElement('a')
                          ancla.href = `/api/personajes/audio?id=${encodeURIComponent(h.id)}`
                          ancla.download = `personaje_${slug(h.tituloVoz)}.wav`
                          ancla.click()
                        }}
                      >
                        <Download className="size-3.5" aria-hidden="true" />
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 text-muted-foreground hover:text-destructive"
                      aria-label={`Borrar generación de ${h.tituloVoz}`}
                      onClick={() => void borrarHistorial(h.id)}
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
