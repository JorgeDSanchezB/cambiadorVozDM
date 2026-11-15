// Motor de audio web — espejo funcional de voz_dnd/app/engine/motor_audio.py.
//
// Cadena del micrófono (full-duplex):
//   mic → [cambiador-voz (worklet)] → analizador → ganancia monitor → salida
//                                      └→ destino de grabación (post-DSP)
// Cadena de lectura/TTS (nodo aparte, sin contención con el micrófono):
//   buffer TTS → [cambiador-voz] → salida
// Durante la lectura el monitor del micrófono se silencia (espejo del
// "swap" de MotorAudio.reproducir: nunca suenan los dos a la vez).

import { errorVoz } from './errores'
import type { ParametrosDSP } from './tipos'

export type EstadoMotor = 'detenido' | 'iniciando' | 'activo' | 'pausado'

export interface ResultadoGrabacion {
  blob: Blob
  url: string
  extension: string
}

const URL_WORKLET = '/worklets/cambiador-voz.js'
const RMS_PISO = 1e-12

function crearNodoVoz(ctx: BaseAudioContext, params: ParametrosDSP | null): AudioWorkletNode {
  return new AudioWorkletNode(ctx, 'cambiador-voz', {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    channelCount: 1,
    channelCountMode: 'explicit',
    processorOptions: params ? { params } : {},
  })
}

function elegirMimeGrabacion(): string | null {
  const candidatos = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ]
  if (typeof MediaRecorder === 'undefined') return null
  return candidatos.find((m) => MediaRecorder.isTypeSupported(m)) ?? null
}

class MotorAudio {
  private ctx: AudioContext | null = null
  private nodoVoz: AudioWorkletNode | null = null
  private nodoLectura: AudioWorkletNode | null = null
  private gainLectura: GainNode | null = null
  private micStream: MediaStream | null = null
  private micSource: MediaStreamAudioSourceNode | null = null
  private monitorGain: GainNode | null = null
  private analizador: AnalyserNode | null = null
  private bufferAnalisis: Float32Array | null = null
  private grabDest: MediaStreamAudioDestinationNode | null = null
  private recorder: MediaRecorder | null = null
  private trozos: Blob[] = []
  private fuenteActiva: AudioBufferSourceNode | null = null
  private parametrosActuales: ParametrosDSP | null = null

  estado: EstadoMotor = 'detenido'
  monitorActivo = true
  volumenMonitor = 1
  srObjetivo = 48000
  onCambio: (() => void) | null = null
  onMicrofonoPerdido: (() => void) | null = null
  onDegradacionWorklet: ((error: Error) => void) | null = null

  get srEfectivo(): number | null {
    return this.ctx ? this.ctx.sampleRate : null
  }

  get contextoSuspendido(): boolean {
    return this.ctx !== null && this.ctx.state === 'suspended'
  }

  private notificar() {
    this.onCambio?.()
  }

