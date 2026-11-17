// Estado del elenco de personajes (FakeYou) — catálogo latino, favoritos,
// historial y la generación en curso. La encuesta (polling) vive aquí, no en
// el componente, para que siga viva al cambiar de pestaña. La SELECCIÓN de
// voz vive en la pestaña Leer («¿Quién lee?») y se sincroniza en
// `vozSeleccionadaToken`.

'use client'

import { create } from 'zustand'
import { toast } from 'sonner'

export interface VozPersonaje {
  token: string
  titulo: string
  creador: string
  locale: string
  grupo: string
  destacada: boolean
  prioridad: number
}

export interface ItemHistorial {
  id: string
  tituloVoz: string
  texto: string
  estado: string
  error: string | null
  createdAt: string
}

export type FaseGeneracion = 'inactiva' | 'enviando' | 'pendiente' | 'listo' | 'error'

export interface EstadoGeneracion {
  fase: FaseGeneracion
  id: string | null
  tituloVoz: string | null
  texto: string | null
  mensaje: string | null
  cacheado: boolean
}

const GENERACION_INACTIVA: EstadoGeneracion = {
  fase: 'inactiva',
  id: null,
  tituloVoz: null,
  texto: null,
  mensaje: null,
  cacheado: false,
}

const CLAVE_SESION = 'voz_dnd_web.sesion_fakeyou'

function leerSesionLocal(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_SESION)
  } catch {
    return null
  }
}

function escribirSesionLocal(valor: string | null): boolean {
  try {
    if (valor) window.localStorage.setItem(CLAVE_SESION, valor)
    else window.localStorage.removeItem(CLAVE_SESION)
    return true
  } catch {
    return false
  }
}

