// Cambiador de Voz DM — procesador AudioWorklet (rama web, espejo de voz_dnd).
//
// ESPEJO de voz_dnd/app/domain/efectos.py: misma cadena, mismas constantes de
// diseño y mismas fórmulas. Cadena (orden acústico del escritorio):
//   Ganancia → Pitch → Formante → Distorsión → RingMod → EQ → Reverb
//
// Contrato de tiempo real (espejo de MotorAudio): process() JAMÁS lanza ni
// bloquea; ante error interno deja pasar la señal sin procesar y lo reporta
// una sola vez por el puerto de mensajes.
//
// Regla de espejo (AGENTS.md): cualquier cambio aquí exige el cambio
// equivalente en voz_dnd/app/domain/efectos.py y viceversa.

const UMBRAL_ACTIVACION = 1e-3;
const PITCH_MARGEN_LECTURA = 64;      // separación mínima lectura/escritura
const PITCH_TAM_GRANO = 512;          // espejo de config.json: motor.tam_grano_pitch
const PITCH_LINEA_SEG = 1;            // línea de retardo de 1 s (igual que numpy zeros(sr))
const DC_BLOCKER_R = 0.995;           // polo del bloqueador DC de la distorsión
const EQ_FREC_LOW_HZ = 120.0;         // estante de graves
const EQ_FREC_MID_HZ = 1200.0;        // campana de medios (voz)
const EQ_FREC_HIGH_HZ = 6000.0;       // estante de agudos
const EQ_Q_MEDIO = 1.0;
const REVERB_COMBOS_MS = [29.7, 31.3, 33.7, 35.9];   // peines de Schroeder
const REVERB_ALLPASS_MS = [7.7, 5.1];                // allpass en serie
const REVERB_G_BASE = 0.70;           // realimentación mínima de los peines
const REVERB_G_RANGO = 0.28;          // realimentación añadida por room_size
const FORMANT_TAM = 512;              // tamaño de FFT del formante (STFT)
const FORMANT_HOP = 128;              // salto de la STFT
const FORMANT_LIFTER = 24;            // quefrencia de liftering cepstral
const FORMANT_BINS = 257;             // TAM/2 + 1
const DOS_PI = Math.PI * 2;

