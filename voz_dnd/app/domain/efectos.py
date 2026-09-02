"""Cadena de efectos DSP en tiempo real — el corazón del programa (Fase 4).

Contrato en tiempo real (invariante que respeta el MotorAudio):
  * `procesar()` recibe bloques float32 de forma (frames, 1) y devuelve
    la misma forma.
  * Ningún efecto hace I/O, toca Qt ni toma locks; todo el estado es local.
  * Los buffers internos están PRE-ALOCADOS en el constructor; por bloque
    solo se crean arrays pequeños de trabajo (aceptable a 48 kHz).
  * El estado persiste entre bloques (reverb continua, fases de osciladores,
    estados de filtro) y `reset()` lo limpia al cambiar de voz.

Efectos disponibles (orden de la cadena, ver FabricaCadena):
  Ganancia → PitchShifter → FormantShifter → Distorsion → RingMod
  → EfectoEQ → ReverbSchroeder

Todos están implementados con numpy/scipy y son vectorizados (sin bucles
por muestra en Python), lo que garantiza CPU baja con buffers de 128-256.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np
from scipy.signal import lfilter

# Constantes de diseño (nombradas, no números mágicos dispersos)
RMS_PISO = 1e-12               # evita log(0) en el medidor de nivel
DC_BLOCKER_R = 0.995           # polo del bloqueador DC de la distorsión
PITCH_MARGEN_LECTURA = 64      # separación mínima lectura/escritura (muestras)
EQ_FREC_LOW_HZ = 120.0         # estante de graves
EQ_FREC_MID_HZ = 1200.0        # campana de medios (voz)
EQ_FREC_HIGH_HZ = 6000.0       # estante de agudos
EQ_Q_MEDIO = 1.0
REVERB_COMBOS_MS = (29.7, 31.3, 33.7, 35.9)   # retardos de Schroeder
REVERB_ALLPASS_MS = (7.7, 5.1)
REVERB_G_BASE = 0.70           # realimentación mínima de los peines
REVERB_G_RANGO = 0.28          # realimentación añadida por "room_size"


def db_a_lineal(db: float) -> float:
    return 10.0 ** (db / 20.0)


def rms_a_db(x: np.ndarray) -> float:
    """Convierte el RMS de un bloque a dBFS (para el medidor de nivel)."""
    if x.size == 0:
        return -90.0
    raiz = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))
    if raiz < RMS_PISO:
        return -90.0
    return 20.0 * math.log10(raiz)


class IEfectoDSP(ABC):
    """Contrato de un eslabón de la cadena (Chain of Responsibility)."""

    @abstractmethod
    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        """Procesa un bloque (frames, 1) float32 y devuelve otro igual."""

    def reset(self) -> None:
        """Limpia el estado interno (se llama al cambiar de voz)."""

    @property
    def latencia_muestras(self) -> int:
        """Latencia algorítmica introducida por el efecto (0 = nula)."""
        return 0


# --------------------------------------------------------------------------- #
# 1) Ganancia
# --------------------------------------------------------------------------- #
class Ganancia(IEfectoDSP):
    def __init__(self, gain_db: float):
        self._g = db_a_lineal(gain_db)

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        return (bloque * np.float32(self._g)).astype(np.float32)


# --------------------------------------------------------------------------- #
# 2) Pitch shifter granular (armonizador de dos granos)
# --------------------------------------------------------------------------- #
class PitchShifter(IEfectoDSP):
    """Desplazamiento de tono por línea de retardo con dos cabezales.

    Método: dos punteros de lectura avanzan a razón `ratio` respecto a la
    escritura; sus fases sierra se envuelven cada `tam_grano` muestras y se
    solapan con ventanas Hann complementarias (w(x) + w(x + 1/2) = 1), lo
    que elimina los chasquidos en el empalme de granos.

    Latencia algorítmica ≈ margen + tam_grano muestras (arranque del delay
    line). Consumo de CPU: mínimo (solo interpolación vectorizada).
    """

    def __init__(self, sr: int, semitonos: float, tam_grano: int = 1024):
        self._ratio = 2.0 ** (semitonos / 12.0)
        self._grano = int(max(256, tam_grano))
        self._buf = np.zeros(sr, dtype=np.float64)  # línea de retardo de 1 s
        self._pos_w = 0                             # posición de escritura
        self._fase = 0.0                            # fase sierra del grano A

    @property
    def latencia_muestras(self) -> int:
        return PITCH_MARGEN_LECTURA + self._grano

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        if abs(self._ratio - 1.0) < 1e-4:            # ratio neutro → bypass
            return bloque
        n = bloque.shape[0]
        L = self._buf.size

        # 1) Escritura de la entrada en la línea de retardo
        pos_base = self._pos_w
        idx_w = (pos_base + np.arange(n)) % L
        self._buf[idx_w] = bloque[:, 0]
        self._pos_w = int((pos_base + n) % L)

        # 2) Fase sierra por muestra: avanza (1 - ratio) → Doppler
        fase = (self._fase + (1.0 - self._ratio) * np.arange(1, n + 1)) % self._grano
        self._fase = float(fase[-1])

        # 3) Dos taps de lectura con retraso distinto y crossfade Hann
        margen = float(PITCH_MARGEN_LECTURA)   # separación mínima de la escritura
        d_a = margen + fase
        d_b = margen + (fase + self._grano * 0.5) % self._grano
        a = self._leer(pos_base + np.arange(n) - d_a)
        b = self._leer(pos_base + np.arange(n) - d_b)
        w_a = 0.5 - 0.5 * np.cos(2.0 * np.pi * fase / self._grano)
        y = a * w_a + b * (1.0 - w_a)
        return y.astype(np.float32).reshape(-1, 1)

    def _leer(self, posiciones: np.ndarray) -> np.ndarray:
        """Lectura con interpolación lineal (índices fraccionarios, mod L)."""
        L = self._buf.size
        i0 = np.floor(posiciones).astype(np.int64) % L
        i1 = (i0 + 1) % L
        frac = posiciones - np.floor(posiciones)
        return self._buf[i0] * (1.0 - frac) + self._buf[i1] * frac


# --------------------------------------------------------------------------- #
# 3) Desplazador de formantes (envolvente espectral por cepstro)
# --------------------------------------------------------------------------- #
class FormantShifter(IEfectoDSP):
    """Cambia el "tamaño de garganta" sin cambiar el tono musical.

    Implementación: STFT con solapamiento (ventana Hann 512, hop 128).
    Solo se modifica la MAGNITUD del espectro (la fase queda intacta), por
    lo que la reconstrucción OLA es perfecta y sin artefactos entre bloques.
    La envolvente espectral se extrae por liftering cepstral y se re-muestrea
    según el factor: factor < 1 = garganta pequeña/formantes agudos,
    factor > 1 = garganta grande/formantes graves.

    Latencia: TAM_FFT muestras (≈ 10.7 ms @ 48 kHz) — elegido para mantener
    el objetivo de latencia total < 50 ms junto al PitchShifter.
    """

    TAM_FFT = 512
    HOP = 128
    LIFTER_QUEFRENCIA = 24

    def __init__(self, sr: int, factor: float):
        self._factor = float(factor)
        self._ventana = np.hanning(self.TAM_FFT)
        self._bins = np.arange(self.TAM_FFT // 2 + 1, dtype=np.float64)
        self._cola_in = np.zeros(0)
        self._ola = np.zeros(self.TAM_FFT)
        self._norm_run = np.zeros(self.TAM_FFT)
        self._salida = np.zeros(0)

    @property
    def latencia_muestras(self) -> int:
        return self.TAM_FFT

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        if abs(self._factor - 1.0) < 1e-3:
            return bloque
        self._cola_in = np.concatenate([self._cola_in, bloque[:, 0].astype(np.float64)])
        while self._cola_in.size >= self.TAM_FFT:
            self._procesar_marco(self._cola_in[: self.TAM_FFT])
            self._cola_in = self._cola_in[self.HOP:]

        n = bloque.shape[0]
        if self._salida.size >= n:
            out = self._salida[:n]
            self._salida = self._salida[n:]
        else:  # arranque: todavía no hay suficiente solapamiento
            out = np.pad(self._salida, (0, n - self._salida.size))
            self._salida = np.zeros(0)
        return out.astype(np.float32).reshape(-1, 1)

    def _procesar_marco(self, marco: np.ndarray) -> None:
        espec = np.fft.rfft(marco * self._ventana)
        mag = np.abs(espec) + 1e-10

        # Envolvente espectral por cepstro (liftering)
        ceps = np.fft.irfft(np.log(mag), n=self.TAM_FFT)
        ceps[self.LIFTER_QUEFRENCIA: self.TAM_FFT - self.LIFTER_QUEFRENCIA] = 0.0
        env = np.exp(np.fft.rfft(ceps).real)

        # Envolvente desplazada según el factor de garganta
        env_despl = np.interp(self._bins * self._factor, self._bins, env,
                              left=env[0], right=env[-1])
        ratio = np.clip(env_despl / env, 0.05, 20.0)

        # Resíntesis (fase intacta) + OLA normalizado por suma de ventanas²
        sintesis = np.fft.irfft(espec * ratio, n=self.TAM_FFT)
        self._ola += sintesis * self._ventana
        self._norm_run += self._ventana ** 2
        paso = self._ola[: self.HOP] / np.maximum(self._norm_run[: self.HOP], 1e-6)
        self._salida = np.concatenate([self._salida, paso])
        self._ola = np.concatenate([self._ola[self.HOP:], np.zeros(self.HOP)])
        self._norm_run = np.concatenate([self._norm_run[self.HOP:], np.zeros(self.HOP)])

    def reset(self) -> None:
        self._cola_in = np.zeros(0)
        self._ola = np.zeros(self.TAM_FFT)
        self._norm_run = np.zeros(self.TAM_FFT)
        self._salida = np.zeros(0)


# --------------------------------------------------------------------------- #
# 4) Distorsión (waveshaping tanh + bloqueador DC)
# --------------------------------------------------------------------------- #
class Distorsion(IEfectoDSP):
    def __init__(self, drive: float):
        self._k = 1.0 + drive * 24.0          # drive 0..1 → dureza 1..25
        self._norm = math.tanh(self._k)       # normaliza la amplitud de salida
        self._zi_dc = np.zeros(1)             # estado del bloqueador DC

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = np.clip(bloque[:, 0].astype(np.float64), -1.0, 1.0)
        y = np.tanh(self._k * x) / self._norm
        # Bloqueador DC: y[n] = x[n] - x[n-1] + R·y[n-1]  (lfilter con estado)
        y, self._zi_dc = lfilter([1.0, -1.0], [1.0, -DC_BLOCKER_R], y, zi=self._zi_dc)
        return y.astype(np.float32).reshape(-1, 1)

    def reset(self) -> None:
        self._zi_dc = np.zeros(1)


# --------------------------------------------------------------------------- #
# 5) Ring modulator (voz robótica / aberración)
# --------------------------------------------------------------------------- #
class RingMod(IEfectoDSP):
    def __init__(self, sr: int, freq_hz: float):
        self._f = float(freq_hz)
        self._dos_pi_f_sobre_sr = 2.0 * math.pi * self._f / sr
        self._fase = 0.0

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        n = bloque.shape[0]
        fase = (self._fase + self._dos_pi_f_sobre_sr * np.arange(1, n + 1)) % (2.0 * math.pi)
        self._fase = float(fase[-1])
        portadora = np.sin(fase)
        return (bloque[:, 0] * portadora).astype(np.float32).reshape(-1, 1)

    def reset(self) -> None:
        self._fase = 0.0


# --------------------------------------------------------------------------- #
# 6) EQ de 3 bandas (biquads RBJ con estado persistente)
# --------------------------------------------------------------------------- #
class _Biquad:
    """Biquad con estado entre bloques vía scipy.signal.lfilter (vectorizado)."""

    def __init__(self, b: tuple[float, float, float], a: tuple[float, float, float]):
        self._b = np.asarray(b, dtype=np.float64)
        self._a = np.asarray(a, dtype=np.float64)
        self._zi = np.zeros(2)

    def procesar(self, x: np.ndarray) -> np.ndarray:
        y, self._zi = lfilter(self._b, self._a, x, zi=self._zi)
        return y

    def reset(self) -> None:
        self._zi = np.zeros(2)


def _biquad_shelf(sr: int, f0: float, gain_db: float, tipo: str) -> tuple[
        tuple[float, float, float], tuple[float, float, float]]:
    """Estante low/high del cookbook RBJ (pendiente S = 1)."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / sr
    cosw, sinw = math.cos(w0), math.sin(w0)
    alpha = sinw / 2.0 * math.sqrt(2.0)              # S = 1
    dos_raiz_A_alpha = 2.0 * math.sqrt(A) * alpha
    a0 = (A + 1.0) + (A - 1.0) * cosw + dos_raiz_A_alpha
    a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cosw)
    a2 = (A + 1.0) + (A - 1.0) * cosw - dos_raiz_A_alpha
    if tipo == "low":
        b0 = A * ((A + 1.0) - (A - 1.0) * cosw + dos_raiz_A_alpha)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cosw)
        b2 = A * ((A + 1.0) - (A - 1.0) * cosw - dos_raiz_A_alpha)
    else:  # "high"
        b0 = A * ((A + 1.0) + (A - 1.0) * cosw + dos_raiz_A_alpha)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cosw)
        b2 = A * ((A + 1.0) + (A - 1.0) * cosw - dos_raiz_A_alpha)
    return ((b0 / a0, b1 / a0, b2 / a0), (1.0, a1 / a0, a2 / a0))