function dormir(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

interface EstadoPersonajes {
  // Catálogo
  cargandoCatalogo: boolean
  errorCatalogo: string | null
  voces: VozPersonaje[]
  total: number
  generadoEn: string | null

  // Selección sincronizada con «¿Quién lee?» de la pestaña Leer
  vozSeleccionadaToken: string | null

  // Favoritos / historial / sesión
  favoritas: string[]
  historial: ItemHistorial[]
  sesionFakeyou: string | null

  // Generación en curso y audio visible en el reproductor
  generacion: EstadoGeneracion
  audioId: string | null

  init(): void
  cargarCatalogo(): Promise<void>
  cargarFavoritos(): Promise<void>
  cargarHistorial(): Promise<void>
  alternarFavorito(voz: VozPersonaje): Promise<void>
  seleccionarVoz(token: string | null): void
  setAudioId(id: string | null): void
  setSesion(sesion: string | null): void
  generar(texto: string): Promise<void>
  cancelarGeneracion(): void
  borrarHistorial(id: string): Promise<void>
}

export const usePersonajesStore = create<EstadoPersonajes>((set, get) => ({
  cargandoCatalogo: false,
  errorCatalogo: null,
  voces: [],
  total: 0,
  generadoEn: null,
  vozSeleccionadaToken: null,
  favoritas: [],
  historial: [],
  sesionFakeyou: null,
  generacion: GENERACION_INACTIVA,
  audioId: null,

  init() {
    if (get().sesionFakeyou !== null) return
    const sesion = leerSesionLocal()
    set({ sesionFakeyou: sesion })
  },

  async cargarCatalogo() {
    if (get().cargandoCatalogo) return
    set({ cargandoCatalogo: true, errorCatalogo: null })
    try {
      const resp = await fetch('/api/personajes', { cache: 'no-store' })
      const data = (await resp.json()) as {
        ok: boolean
        total?: number
        generadoEn?: string
        voces?: VozPersonaje[]
        mensaje?: string
      }
      if (!resp.ok || !data.ok || !Array.isArray(data.voces)) {
        throw new Error(data.mensaje ?? 'El catálogo de FakeYou no está disponible ahora mismo')
      }
      set({
        voces: data.voces,
        total: data.total ?? data.voces.length,
        generadoEn: data.generadoEn ?? null,
        cargandoCatalogo: false,
      })
    } catch (e) {
      set({
        cargandoCatalogo: false,
        errorCatalogo: e instanceof Error ? e.message : 'Catálogo no disponible',
      })
    }
  },

  async cargarFavoritos() {
    try {
      const resp = await fetch('/api/personajes/favoritos', { cache: 'no-store' })
      const data = (await resp.json()) as { ok: boolean; favoritos?: { modelToken: string }[] }
      if (data.ok && Array.isArray(data.favoritos)) {
        set({ favoritas: data.favoritos.map((f) => f.modelToken) })
      }
    } catch {
      /* favoritos no críticos: se reintenta en la próxima visita */
    }
  },

  async cargarHistorial() {
    try {
      const resp = await fetch('/api/personajes/historial', { cache: 'no-store' })
      const data = (await resp.json()) as { ok: boolean; historial?: ItemHistorial[] }
      if (data.ok && Array.isArray(data.historial)) {
        set({ historial: data.historial })
      }
    } catch {
      /* histórico no crítico */
    }
  },

  async alternarFavorito(voz) {
    const actuales = get().favoritas
    const yaEsta = actuales.includes(voz.token)
    // Actualización optimista; se revierte si el servidor falla.
    set({ favoritas: yaEsta ? actuales.filter((t) => t !== voz.token) : [...actuales, voz.token] })
    try {
      const resp = yaEsta
        ? await fetch(`/api/personajes/favoritos?modelToken=${encodeURIComponent(voz.token)}`, {
            method: 'DELETE',
          })
        : await fetch('/api/personajes/favoritos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modelToken: voz.token, tituloVoz: voz.titulo }),
          })
      if (!resp.ok) throw new Error('respuesta no ok')
    } catch {
      set({ favoritas: actuales })
      toast.error('No se pudo guardar el favorito', {
        description: 'Inténtalo de nuevo en unos segundos.',
      })
    }
  },

  seleccionarVoz(token) {
    set({ vozSeleccionadaToken: token })
  },

  setAudioId(id) {
    set({ audioId: id })
  },

  setSesion(sesion) {
    const limpio = sesion?.trim() || null
    if (!escribirSesionLocal(limpio)) {
      toast.error('No se pudo guardar el token de sesión', {
        description: 'El almacenamiento local no está disponible en este navegador.',
      })
      return
    }
    set({ sesionFakeyou: limpio })
    toast.success(limpio ? 'Cuenta de FakeYou conectada' : 'Cuenta de FakeYou desconectada', {
      description: limpio
        ? 'Las siguientes generaciones usarán tu sesión (más cupo).'
        : 'Se volverá al cupo anónimo de FakeYou.',
    })
  },

  async generar(texto) {
    const { vozSeleccionadaToken, voces, sesionFakeyou, generacion } = get()
    const voz = voces.find((v) => v.token === vozSeleccionadaToken)
    if (!voz) {
      toast.error('Elige primero una voz del catálogo')
      return
    }
    const limpio = texto.trim()
    if (!limpio) {
      toast.error('Escribe qué dirá el personaje')
      return
    }
    if (generacion.fase === 'enviando' || generacion.fase === 'pendiente') {
      toast.info('Ya hay una generación en curso', {
        description: 'Espera a que termine o cancélala.',
      })
      return
    }

    set({
      generacion: { ...GENERACION_INACTIVA, fase: 'enviando', tituloVoz: voz.titulo, texto: limpio },
    })

    try {
      const resp = await fetch('/api/personajes/generar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modelToken: voz.token,
          tituloVoz: voz.titulo,
          texto: limpio,
          sesion: sesionFakeyou ?? undefined,
        }),
      })
      const data = (await resp.json()) as {
        ok: boolean
        id?: string
        estado?: string
        cacheado?: boolean
        mensaje?: string
        error?: string
      }

      if (!resp.ok || !data.ok) {
        set({
          generacion: {
            ...GENERACION_INACTIVA,
            fase: 'error',
            tituloVoz: voz.titulo,
            texto: limpio,
            mensaje: data.mensaje ?? 'No se pudo enviar la síntesis a FakeYou',
          },
        })
        void get().cargarHistorial()
        return
      }

      const id = data.id ?? null
      const cacheado = data.cacheado ?? false

      if (data.estado === 'listo' && id) {
        set({
          generacion: { ...GENERACION_INACTIVA, fase: 'listo', id, tituloVoz: voz.titulo, texto: limpio, cacheado },
          audioId: id,
        })
        toast.success(`Voz de ${voz.titulo} lista${cacheado ? ' (en caché)' : ''}`, {
          description: 'Reprodúcela o descárgala desde el reproductor.',
        })
        void get().cargarHistorial()
        return
      }

      set({
        generacion: { ...GENERACION_INACTIVA, fase: 'pendiente', id, tituloVoz: voz.titulo, texto: limpio },
      })
      if (id) void encuestaGeneracion(id)
    } catch {
      set({
        generacion: {
          ...GENERACION_INACTIVA,
          fase: 'error',
          tituloVoz: voz.titulo,
          texto: limpio,
          mensaje: 'Fallo de red al contactar con el servidor. Revisa tu conexión e inténtalo de nuevo.',
        },
      })
    }
  },

  cancelarGeneracion() {
    set({ generacion: GENERACION_INACTIVA })
    toast.info('Generación cancelada', {
      description: 'Si FakeYou ya aceptó el trabajo, el audio aparecerá en el historial al terminar.',
    })
  },

  async borrarHistorial(id) {
    const previo = get().historial
    set({ historial: previo.filter((h) => h.id !== id) })
    try {
      const resp = await fetch(`/api/personajes/historial?id=${encodeURIComponent(id)}`, {
        method: 'DELETE',
      })
      if (!resp.ok) throw new Error('respuesta no ok')
    } catch {
      set({ historial: previo })
      toast.error('No se pudo borrar la generación')
    }
  },
}))

