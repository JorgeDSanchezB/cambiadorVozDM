// Tipos del dominio de voz — espejo de voz_dnd/app/domain/models.py (rama web).

export interface ParametrosDSP {
  pitch_semitonos: number
  formant_shift: number
  reverb_room_size: number
  reverb_damping: number
  distortion_drive: number
  gain_db: number
  ring_mod_freq: number
  eq_low_db: number
  eq_mid_db: number
  eq_high_db: number
}

export type ClaveParametro = keyof ParametrosDSP

// Espejo de data/parametros.json: fuente única de rangos para los sliders.
export interface DefParametro {
  etiqueta: string
  min: number
  max: number
  paso: number
  neutro: number
  unidad: string
}

export interface Voz {
  id: string
  nombre: string
  tipo: 'DSP' | 'IA'
  icono: string
  color: string
  atajo: string | null
  parametros_dsp: ParametrosDSP
  personalizada?: boolean
}

export interface CatalogoVoces {
  version: number
  generado_por: string
  fuente: string
  voces: Voz[]
}

export interface Ajustes {
  dispositivoEntrada: string | null
  monitor: boolean
  volumenMonitor: number
  atajos: boolean
  srObjetivo: number
}