  // ------------------------------------------------------------------ //
  // Contexto y módulo del worklet
  // ------------------------------------------------------------------ //
  async ensureContexto(): Promise<AudioContext> {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') {
        await this.ctx.resume().catch(() => {
          /* política de autoplay: el usuario reintenta con un clic */
        })
      }
      return this.ctx
    }
    if (typeof window === 'undefined') throw errorVoz('contexto_bloqueado', 'sin ventana')
    let ctx: AudioContext
    try {
      ctx = new AudioContext({ sampleRate: this.srObjetivo, latencyHint: 'interactive' })
    } catch {
      ctx = new AudioContext()
    }
    if (ctx.state === 'suspended') {
      await ctx.resume().catch(() => {
        /* se reanudará con el siguiente gesto del usuario */
      })
    }
    if (!ctx.audioWorklet || typeof AudioWorkletNode === 'undefined') {
      throw errorVoz('worklet_no_soportado')
    }
    try {
      await ctx.audioWorklet.addModule(URL_WORKLET)
    } catch (e) {
      throw errorVoz('worklet_no_soportado', e instanceof Error ? e.message : '')
    }
    // Cadena de lectura (TTS/demo): nodo aparte del micrófono.
    this.nodoLectura = crearNodoVoz(ctx, this.parametrosActuales)
    this.gainLectura = ctx.createGain()
    this.nodoLectura.connect(this.gainLectura)
    this.gainLectura.connect(ctx.destination)
    this.nodoLectura.port.onmessage = (ev) => this._manejarMensajeWorklet(ev.data)
    this.ctx = ctx
    return ctx
  }

  private _manejarMensajeWorklet(dato: unknown): void {
    const d = dato as { tipo?: string; mensaje?: string }
    if (d && d.tipo === 'error-interno') {
      this.onDegradacionWorklet?.(new Error(d.mensaje ?? 'error del worklet'))
    }
  }

  // ------------------------------------------------------------------ //
  // Micrófono
  // ------------------------------------------------------------------ //
  async iniciarMic(dispositivoId: string | null): Promise<void> {
    if (this.estado === 'activo' || this.estado === 'iniciando') return
    const ctx = await this.ensureContexto()
    this.estado = 'iniciando'
    this.notificar()

    const audio: MediaTrackConstraints = {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1,
    }
    if (dispositivoId) audio.deviceId = { exact: dispositivoId }

    const stream = await navigator.mediaDevices.getUserMedia({ audio }).catch((e) => {
      // Jamás dejar el motor atascado en "iniciando" si el micrófono falla.
      this.estado = 'detenido'
      this.notificar()
      throw e
    })
    this.micStream = stream
    this.micSource = ctx.createMediaStreamSource(stream)

    this.nodoVoz = crearNodoVoz(ctx, this.parametrosActuales)
    this.nodoVoz.port.onmessage = (ev) => this._manejarMensajeWorklet(ev.data)

    this.analizador = ctx.createAnalyser()
    this.analizador.fftSize = 1024
    this.analizador.smoothingTimeConstant = 0.4
    this.bufferAnalisis = new Float32Array(this.analizador.fftSize)

    this.monitorGain = ctx.createGain()
    this.monitorGain.gain.value = this.monitorActivo ? this.volumenMonitor : 0

    this.micSource.connect(this.nodoVoz)
    this.nodoVoz.connect(this.analizador)
    this.analizador.connect(this.monitorGain)
    this.monitorGain.connect(ctx.destination)

    const pista = stream.getAudioTracks()[0]
    pista?.addEventListener('ended', () => {
      if (this.estado === 'activo' || this.estado === 'pausado') {
        this._limpiarMic()
        this.estado = 'detenido'
        this.notificar()
        this.onMicrofonoPerdido?.()
      }
    })

    this.estado = 'activo'
    this.notificar()
  }

  private _limpiarMic(): void {
    if (this.recorder && this.recorder.state !== 'inactive') {
      try { this.recorder.stop() } catch { /* sin residuos */ }
    }
    this.micSource?.disconnect()
    this.nodoVoz?.disconnect()
    this.analizador?.disconnect()
    this.monitorGain?.disconnect()
    this.nodoVoz?.disconnect(this.grabDest ?? undefined as unknown as AudioNode)
    this.micStream?.getTracks().forEach((t) => t.stop())
    this.micSource = null
    this.nodoVoz = null
    this.analizador = null
    this.monitorGain = null
    this.micStream = null
  }

  pararMic(): void {
    if (this.estado === 'detenido') return
    this._limpiarMic()
    this.estado = 'detenido'
    this.notificar()
  }

  pausar(): void {
    this.micStream?.getAudioTracks().forEach((t) => { t.enabled = false })
    this.estado = 'pausado'
    this.notificar()
  }

  reanudar(): void {
    this.micStream?.getAudioTracks().forEach((t) => { t.enabled = true })
    this.estado = 'activo'
    this.notificar()
  }

  // ------------------------------------------------------------------ //
  // Parámetros de la voz (a ambos nodos: micrófono y lectura)
  // ------------------------------------------------------------------ //
  fijarParametros(params: ParametrosDSP, opts?: { reset?: boolean }): void {
    this.parametrosActuales = params
    const mensaje = { tipo: 'params', params, reset: opts?.reset ?? false }
    try { this.nodoVoz?.port.postMessage(mensaje) } catch { /* nodo aún no listo */ }
    try { this.nodoLectura?.port.postMessage(mensaje) } catch { /* nodo aún no listo */ }
  }

  // Solo la cadena de lectura (para "Probar voz" sin cambiar la activa).
  fijarParametrosLectura(params: ParametrosDSP): void {
    try {
      this.nodoLectura?.port.postMessage({ tipo: 'params', params, reset: true })
    } catch { /* sin nodo: nada que hacer */ }
  }

  // Devuelve la cadena de lectura a los parámetros de la voz activa.
  restaurarParametrosLectura(): void {
    if (this.parametrosActuales) {
      try {
        this.nodoLectura?.port.postMessage({
          tipo: 'params',
          params: this.parametrosActuales,
          reset: true,
        })
      } catch { /* sin nodo: nada que hacer */ }
    }
  }

  // ------------------------------------------------------------------ //
  // Monitor
  // ------------------------------------------------------------------ //
  private _aplicarMonitor(): void {
    if (!this.monitorGain || !this.ctx) return
    const objetivo = this.monitorActivo ? this.volumenMonitor : 0
    this.monitorGain.gain.setTargetAtTime(objetivo, this.ctx.currentTime, 0.02)
  }

  setMonitor(activo: boolean): void {
    this.monitorActivo = activo
    this._aplicarMonitor()
  }

  setVolumenMonitor(v: number): void {
    this.volumenMonitor = Math.min(Math.max(v, 0), 1)
    this._aplicarMonitor()
  }

  // Previa del editor (espejo del "preview 2 s" del escritorio): sube el
  // monitor durante `ms` milisegundos y lo devuelve a su estado anterior.
  previa(ms: number): void {
    if (!this.monitorGain || !this.ctx || this.estado === 'detenido') return
    const ahora = this.ctx.currentTime
    const final = this.monitorActivo ? this.volumenMonitor : 0
    this.monitorGain.gain.cancelScheduledValues(ahora)
    this.monitorGain.gain.setTargetAtTime(this.volumenMonitor, ahora, 0.02)
    this.monitorGain.gain.setTargetAtTime(final, ahora + ms / 1000, 0.05)
  }

  setSrObjetivo(sr: number): void {
    this.srObjetivo = sr
  }

  // ------------------------------------------------------------------ //
  // Medidor de nivel (espejo de rms_a_db: RMS → dBFS con piso -90)
  // ------------------------------------------------------------------ //
  nivelDb(): number {
    if (!this.analizador || !this.bufferAnalisis) return -90
    this.analizador.getFloatTimeDomainData(this.bufferAnalisis)
    let suma = 0
    for (let i = 0; i < this.bufferAnalisis.length; i++) suma += this.bufferAnalisis[i] * this.bufferAnalisis[i]
    const rms = Math.sqrt(suma / this.bufferAnalisis.length)
    if (rms < RMS_PISO) return -90
    return 20 * Math.log10(rms)
  }

  // ------------------------------------------------------------------ //
  // Grabación post-DSP (espejo de gestor_grabacion: nunca se pierde audio,
  // un archivo vacío se reporta en vez de descargarse)
  // ------------------------------------------------------------------ //
  async grabarInicio(): Promise<void> {
    if (this.estado !== 'activo' && this.estado !== 'pausado') {
      throw errorVoz('mic_ausente', 'inicia el micrófono antes de grabar')
    }
    const ctx = this.ctx
    if (!ctx || !this.nodoVoz) throw errorVoz('desconocido', 'motor sin nodos')
    if (!this.grabDest) {
      this.grabDest = ctx.createMediaStreamDestination()
    }
    this.nodoVoz.connect(this.grabDest)
    const mime = elegirMimeGrabacion()
    this.trozos = []
    this.recorder = new MediaRecorder(this.grabDest.stream, mime ? { mimeType: mime } : undefined)
    this.recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) this.trozos.push(ev.data)
    }
    this.recorder.start(250)
  }

  grabarFin(): Promise<ResultadoGrabacion> {
    return new Promise((resolver, rechazar) => {
      const r = this.recorder
      if (!r || r.state === 'inactive') {
        rechazar(errorVoz('grabacion_vacia', 'no hay grabación en curso'))
        return
      }
      r.onstop = () => {
        const trozos = this.trozos
        this.trozos = []
        this.recorder = null
        this.nodoVoz?.disconnect(this.grabDest ?? undefined as unknown as AudioNode)
        const tipo = r.mimeType || 'audio/webm'
        if (trozos.length === 0) {
          rechazar(errorVoz('grabacion_vacia'))
          return
        }
        const blob = new Blob(trozos, { type: tipo })
        if (blob.size === 0) {
          rechazar(errorVoz('grabacion_vacia'))
          return
        }
        const extension = tipo.includes('mp4') ? 'm4a' : tipo.includes('ogg') ? 'ogg' : 'webm'
        resolver({ blob, url: URL.createObjectURL(blob), extension })
      }
      r.stop()
    })
  }

  estaGrabando(): boolean {
    return this.recorder !== null && this.recorder.state === 'recording'
  }

  // ------------------------------------------------------------------ //
  // Reproducción de TTS/demo a través de la cadena de voz
  // ------------------------------------------------------------------ //
  async decodificar(datos: ArrayBuffer): Promise<AudioBuffer> {
    const ctx = await this.ensureContexto()
    return ctx.decodeAudioData(datos)
  }

  reproducirBuffer(buffer: AudioBuffer, conEfectos: boolean): Promise<void> {
    return new Promise((resolver) => {
      if (!this.ctx) {
        resolver()
        return
      }
      this.detenerLectura()
      const fuente = this.ctx.createBufferSource()
      fuente.buffer = buffer
      const destino = conEfectos && this.nodoLectura ? this.nodoLectura : this.ctx.destination
      fuente.connect(destino)
      // Espejo del swap del escritorio: durante la lectura el micrófono no
      // suena por el monitor (los dos audios jamás se superponen).
      const silenciarMonitor = conEfectos && this.monitorActivo && this.estado === 'activo'
      if (silenciarMonitor) this._aplicarMonitorSilencio(true)
      fuente.onended = () => {
        if (fuente === this.fuenteActiva) this.fuenteActiva = null
        if (silenciarMonitor) this._aplicarMonitorSilencio(false)
        resolver()
      }
      this.fuenteActiva = fuente
      fuente.start()
    })
  }

  private _aplicarMonitorSilencio(silenciar: boolean): void {
    if (!this.monitorGain || !this.ctx) return
    const objetivo = silenciar ? 0 : this.monitorActivo ? this.volumenMonitor : 0
    this.monitorGain.gain.setTargetAtTime(objetivo, this.ctx.currentTime, 0.02)
  }

  detenerLectura(): void {
    if (this.fuenteActiva) {
      const fuente = this.fuenteActiva
      this.fuenteActiva = null
      try { fuente.stop() } catch { /* ya detenida */ }
    }
  }

  // ------------------------------------------------------------------ //
  // Render offline (descargar WAV con la voz aplicada)
  // ------------------------------------------------------------------ //
  async renderizarOffline(buffer: AudioBuffer, params: ParametrosDSP): Promise<AudioBuffer> {
    if (typeof window === 'undefined') throw errorVoz('desconocido', 'sin ventana')
    const sr = buffer.sampleRate
    const colaReverb = Math.ceil(sr * 0.6)
    const offline = new OfflineAudioContext(1, buffer.length + colaReverb, sr)
    await offline.audioWorklet.addModule(URL_WORKLET)
    const nodo = crearNodoVoz(offline, params)
    const fuente = offline.createBufferSource()
    fuente.buffer = buffer
    fuente.connect(nodo)
    nodo.connect(offline.destination)
    fuente.start()
    return offline.startRendering()
  }

  // ------------------------------------------------------------------ //
  // Cierre completo (al desmontar la app)
  // ------------------------------------------------------------------ //
  cerrar(): void {
    this.detenerLectura()
    this._limpiarMic()
    this.nodoLectura?.disconnect()
    this.gainLectura?.disconnect()
    this.nodoLectura = null
    this.gainLectura = null
    this.ctx?.close().catch(() => { /* ya cerrado */ })
    this.ctx = null
    this.estado = 'detenido'
  }
}

export const motor = new MotorAudio()