def _biquad_peak(sr: int, f0: float, gain_db: float, q: float) -> tuple[
        tuple[float, float, float], tuple[float, float, float]]:
    """Campana (peaking EQ) del cookbook RBJ."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / sr
    cosw, sinw = math.cos(w0), math.sin(w0)
    alpha = sinw / (2.0 * q)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * cosw
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha / A
    return ((b0 / a0, b1 / a0, b2 / a0), (1.0, a1 / a0, a2 / a0))


class EfectoEQ(IEfectoDSP):
    def __init__(self, sr: int, low_db: float, mid_db: float, high_db: float):
        self._secciones: list[_Biquad] = []
        if abs(low_db) > 0.01:
            self._secciones.append(_Biquad(*_biquad_shelf(sr, EQ_FREC_LOW_HZ, low_db, "low")))
        if abs(mid_db) > 0.01:
            self._secciones.append(_Biquad(*_biquad_peak(sr, EQ_FREC_MID_HZ, mid_db, EQ_Q_MEDIO)))
        if abs(high_db) > 0.01:
            self._secciones.append(_Biquad(*_biquad_shelf(sr, EQ_FREC_HIGH_HZ, high_db, "high")))

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        if not self._secciones:
            return bloque
        x = bloque[:, 0].astype(np.float64)
        for seccion in self._secciones:
            x = seccion.procesar(x)
        return x.astype(np.float32).reshape(-1, 1)

    def reset(self) -> None:
        for seccion in self._secciones:
            seccion.reset()


# --------------------------------------------------------------------------- #
# 7) Reverb de Schroeder (4 peines amortiguados + 2 allpass en serie)
# --------------------------------------------------------------------------- #
class _CombDamp:
    """Peine con realimentación amortiguada: y[n] = x[n] + g·lp(y[n-D])."""

    def __init__(self, retardo: int, ganancia: float, amortiguacion: float):
        self._buf = np.zeros(max(int(retardo), 1))
        self._g = ganancia
        self._i = 0
        self._b = np.array([1.0 - amortiguacion])
        self._a = np.array([1.0, -amortiguacion])
        self._zi = np.zeros(1)

    def procesar(self, x: np.ndarray) -> np.ndarray:
        D = self._buf.size
        if x.size <= D:
            return self._procesar_trozo(x)
        salida = np.empty_like(x)
        pos = 0
        while pos < x.size:                    # trozos ≤ D: recursión correcta
            fin = min(pos + D, x.size)
            salida[pos:fin] = self._procesar_trozo(x[pos:fin])
            pos = fin
        return salida

    def _procesar_trozo(self, x: np.ndarray) -> np.ndarray:
        D = self._buf.size
        idx = (self._i + np.arange(x.size)) % D
        yd = self._buf[idx]                    # y[n - D]
        fd, self._zi = lfilter(self._b, self._a, yd, zi=self._zi)
        y = x + self._g * fd
        self._buf[idx] = y
        self._i = int((self._i + x.size) % D)
        return y

    def reset(self) -> None:
        self._buf[:] = 0.0
        self._i = 0
        self._zi = np.zeros(1)


class _Allpass:
    """Allpass de Schroeder: y[n] = -x[n] + x[n-D] + g·y[n-D] (truco Freeverb)."""

    def __init__(self, retardo: int, ganancia: float = 0.5):
        self._buf = np.zeros(max(int(retardo), 1))
        self._g = ganancia
        self._i = 0

    def procesar(self, x: np.ndarray) -> np.ndarray:
        D = self._buf.size
        if x.size <= D:
            return self._procesar_trozo(x)
        salida = np.empty_like(x)
        pos = 0
        while pos < x.size:
            fin = min(pos + D, x.size)
            salida[pos:fin] = self._procesar_trozo(x[pos:fin])
            pos = fin
        return salida

    def _procesar_trozo(self, x: np.ndarray) -> np.ndarray:
        D = self._buf.size
        idx = (self._i + np.arange(x.size)) % D
        bufout = self._buf[idx]
        y = bufout - x
        self._buf[idx] = x + bufout * self._g
        self._i = int((self._i + x.size) % D)
        return y

    def reset(self) -> None:
        self._buf[:] = 0.0
        self._i = 0


class ReverbSchroeder(IEfectoDSP):
    """Reverb económica y RT-safe: 4 peines en paralelo → 2 allpass en serie.

    `room_size` controla mezcla wet y realimentación; `damping` amortigua
    los agudos en la cola (salas grandes = cola más apagada).
    """

    def __init__(self, sr: int, room_size: float, damping: float):
        self._wet = float(min(max(room_size, 0.0), 1.0))
        self._amortiguacion = float(min(max(damping, 0.0), 1.0))
        g = REVERB_G_BASE + REVERB_G_RANGO * self._wet
        self._combs = [
            _CombDamp(int(ms * sr / 1000.0), g, self._amortiguacion)
            for ms in REVERB_COMBOS_MS
        ]
        self._allpass = [
            _Allpass(int(ms * sr / 1000.0), 0.5)
            for ms in REVERB_ALLPASS_MS
        ]

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = bloque[:, 0].astype(np.float64)
        mojado = np.zeros_like(x)
        for comb in self._combs:                # 4 peines en paralelo
            mojado += comb.procesar(x)
        mojado *= 0.25
        for ap in self._allpass:                # 2 allpass en serie
            mojado = ap.procesar(mojado)
        mezcla = x * (1.0 - 0.35 * self._wet) + mojado * 1.3 * self._wet
        return np.clip(mezcla, -1.0, 1.0).astype(np.float32).reshape(-1, 1)

    def reset(self) -> None:
        for comb in self._combs:
            comb.reset()
        for ap in self._allpass:
            ap.reset()
