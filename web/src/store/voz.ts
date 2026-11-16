// Estado global de la app (zustand). El motor de audio es un singleton
// imperativo (src/lib/motor-audio.ts); el store sincroniza la UI con él.

'use client'

import { create } from 'zustand'
import { toast } from 'sonner'
import { clasificarError, errorVoz } from '@/lib/errores'
import { motor, type EstadoMotor, type ResultadoGrabacion } from '@/lib/motor-audio'
import {
  AJUSTES_POR_DEFECTO,
  cargarVocesBase,
  crearVozPersonalizada,
  escribirAjustes,
  escribirAtajosGuardados,
  escribirIdsVocesOcultas,
  escribirVocesPersonalizadas,
  escribirVozActiva,
  leerAjustes,
  leerAtajosGuardados,
  leerIdsVocesOcultas,
  leerVocesPersonalizadas,
  leerVozActiva,
} from '@/lib/voces'
import type { Ajustes, ParametrosDSP, Voz } from '@/lib/tipos'

export interface Degradacion {
  id: string
  mensaje: string
}

interface EstadoLectura {
  activa: boolean
  fase: string
  fragmento: number
  total: number
}

interface EstadoApp {
  listo: boolean
  voces: Voz[]
  vocesOcultas: Voz[]
  vozActivaId: string
  ajustes: Ajustes
  /** Overrides de atajos sobre las voces base (la del catálogo es sugerencia inicial). */
  atajosGuardados: Record<string, string | null>
  /** Id de la voz cuya tecla se está capturando en Ajustes (null = captura apagada). */
  capturandoAtajoId: string | null
  estadoMotor: EstadoMotor
  grabando: boolean
  grabacion: ResultadoGrabacion | null
  dispositivosEntrada: MediaDeviceInfo[]
  degradaciones: Degradacion[]
  lectura: EstadoLectura

  init(): void
  vozActiva(): Voz | undefined
  seleccionarVoz(id: string): void
  aplicarParametrosEnVivo(params: ParametrosDSP): void
  guardarVozPersonalizada(
    nombre: string,
    params: ParametrosDSP,
    extras?: { icono?: string; color?: string },
  ): void
  borrarVozPersonalizada(id: string): void
  reinsertarVozPersonalizada(voz: Voz): void
  ocultarVoz(id: string): void
  restaurarVoz(id: string): void
  restaurarVocesOcultas(): void
  iniciarCapturaAtajo(id: string | null): void
  asignarAtajo(id: string, combo: string | null): void
  restaurarAtajosSugeridos(): void

  iniciarMotor(): Promise<void>
  pararMotor(): void
  alternarPausa(): void
  setMonitor(activo: boolean): void
  setVolumenMonitor(v: number): void
  setSrObjetivo(sr: number): void
  setAtajos(activos: boolean): void
  setDispositivoEntrada(id: string | null): void
  actualizarDispositivos(): Promise<void>

  iniciarGrabacion(): Promise<void>
  terminarGrabacion(): Promise<void>
  limpiarGrabacion(): void

  setLectura(lectura: Partial<EstadoLectura>): void
  addDegradacion(id: string, mensaje: string): void
  quitarDegradacion(id: string): void
  restablecerDatos(): void
}

function persistirAjustes(ajustes: Ajustes): void {
  if (!escribirAjustes(ajustes)) {
    toast.error('No se pudieron guardar los ajustes', {
      description: 'El almacenamiento local no está disponible en este navegador.',
    })
  }
}