// Encuesta del estado de una generación hasta listo/error (máx. ~4 min).
// Se detiene sola si el usuario cancela o arranca otra generación.
async function encuestaGeneracion(id: string): Promise<void> {
  const store = usePersonajesStore
  for (let intento = 0; intento < 80; intento++) {
    await dormir(3000)
    const actual = store.getState().generacion
    if (actual.id !== id || actual.fase !== 'pendiente') return

    type EstadoRespuesta = { ok?: boolean; estado?: string; mensaje?: string; tituloVoz?: string } | null
    let data: EstadoRespuesta = null
    try {
      const resp = await fetch(`/api/personajes/estado?id=${encodeURIComponent(id)}`, {
        cache: 'no-store',
      })
      data = (await resp.json()) as EstadoRespuesta
    } catch {
      continue // fallo transitorio: siguiente intento
    }
    if (!data?.ok) continue

    if (data.estado === 'listo') {
      const titulo = data.tituloVoz ?? store.getState().generacion.tituloVoz ?? 'personaje'
      store.setState((s) => ({
        generacion: { ...s.generacion, fase: 'listo' },
        audioId: id,
      }))
      toast.success(`Voz de ${titulo} lista`, {
        description: 'Reprodúcela o descárgala desde el reproductor.',
      })
      void store.getState().cargarHistorial()
      return
    }
    if (data.estado === 'error') {
      store.setState((s) => ({
        generacion: { ...s.generacion, fase: 'error', mensaje: data?.mensaje ?? 'La síntesis falló' },
      }))
      toast.error('La síntesis falló', { description: data.mensaje ?? 'FakeYou no completó el trabajo.' })
      void store.getState().cargarHistorial()
      return
    }
    // pendiente → siguiente intento
  }
  store.setState((s) => ({
    generacion: { ...s.generacion, fase: 'error', mensaje: 'La síntesis tardó demasiado (más de 4 minutos).' },
  }))
}