// --------------------------------------------------------------------- //
// FFT radix-2 iterativa (in-place). Convención numpy: directa con e^-i,
// inversa con e^+i y escalado 1/N aplicado por el llamador.
// --------------------------------------------------------------------- //
class FFT {
  constructor(n) {
    this.n = n;
    this.niveles = Math.round(Math.log2(n));
    this.cos = new Float64Array(n / 2);
    this.sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      this.cos[i] = Math.cos((DOS_PI * i) / n);
      this.sin[i] = Math.sin((DOS_PI * i) / n);
    }
    this.rev = new Uint32Array(n);
    for (let i = 0; i < n; i++) {
      let x = i;
      let r = 0;
      for (let j = 0; j < this.niveles; j++) {
        r = (r << 1) | (x & 1);
        x >>= 1;
      }
      this.rev[i] = r;
    }
  }

  transformar(re, im, inversa) {
    const n = this.n;
    const rev = this.rev;
    for (let i = 0; i < n; i++) {
      const j = rev[i];
      if (j > i) {
        let t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    for (let tam = 2; tam <= n; tam <<= 1) {
      const paso = n / tam;
      const mitad = tam >> 1;
      for (let i = 0; i < n; i += tam) {
        for (let j = i, k = 0; j < i + mitad; j++, k += paso) {
          const c = this.cos[k];
          const s = inversa ? this.sin[k] : -this.sin[k];
          const pr = re[j + mitad];
          const pi = im[j + mitad];
          const tr = pr * c - pi * s;
          const ti = pr * s + pi * c;
          re[j + mitad] = re[j] - tr;
          im[j + mitad] = im[j] - ti;
          re[j] += tr;
          im[j] += ti;
        }
      }
    }
  }

  // irfft de un espectro Hermitiano dado en bins 0..N/2 → señal real.
  inversaReal(reBins, imBins, salida) {
    const n = this.n;
    for (let k = 1; k < n / 2; k++) {
      reBins[n - k] = reBins[k];
      imBins[n - k] = -imBins[k];
    }
    imBins[0] = 0;
    imBins[n / 2] = 0;
    this.transformar(reBins, imBins, true);
    const esc = 1 / n;
    for (let i = 0; i < n; i++) salida[i] = reBins[i] * esc;
  }
}

// --------------------------------------------------------------------- //
// Biquads RBJ (espejo de _biquad_shelf / _biquad_peak)
// --------------------------------------------------------------------- //
function coefsBiquad(sr, f0, gainDb, tipo, q) {
  const A = Math.pow(10, gainDb / 40);
  const w0 = (DOS_PI * f0) / sr;
  const cosw = Math.cos(w0);
  const sinw = Math.sin(w0);
  let alpha;
  if (tipo === 'low' || tipo === 'high') {
    alpha = (sinw / 2) * Math.SQRT2;            // estante con S = 1
  } else {
    alpha = sinw / (2 * q);                     // campana
  }
  const dosRaizAAlpha = 2 * Math.sqrt(A) * alpha;
  const a0 = A + 1 + (A - 1) * cosw + dosRaizAAlpha;
  const a1 = -2 * (A - 1 + (A + 1) * cosw);
  const a2 = A + 1 + (A - 1) * cosw - dosRaizAAlpha;
  let b0, b1, b2;
  if (tipo === 'low') {
    b0 = A * (A + 1 - (A - 1) * cosw + dosRaizAAlpha);
    b1 = 2 * A * (A - 1 - (A + 1) * cosw);
    b2 = A * (A + 1 - (A - 1) * cosw - dosRaizAAlpha);
  } else if (tipo === 'high') {
    b0 = A * (A + 1 + (A - 1) * cosw + dosRaizAAlpha);
    b1 = -2 * A * (A - 1 + (A + 1) * cosw);
    b2 = A * (A + 1 + (A - 1) * cosw - dosRaizAAlpha);
  } else {
    b0 = 1 + alpha * A;
    b1 = -2 * cosw;
    b2 = 1 - alpha * A;
  }
  return { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 };
}

class SeccionBiquad {
  constructor() {
    this.activa = false;
    this.b0 = 1; this.b1 = 0; this.b2 = 0;
    this.a1 = 0; this.a2 = 0;
    this.z1 = 0; this.z2 = 0;              // estado DF2T persistente
  }
  procesar(x, n) {
    const { b0, b1, b2, a1, a2 } = this;
    let z1 = this.z1, z2 = this.z2;
    for (let i = 0; i < n; i++) {
      const xn = x[i];
      const y = b0 * xn + z1;
      z1 = b1 * xn + z2 - a1 * y;
      z2 = b2 * xn - a2 * y;
      x[i] = y;
    }
    this.z1 = z1;
    this.z2 = z2;
  }
  reset() { this.z1 = 0; this.z2 = 0; }
}

// --------------------------------------------------------------------- //
// Cadena completa (espejo de efectos.py + FabricaCadena)
// --------------------------------------------------------------------- //
class ProcesadorCadena {
  constructor(sr) {
    this.sr = sr;

    // Ganancia
    this.gananciaActiva = false;
    this.gLin = 1;

    // PitchShifter granular de dos granos
    this.pitchActivo = false;
    this.pitchRatio = 1;
    const L = Math.max(sr * PITCH_LINEA_SEG, PITCH_TAM_GRANO * 4) | 0;
    this.pitchBuf = new Float64Array(L);
    this.pitchL = L;
    this.pitchPosW = 0;
    this.pitchFase = 0;

    // FormantShifter (STFT + liftering cepstral)
    this.formantActivo = false;
    this.formantFactor = 1;
    this.fft = new FFT(FORMANT_TAM);
    this.ventana = new Float64Array(FORMANT_TAM);
    for (let i = 0; i < FORMANT_TAM; i++) {
      // np.hanning(N): 0.5 - 0.5*cos(2·pi·i/(N-1))
      this.ventana[i] = 0.5 - 0.5 * Math.cos((DOS_PI * i) / (FORMANT_TAM - 1));
    }
    this.cola = new Float64Array(FORMANT_TAM * 2);
    this.colaN = 0;
    this.ola = new Float64Array(FORMANT_TAM);
    this.normRun = new Float64Array(FORMANT_TAM);
    this.salida = new Float64Array(FORMANT_TAM * 2);
    this.salidaN = 0;
    this.fftRe = new Float64Array(FORMANT_TAM);
    this.fftIm = new Float64Array(FORMANT_TAM);
    this.espRe = new Float64Array(FORMANT_BINS);   // espectro original (bins 0..256)
    this.espIm = new Float64Array(FORMANT_BINS);
    this.cepsRe = new Float64Array(FORMANT_TAM);   // zona de trabajo del cepstro
    this.cepsIm = new Float64Array(FORMANT_TAM);
    this.logMag = new Float64Array(FORMANT_BINS);
    this.env = new Float64Array(FORMANT_BINS);
    this.envDespl = new Float64Array(FORMANT_BINS);
    this.ratio = new Float64Array(FORMANT_BINS);
    this.marco = new Float64Array(FORMANT_TAM);

    // Distorsión (tanh + bloqueador DC)
    this.distActiva = false;
    this.distK = 1;
    this.distNorm = Math.tanh(1);
    this.distYPrev = 0;
    this.distYdPrev = 0;

    // RingMod
    this.ringActivo = false;
    this.ringW = 0;
    this.ringFase = 0;

    // EQ de 3 bandas
    this.eqLow = new SeccionBiquad();
    this.eqMid = new SeccionBiquad();
    this.eqHigh = new SeccionBiquad();

    // Reverb de Schroeder (4 peines amortiguados + 2 allpass)
    this.reverbActiva = false;
    this.reverbWet = 0;
    this.reverbG = REVERB_G_BASE;
    this.reverbDamp = 0.5;
    this.combs = REVERB_COMBOS_MS.map((ms) => {
      const D = Math.max(Math.round((ms * sr) / 1000), 1);
      return { buf: new Float64Array(D), i: 0, fdPrev: 0 };
    });
    this.allpass = REVERB_ALLPASS_MS.map((ms) => {
      const D = Math.max(Math.round((ms * sr) / 1000), 1);
      return { buf: new Float64Array(D), i: 0, g: 0.5 };
    });

    this.algoActivo = false;
  }

  fijarParametros(p) {
    try {
      const u = UMBRAL_ACTIVACION;

      this.gananciaActiva = Math.abs(p.gain_db) > u;
      this.gLin = Math.pow(10, p.gain_db / 20);

      this.pitchActivo = Math.abs(p.pitch_semitonos) > u;
      this.pitchRatio = Math.pow(2, p.pitch_semitonos / 12);

      this.formantActivo = Math.abs(p.formant_shift - 1) > u;
      this.formantFactor = p.formant_shift;

      this.distActiva = p.distortion_drive > u;
      this.distK = 1 + p.distortion_drive * 24;
      this.distNorm = Math.tanh(this.distK);

      this.ringActivo = p.ring_mod_freq > u;
      this.ringW = (DOS_PI * p.ring_mod_freq) / this.sr;

      this.eqLow.activa = Math.abs(p.eq_low_db) > 0.01;
      if (this.eqLow.activa) {
        Object.assign(this.eqLow, coefsBiquad(this.sr, EQ_FREC_LOW_HZ, p.eq_low_db, 'low'));
      }
      this.eqMid.activa = Math.abs(p.eq_mid_db) > 0.01;
      if (this.eqMid.activa) {
        Object.assign(this.eqMid, coefsBiquad(this.sr, EQ_FREC_MID_HZ, p.eq_mid_db, 'peak', EQ_Q_MEDIO));
      }
      this.eqHigh.activa = Math.abs(p.eq_high_db) > 0.01;
      if (this.eqHigh.activa) {
        Object.assign(this.eqHigh, coefsBiquad(this.sr, EQ_FREC_HIGH_HZ, p.eq_high_db, 'high'));
      }

      this.reverbActiva = p.reverb_room_size > u;
      const wet = Math.min(Math.max(p.reverb_room_size, 0), 1);
      this.reverbWet = wet;
      this.reverbG = REVERB_G_BASE + REVERB_G_RANGO * wet;
      this.reverbDamp = Math.min(Math.max(p.reverb_damping, 0), 1);

      this.algoActivo =
        this.gananciaActiva || this.pitchActivo || this.formantActivo ||
        this.distActiva || this.ringActivo || this.reverbActiva ||
        this.eqLow.activa || this.eqMid.activa || this.eqHigh.activa;
    } catch (e) {
      this.algoActivo = false; // ante datos inválidos: bypass, nunca romper
    }
  }

  reset() {
    this.pitchBuf.fill(0);
    this.pitchPosW = 0;
    this.pitchFase = 0;
    this.colaN = 0;
    this.salidaN = 0;
    this.ola.fill(0);
    this.normRun.fill(0);
    this.distYPrev = 0;
    this.distYdPrev = 0;
    this.ringFase = 0;
    this.eqLow.reset();
    this.eqMid.reset();
    this.eqHigh.reset();
    for (const c of this.combs) { c.buf.fill(0); c.i = 0; c.fdPrev = 0; }
    for (const a of this.allpass) { a.buf.fill(0); a.i = 0; }
  }

  // Lectura con interpolación lineal sobre la línea de retardo (índices
  // fraccionarios, puede ser negativa al arrancar → se lee silencio).
  _leer(pos) {
    const L = this.pitchL;
    const piso = Math.floor(pos);
    const frac = pos - piso;
    const i0 = ((piso % L) + L) % L;
    const i1 = (i0 + 1) % L;
    return this.pitchBuf[i0] * (1 - frac) + this.pitchBuf[i1] * frac;
  }

  _procesarPitch(x, n) {
    const grano = PITCH_TAM_GRANO;
    const margen = PITCH_MARGEN_LECTURA;
    const ratio = this.pitchRatio;
    const buf = this.pitchBuf;
    const L = this.pitchL;
    let posW = this.pitchPosW;
    let fase = this.pitchFase;
    for (let i = 0; i < n; i++) {
      buf[posW] = x[i];
      fase += 1 - ratio;
      if (fase >= grano) fase -= grano;
      else if (fase < 0) fase += grano;
      const dA = margen + fase;
      const dB = margen + ((fase + grano * 0.5) % grano);
      const a = this._leer(posW - dA);
      const b = this._leer(posW - dB);
      const w = 0.5 - 0.5 * Math.cos((DOS_PI * fase) / grano);
      x[i] = a * w + b * (1 - w);
      posW++;
      if (posW >= L) posW = 0;
    }
    this.pitchPosW = posW;
    this.pitchFase = fase;
  }

  _alimentarPitch(x, n) {
    // Con el pitch inactivo la línea se sigue alimentando para que al
    // activarlo en vivo no suenen datos añejos.
    const buf = this.pitchBuf;
    const L = this.pitchL;
    let posW = this.pitchPosW;
    for (let i = 0; i < n; i++) {
      buf[posW] = x[i];
      posW++;
      if (posW >= L) posW = 0;
    }
    this.pitchPosW = posW;
  }

  _procesarMarcoFormante() {
    const T = FORMANT_TAM;
    const H = FORMANT_HOP;
    const bins = FORMANT_BINS;
    const { fft, ventana, fftRe, fftIm, espRe, espIm, cepsRe, cepsIm,
            marco, cola, ola, normRun, salida } = this;

    // FFT del marco ventanaado; se guarda el espectro original (bins 0..256)
    // porque los buffers de trabajo se reutilizan para el cepstro.
    for (let i = 0; i < T; i++) {
      fftRe[i] = cola[i] * ventana[i];
      fftIm[i] = 0;
    }
    fft.transformar(fftRe, fftIm, false);
    for (let k = 0; k < bins; k++) {
      espRe[k] = fftRe[k];
      espIm[k] = fftIm[k];
      this.logMag[k] = Math.log(Math.hypot(espRe[k], espIm[k]) + 1e-10);
    }

    // Cepstro real: irfft del log-magnitude (espectro Hermitiano completo).
    cepsRe.fill(0);
    cepsIm.fill(0);
    for (let k = 0; k < bins; k++) cepsRe[k] = this.logMag[k];
    fft.inversaReal(cepsRe, cepsIm, marco);

    // Liftering: conservar solo quefrencias bajas (±LIFTER).
    for (let q = FORMANT_LIFTER; q < T - FORMANT_LIFTER; q++) marco[q] = 0;

    // Envolvente: rfft del cepstrum lifterado (simétrico → parte real).
    for (let i = 0; i < T; i++) { cepsRe[i] = marco[i]; cepsIm[i] = 0; }
    fft.transformar(cepsRe, cepsIm, false);
    for (let k = 0; k < bins; k++) this.env[k] = Math.exp(cepsRe[k]);

    // Envolvente desplazada por el factor de garganta (np.interp con bordes).
    const f = this.formantFactor;
    for (let k = 0; k < bins; k++) {
      const pos = k * f;
      let val;
      if (pos <= 0) val = this.env[0];
      else if (pos >= bins - 1) val = this.env[bins - 1];
      else {
        const i0 = pos | 0;
        const frac = pos - i0;
        val = this.env[i0] * (1 - frac) + this.env[i0 + 1] * frac;
      }
      this.envDespl[k] = val;
    }

    // Re-síntesis con fase intacta + OLA normalizado por suma de ventanas².
    for (let k = 0; k < bins; k++) {
      let r = this.envDespl[k] / this.env[k];
      if (r < 0.05) r = 0.05;
      else if (r > 20) r = 20;
      this.ratio[k] = r;
      fftRe[k] = espRe[k] * r;
      fftIm[k] = espIm[k] * r;
    }
    fft.inversaReal(fftRe, fftIm, marco);

    for (let i = 0; i < T; i++) {
      ola[i] += marco[i] * ventana[i];
      normRun[i] += ventana[i] * ventana[i];
    }
    let nSal = this.salidaN;
    for (let i = 0; i < H; i++) {
      const norm = normRun[i] > 1e-6 ? normRun[i] : 1e-6;
      salida[nSal++] = ola[i] / norm;
    }
    this.salidaN = nSal;
    for (let i = 0; i + H < T; i++) {
      ola[i] = ola[i + H];
      normRun[i] = normRun[i + H];
    }
    for (let i = T - H; i < T; i++) { ola[i] = 0; normRun[i] = 0; }
  }

  _procesarFormante(x, n) {
    const T = FORMANT_TAM;
    const H = FORMANT_HOP;
    // Asegurar capacidad de la cola (crece si hace falta; nunca se encoge).
    if (this.colaN + n > this.cola.length) {
      const nueva = new Float64Array(Math.max(this.cola.length * 2, this.colaN + n));
      nueva.set(this.cola.subarray(0, this.colaN));
      this.cola = nueva;
    }
    let cn = this.colaN;
    for (let i = 0; i < n; i++) this.cola[cn++] = x[i];
    while (cn >= T) {
      // Capacidad defensiva: cada marco aporta H muestras a la salida. El
      // navegador siempre entrega bloques de 128, pero el contrato RT exige
      // tolerar cualquier n sin escribir fuera del buffer.
      if (this.salidaN + H > this.salida.length) {
        const nueva = new Float64Array(this.salida.length * 2 + H);
        nueva.set(this.salida.subarray(0, this.salidaN));
        this.salida = nueva;
      }
      this._procesarMarcoFormante();
      this.cola.copyWithin(0, H, cn);
      cn -= H;
    }
    this.colaN = cn;

    // Drenar n muestras de la salida (rellenar con silencio al arranque,
    // espejo del np.pad del escritorio).
    const s = this.salida;
    const S = this.salidaN;
    const m = Math.min(n, S);
    for (let i = 0; i < m; i++) x[i] = s[i];
    for (let i = m; i < n; i++) x[i] = 0;
    if (m > 0) s.copyWithin(0, m, S);
    this.salidaN = S - m;
  }

  _procesarDistorsion(x, n) {
    const k = this.distK;
    const norm = this.distNorm;
    let yPrev = this.distYPrev;
    let ydPrev = this.distYdPrev;
    for (let i = 0; i < n; i++) {
      let v = x[i];
      if (v > 1) v = 1; else if (v < -1) v = -1;
      const y = Math.tanh(k * v) / norm;
      const yd = y - yPrev + DC_BLOCKER_R * ydPrev;
      yPrev = y;
      ydPrev = yd;
      x[i] = yd;
    }
    this.distYPrev = yPrev;
    this.distYdPrev = ydPrev;
  }

  _procesarRing(x, n) {
    const w = this.ringW;
    let fase = this.ringFase;
    for (let i = 0; i < n; i++) {
      fase += w;
      if (fase >= DOS_PI) fase -= DOS_PI;
      x[i] *= Math.sin(fase);
    }
    this.ringFase = fase;
  }

  _procesarReverb(x, n) {
    const g = this.reverbG;
    const damp = this.reverbDamp;
    const wet = this.reverbWet;
    const unMenosDamp = 1 - damp;
    const combs = this.combs;
    const allpass = this.allpass;
    for (let i = 0; i < n; i++) {
      const xn = x[i];
      let mojado = 0;
      for (let ci = 0; ci < combs.length; ci++) {
        const comb = combs[ci];
        const yd = comb.buf[comb.i];
        const fd = unMenosDamp * yd + damp * comb.fdPrev;
        comb.fdPrev = fd;
        const y = xn + g * fd;
        comb.buf[comb.i] = y;
        comb.i++;
        if (comb.i >= comb.buf.length) comb.i = 0;
        mojado += y;
      }
      mojado *= 0.25;
      for (let ai = 0; ai < allpass.length; ai++) {
        const ap = allpass[ai];
        const bo = ap.buf[ap.i];
        const y = bo - mojado;
        ap.buf[ap.i] = mojado + bo * ap.g;
        ap.i++;
        if (ap.i >= ap.buf.length) ap.i = 0;
        mojado = y;
      }
      let mezcla = xn * (1 - 0.35 * wet) + mojado * 1.3 * wet;
      if (mezcla > 1) mezcla = 1; else if (mezcla < -1) mezcla = -1;
      x[i] = mezcla;
    }
  }

  procesar(entrada, salida, n) {
    // 0) Copia de trabajo (in-place sobre el buffer interno).
    for (let i = 0; i < n; i++) salida[i] = entrada[i];

    // 1) Ganancia
    if (this.gananciaActiva) {
      for (let i = 0; i < n; i++) salida[i] *= this.gLin;
    }

    // 2) Pitch (la línea se alimenta siempre; espejo del bypass de escritorio)
    if (this.pitchActivo) this._procesarPitch(salida, n);
    else this._alimentarPitch(salida, n);

    // 3) Formante
    if (this.formantActivo) this._procesarFormante(salida, n);

    // 4) Distorsión
    if (this.distActiva) this._procesarDistorsion(salida, n);

    // 5) RingMod
    if (this.ringActivo) this._procesarRing(salida, n);

    // 6) EQ (graves → medios → agudos)
    if (this.eqLow.activa) this.eqLow.procesar(salida, n);
    if (this.eqMid.activa) this.eqMid.procesar(salida, n);
    if (this.eqHigh.activa) this.eqHigh.procesar(salida, n);

    // 7) Reverb
    if (this.reverbActiva) this._procesarReverb(salida, n);
  }
}

// --------------------------------------------------------------------- //
// Procesador AudioWorklet
// --------------------------------------------------------------------- //
class ProcesadorVoz extends AudioWorkletProcessor {
  constructor(opciones) {
    super();
    this.cadena = new ProcesadorCadena(sampleRate);
    this.errorReportado = false;
    const iniciales = opciones && opciones.processorOptions && opciones.processorOptions.params;
    if (iniciales) this.cadena.fijarParametros(iniciales);
    this.port.onmessage = (evento) => {
      const d = evento.data || {};
      try {
        if (d.tipo === 'params' && d.params) {
          this.cadena.fijarParametros(d.params);
          if (d.reset) this.cadena.reset();
        } else if (d.tipo === 'reset') {
          this.cadena.reset();
        }
      } catch (e) {
        this._reportarError(e);
      }
    };
  }

  _reportarError(e) {
    if (this.errorReportado) return;
    this.errorReportado = true;
    this.port.postMessage({
      tipo: 'error-interno',
      mensaje: e && e.message ? e.message : 'error desconocido en el worklet',
    });
  }

  process(entradas, salidas) {
    const entrada = entradas[0] && entradas[0][0] ? entradas[0][0] : null;
    const salida = salidas[0][0];
    if (!salida) return true;
    if (!entrada) {
      salida.fill(0);
      return true;
    }
    const n = Math.min(entrada.length, salida.length);
    try {
      if (this.cadena.algoActivo) {
        this.cadena.procesar(entrada, salida, n);
      } else {
        for (let i = 0; i < n; i++) salida[i] = entrada[i]; // bypass (Neutral)
      }
    } catch (e) {
      // Contrato RT: jamás romper el stream; degradar a paso recto.
      for (let i = 0; i < n; i++) salida[i] = entrada[i];
      this._reportarError(e);
    }
    return true;
  }
}

registerProcessor('cambiador-voz', ProcesadorVoz);