export const useVozStore = create<EstadoApp>((set, get) => ({
  listo: false,
  voces: [],
  vocesOcultas: [],
  vozActivaId: '',
  ajustes: AJUSTES_POR_DEFECTO,
  atajosGuardados: {},
  capturandoAtajoId: null,
  estadoMotor: 'detenido',
  grabando: false,
  grabacion: null,
  dispositivosEntrada: [],
  degradaciones: [],
  lectura: { activa: false, fase: 'fin', fragmento: 0, total: 0 },

  init() {
    if (get().listo) return
    const base = cargarVocesBase()
    const custom = leerVocesPersonalizadas()
    const { ajustes, aviso: avisoAjustes } = leerAjustes()
    const { ids: idsOcultos, aviso: avisoOcultos } = leerIdsVocesOcultas()
    const atajosGuardados = leerAtajosGuardados()

    // Los atajos decididos por el usuario (Ajustes) se aplican sobre el catálogo
    // cargado; el dato generado nunca se toca. También cubre las voces ocultas
    // para que, al restaurarlas, conserven la tecla que tenían.
    const conAtajos = base.voces.map((v) =>
      v.id in atajosGuardados ? { ...v, atajo: atajosGuardados[v.id] } : v,
    )

    // Voces base quitadas de la lista (restaurables). La Neutral JAMÁS queda
    // oculta aunque el dato la incluya: es la voz de seguridad del arranque.
    const ocultasSet = new Set(idsOcultos)
    const ocultas = conAtajos.filter((v) => ocultasSet.has(v.id) && v.nombre !== 'Neutral')
    const visibles = conAtajos.filter((v) => !ocultasSet.has(v.id) || v.nombre === 'Neutral')
    const voces = [...visibles, ...custom.voces]

    const guardada = leerVozActiva()
    const inicial = voces.find((v) => v.id === guardada) ?? voces.find((v) => v.nombre === 'Neutral') ?? voces[0]

    motor.monitorActivo = ajustes.monitor
    motor.volumenMonitor = ajustes.volumenMonitor
    motor.srObjetivo = ajustes.srObjetivo
    motor.onCambio = () => set({ estadoMotor: motor.estado })
    motor.onMicrofonoPerdido = () => {
      toast.error('El micrófono se desconectó', {
        description: 'El dispositivo desapareció o fue reclamado por otra app. Vuelve a iniciarlo.',
      })
    }
    motor.onDegradacionWorklet = (e) => {
      get().addDegradacion('worklet-interno', `El procesador de voz falló y quedó en paso directo (${e.message}). Recarga la página si los efectos no vuelven.`)
    }

    if (inicial) motor.fijarParametros(inicial.parametros_dsp)

    set({
      listo: true,
      voces,
      vocesOcultas: ocultas,
      vozActivaId: inicial?.id ?? '',
      ajustes,
      atajosGuardados,
      estadoMotor: motor.estado,
    })

    const avisos = [base.aviso, custom.aviso, avisoAjustes, avisoOcultos].filter(Boolean).join(' ')
    if (avisos) {
      toast.warning('Avisos al cargar', { description: avisos })
    }
  },

  vozActiva() {
    const { voces, vozActivaId } = get()
    return voces.find((v) => v.id === vozActivaId)
  },

  seleccionarVoz(id) {
    const voz = get().voces.find((v) => v.id === id)
    if (!voz || id === get().vozActivaId) return
    motor.fijarParametros(voz.parametros_dsp, { reset: true })
    escribirVozActiva(id)
    set({ vozActivaId: id })
  },

  aplicarParametrosEnVivo(params) {
    motor.fijarParametros(params, { reset: false })
  },

  guardarVozPersonalizada(nombre, params, extras) {
    const nueva = crearVozPersonalizada(nombre, params, extras)
    const custom = get().voces.filter((v) => v.personalizada)
    if (!escribirVocesPersonalizadas([...custom, nueva])) {
      toast.error('No se pudo guardar la voz', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    set({ voces: [...get().voces, nueva] })
    get().seleccionarVoz(nueva.id)
    toast.success(`Voz "${nueva.nombre}" guardada`, {
      description: 'Queda disponible en la pestaña Voces y persiste en este navegador.',
    })
  },

  borrarVozPersonalizada(id) {
    const voz = get().voces.find((v) => v.id === id)
    if (!voz?.personalizada) return
    const restantes = get().voces.filter((v) => v.id !== id)
    if (!escribirVocesPersonalizadas(restantes.filter((v) => v.personalizada))) {
      toast.error('No se pudo eliminar la voz', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    if (get().vozActivaId === id) {
      const neutral = restantes.find((v) => v.nombre === 'Neutral') ?? restantes[0]
      if (neutral) {
        motor.fijarParametros(neutral.parametros_dsp, { reset: true })
        escribirVozActiva(neutral.id)
      }
      set({ voces: restantes, vozActivaId: neutral?.id ?? '' })
    } else {
      set({ voces: restantes })
    }
    toast.success(`Voz "${voz.nombre}" eliminada`, {
      action: { label: 'Deshacer', onClick: () => get().reinsertarVozPersonalizada(voz) },
    })
  },

  // Deshacer del borrado de una voz personalizada: la reinserta y persiste.
  reinsertarVozPersonalizada(voz) {
    if (get().voces.some((v) => v.id === voz.id)) return
    const custom = get().voces.filter((v) => v.personalizada)
    if (!escribirVocesPersonalizadas([...custom, voz])) {
      toast.error('No se pudo recuperar la voz', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    set({ voces: [...get().voces, voz] })
    toast.success(`Voz "${voz.nombre}" recuperada`)
  },

  // Quita una voz BASE de la lista (ocultarla): el catálogo generado no se
  // toca, solo se registra su id como oculto y se puede restaurar. La voz
  // activa nunca se queda huérfana: si se oculta, vuelve a Neutral.
  ocultarVoz(id) {
    const voz = get().voces.find((v) => v.id === id)
    if (!voz || voz.personalizada) return
    if (voz.nombre === 'Neutral') {
      toast.info('La voz Neutral no se puede quitar', {
        description: 'Es la voz de seguridad a la que vuelve la app si algo falla.',
      })
      return
    }
    const visibles = get().voces.filter((v) => v.id !== id)
    const ocultas = [...get().vocesOcultas, voz]
    if (!escribirIdsVocesOcultas(ocultas.map((v) => v.id))) {
      toast.error('No se pudo quitar la voz', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    if (get().vozActivaId === id) {
      const neutral = visibles.find((v) => v.nombre === 'Neutral') ?? visibles[0]
      if (neutral) {
        motor.fijarParametros(neutral.parametros_dsp, { reset: true })
        escribirVozActiva(neutral.id)
      }
      set({ voces: visibles, vocesOcultas: ocultas, vozActivaId: neutral?.id ?? '' })
    } else {
      set({ voces: visibles, vocesOcultas: ocultas })
    }
    toast.success(`Voz "${voz.nombre}" quitada de la lista`, {
      description: 'Se restaura en Ajustes › Voces ocultas.',
      action: { label: 'Deshacer', onClick: () => get().restaurarVoz(id) },
    })
  },

  restaurarVoz(id) {
    const voz = get().vocesOcultas.find((v) => v.id === id)
    if (!voz) return
    const ocultas = get().vocesOcultas.filter((v) => v.id !== id)
    if (!escribirIdsVocesOcultas(ocultas.map((v) => v.id))) {
      toast.error('No se pudo restaurar la voz', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    // Se reinserta entre las base, antes que las personalizadas (orden estable).
    const personalizadas = get().voces.filter((v) => v.personalizada)
    const baseVisibles = get().voces.filter((v) => !v.personalizada)
    set({ voces: [...baseVisibles, voz, ...personalizadas], vocesOcultas: ocultas })
    toast.success(`Voz "${voz.nombre}" restaurada`)
  },

  restaurarVocesOcultas() {
    const ocultas = get().vocesOcultas
    if (ocultas.length === 0) return
    if (!escribirIdsVocesOcultas([])) {
      toast.error('No se pudieron restaurar las voces', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    const personalizadas = get().voces.filter((v) => v.personalizada)
    const baseVisibles = get().voces.filter((v) => !v.personalizada)
    set({ voces: [...baseVisibles, ...ocultas, ...personalizadas], vocesOcultas: [] })
    toast.success(`${ocultas.length} voz(es) restauradas`, {
      description: 'Vuelven a aparecer en la pestaña Voces.',
    })
  },

  // Modo captura de Ajustes: marca qué voz espera una tecla (y silencia el
  // gancho global de atajos mientras tanto).
  iniciarCapturaAtajo(id) {
    set({ capturandoAtajoId: id })
  },

  // Asignación manual de atajos. La tecla es propiedad exclusiva: si otra voz
  // (visible u oculta) ya la tenía, se la quitamos y avisamos. Las voces base
  // persisten como override (el catálogo no se toca); las personalizadas,
  // dentro de su propio dato en localStorage.
  asignarAtajo(id, combo) {
    const voces = get().voces
    const voz = voces.find((v) => v.id === id)
    if (!voz) return
    if ((voz.atajo ?? null) === combo) {
      set({ capturandoAtajoId: null })
      return
    }

    const overrides: Record<string, string | null> = { ...get().atajosGuardados }
    const personalizadasCambiadas: Voz[] = []
    let robadaDe: string | null = null

    if (combo) {
      const duena = [...get().voces, ...get().vocesOcultas].find(
        (v) => v.id !== id && v.atajo === combo,
      )
      if (duena) {
        robadaDe = duena.nombre
        if (duena.personalizada) personalizadasCambiadas.push({ ...duena, atajo: null })
        else overrides[duena.id] = null
      }
    }

    if (voz.personalizada) personalizadasCambiadas.push({ ...voz, atajo: combo })
    else overrides[id] = combo

    if (personalizadasCambiadas.length > 0) {
      const cambiadas = new Map(personalizadasCambiadas.map((v) => [v.id, v]))
      const mezcla = get().voces
        .filter((v) => v.personalizada)
        .map((v) => cambiadas.get(v.id) ?? v)
      if (!escribirVocesPersonalizadas(mezcla)) {
        toast.error('No se pudo guardar el atajo', {
          description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
        })
        return
      }
    }
    if (!escribirAtajosGuardados(overrides)) {
      toast.error('No se pudo guardar el atajo', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }

    const cambiadas = new Map(personalizadasCambiadas.map((v) => [v.id, v]))
    const vocesNuevas = voces.map((v) => {
      if (cambiadas.has(v.id)) return cambiadas.get(v.id)!
      if (v.id in overrides) return { ...v, atajo: overrides[v.id] }
      return v
    })
    const ocultasNuevas = get().vocesOcultas.map((v) =>
      v.id in overrides ? { ...v, atajo: overrides[v.id] } : v,
    )
    set({
      voces: vocesNuevas,
      vocesOcultas: ocultasNuevas,
      atajosGuardados: overrides,
      capturandoAtajoId: null,
    })

    if (combo === null) {
      toast.success(`Atajo de «${voz.nombre}» quitado`)
    } else if (robadaDe) {
      toast.warning(`Atajo ${combo} asignado a «${voz.nombre}»`, {
        description: `Estaba en «${robadaDe}», que se queda sin atajo.`,
      })
    } else {
      toast.success(`Atajo ${combo} asignado a «${voz.nombre}»`)
    }
  },

  // Vuelve a la asignación sugerida por el catálogo: borra todos los overrides
  // (base) y deja sin tecla las personalizadas, que nacen sin atajo.
  restaurarAtajosSugeridos() {
    const sinCambios =
      Object.keys(get().atajosGuardados).length === 0 &&
      !get().voces.some((v) => v.personalizada && v.atajo)
    if (sinCambios) return
    if (!escribirAtajosGuardados({})) {
      toast.error('No se pudieron restaurar los atajos', {
        description: 'El almacenamiento local rechazó la escritura (¿modo privado?).',
      })
      return
    }
    const personalizadas = get()
      .voces.filter((v) => v.personalizada)
      .map((v) => ({ ...v, atajo: null }))
    if (personalizadas.length > 0) escribirVocesPersonalizadas(personalizadas)

    const base = cargarVocesBase()
    const ocultasSet = new Set(get().vocesOcultas.map((v) => v.id))
    set({
      voces: [...base.voces.filter((v) => !ocultasSet.has(v.id) || v.nombre === 'Neutral'), ...personalizadas],
      vocesOcultas: base.voces.filter((v) => ocultasSet.has(v.id) && v.nombre !== 'Neutral'),
      atajosGuardados: {},
    })
    toast.success('Atajos de fábrica restaurados', {
      description: 'La asignación sugerida por el catálogo vuelve a mandar.',
    })
  },

  async iniciarMotor() {
    const { ajustes } = get()
    try {
      motor.setSrObjetivo(ajustes.srObjetivo)
      motor.setMonitor(ajustes.monitor)
      motor.setVolumenMonitor(ajustes.volumenMonitor)
      await motor.iniciarMic(ajustes.dispositivoEntrada)
      await get().actualizarDispositivos()
      toast.success('Micrófono activo', {
        description: 'Auriculares recomendados para evitar acoples. La voz activa ya suena por el monitor.',
      })
    } catch (e) {
      const err = clasificarError(e, 'microfono')
      toast.error(err.titulo, { description: `${err.detalle ? err.detalle + ' ' : ''}${err.remedio}` })
      if (err.categoria === 'worklet_no_soportado') {
        get().addDegradacion('worklet', 'AudioWorklet no disponible: la app funciona sin efectos DSP.')
      }
      set({ estadoMotor: motor.estado })
    }
  },

  pararMotor() {
    if (get().grabando) {
      motor.grabarFin().catch(() => { /* sin residuos */ })
      set({ grabando: false })
    }
    motor.pararMic()
  },

  alternarPausa() {
    if (motor.estado === 'activo') motor.pausar()
    else if (motor.estado === 'pausado') motor.reanudar()
  },

  setMonitor(activo) {
    motor.setMonitor(activo)
    const ajustes = { ...get().ajustes, monitor: activo }
    set({ ajustes })
    persistirAjustes(ajustes)
  },

  setVolumenMonitor(v) {
    motor.setVolumenMonitor(v)
    const ajustes = { ...get().ajustes, volumenMonitor: v }
    set({ ajustes })
    persistirAjustes(ajustes)
  },

  setSrObjetivo(sr) {
    const ajustes = { ...get().ajustes, srObjetivo: sr }
    set({ ajustes })
    persistirAjustes(ajustes)
    motor.setSrObjetivo(sr)
    if (get().estadoMotor !== 'detenido') {
      toast.info('Frecuencia actualizada', {
        description: 'Se aplicará al reiniciar el micrófono (Detener e Iniciar).',
      })
    }
  },

  setAtajos(activos) {
    const ajustes = { ...get().ajustes, atajos: activos }
    set({ ajustes })
    persistirAjustes(ajustes)
  },

  setDispositivoEntrada(id) {
    const ajustes = { ...get().ajustes, dispositivoEntrada: id }
    set({ ajustes })
    persistirAjustes(ajustes)
    if (get().estadoMotor !== 'detenido') {
      toast.info('Dispositivo actualizado', {
        description: 'Reinicia el micrófono para usar el nuevo dispositivo.',
      })
    }
  },

  async actualizarDispositivos() {
    try {
      const dispositivos = await navigator.mediaDevices.enumerateDevices()
      set({ dispositivosEntrada: dispositivos.filter((d) => d.kind === 'audioinput') })
    } catch {
      /* sin permisos aún: la lista se llena tras iniciar el micrófono */
    }
  },

  async iniciarGrabacion() {
    try {
      await motor.grabarInicio()
      set({ grabando: true, grabacion: null })
      toast.info('Grabando (post-DSP)', {
        description: 'Pulsa de nuevo el botón para terminar y descargar.',
      })
    } catch (e) {
      const err = clasificarError(e, 'grabacion')
      toast.error(err.titulo, { description: err.remedio })
    }
  },

  async terminarGrabacion() {
    try {
      const resultado = await motor.grabarFin()
      set({ grabando: false, grabacion: resultado })
      toast.success('Grabación lista', {
        description: 'Descárgala con el botón de descarga de la barra superior.',
        duration: 6000,
      })
    } catch (e) {
      set({ grabando: false })
      const err = e instanceof Error && e.message.includes('vacía')
        ? errorVoz('grabacion_vacia')
        : clasificarError(e, 'grabacion')
      toast.error(err.titulo, { description: err.remedio })
    }
  },

  limpiarGrabacion() {
    const actual = get().grabacion
    if (actual) URL.revokeObjectURL(actual.url)
    set({ grabacion: null })
  },

  setLectura(parcial) {
    set({ lectura: { ...get().lectura, ...parcial } })
  },

  addDegradacion(id, mensaje) {
    const actual = get().degradaciones
    if (actual.some((d) => d.id === id)) return
    set({ degradaciones: [...actual, { id, mensaje }] })
  },

  quitarDegradacion(id) {
    set({ degradaciones: get().degradaciones.filter((d) => d.id !== id) })
  },

  restablecerDatos() {
    try {
      window.localStorage.removeItem('voz_dnd_web.voces_personalizadas')
      window.localStorage.removeItem('voz_dnd_web.ajustes')
      window.localStorage.removeItem('voz_dnd_web.voz_activa')
      window.localStorage.removeItem('voz_dnd_web.voces_ocultas')
      window.localStorage.removeItem('voz_dnd_web.atajos')
    } catch {
      /* modo privado: seguir con los valores en memoria */
    }
    const base = cargarVocesBase()
    const neutral = base.voces.find((v) => v.nombre === 'Neutral') ?? base.voces[0]
    motor.fijarParametros(neutral.parametros_dsp, { reset: true })
    motor.setMonitor(AJUSTES_POR_DEFECTO.monitor)
    motor.setVolumenMonitor(AJUSTES_POR_DEFECTO.volumenMonitor)
    set({
      voces: base.voces,
      vocesOcultas: [],
      vozActivaId: neutral.id,
      ajustes: AJUSTES_POR_DEFECTO,
      atajosGuardados: {},
      capturandoAtajoId: null,
    })
    toast.success('Datos restablecidos', {
      description: 'Voces personalizadas, ocultas y ajustes vuelven a los valores base.',
    })
  },
}))
