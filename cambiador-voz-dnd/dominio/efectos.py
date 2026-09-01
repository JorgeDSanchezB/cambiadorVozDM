"""El corazón del programa: efectos DSP en tiempo real.

Contrato universal (Chain of Responsibility):
    y = efecto.procesar(bloque, sr)

Invariantes de tiempo real que TODO efecto respeta:
  * Trabaja por bloques pequeños (128–1024 muestras) con numpy vectorizado.
  * Mantiene estado interno PERSISTENTE entre bloques (ventanas, retardos,
  * filtros) para que el sonido sea continuo e ininterrumpido.
  * No realiza I/O, no lanza excepciones esperables ni asigna memoria grande
    por muestra.

Constantes de ingeniería (no parámetros musicales): son constantes NOMBRADAS
del diseño DSP; los parámetros musicales llegan SIEMPRE desde el JSON de voz.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import lfilter, lfilter_zi

# --------------------------------------------------------------------------- #
#  Constantes de diseño DSP (nombradas y documentadas)
# --------------------------------------------------------------------------- #
TAM_GRANO_MUESTRAS = 1024      # grano del pitch shifter (≈21 ms @ 48 kHz)
RETARDO_MINIMO_MUESTRAS = 8    # margen de seguridad para interpolación
VENTANA_STFT = 1024            # ventana del desplazador de formantes
SALTOS_STFT = 256              # hop del STFT (75 % overlap)
SUAVIZADO_ENVOLVENTE_BINS = 9  # ancho (bins) del estimador de envolvente
GANANCIA_ENTRADA_REVERB = 0.015  # escala de entrada estilo Freeverb
FEEDBACK_COMB = 0.82           # realimentación de los comb (cola de reverb)
RETRASOS_COMB_MS = (29.7, 37.1, 41.1, 43.7)  # red Schroeder clásica
RETRASOS_PASATODO_MS = (5.0, 1.7)
FREC_EQ_GRAVES_HZ = 120.0
FREC_EQ_MEDIOS_HZ = 1200.0
FREC_EQ_AGUDOS_HZ = 6000.0
Q_EQ = 0.707


class IEfectoDSP(ABC):
    """Contrato de la cadena: todo efecto lo implementa."""

    @abstractmethod
    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        """Procesa un bloque float32 mono y devuelve el bloque transformado."""

    @abstractmethod
    def reset(self) -> None:
        """Limpia el estado interno (se llama al cambiar de voz)."""

    @property
    @abstractmethod
    def latencia_muestras(self) -> int:
        """Retardo algorítmico introducido (para medir latencia total)."""


# --------------------------------------------------------------------------- #
#  1. Ganancia + limitador suave
# --------------------------------------------------------------------------- #
class Ganancia(IEfectoDSP):
    def __init__(self, sr: int, gain_db: float) -> None:
        self._lineal = float(10.0 ** (gain_db / 20.0))

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        y = bloque * self._lineal
        return np.clip(y, -1.0, 1.0).astype(np.float32)

    def reset(self) -> None:
        return None

    @property
    def latencia_muestras(self) -> int:
        return 0


# --------------------------------------------------------------------------- #
#  2. PitchShifter granular de "dos cabezas"
# --------------------------------------------------------------------------- #
class PitchShifter(IEfectoDSP):
    """Desplazador de tono en tiempo real.

    Técnica: dos punteros de lectura recorren una línea de retardo a razón
    `ratio` veces la velocidad de escritura (efecto Doppler). Sus ventanas
    sin² desfasadas medio período suman EXACTAMENTE 1:

        sin²(θ) + sin²(θ + π/2) = 1   →   ganancia unitaria sin saltos.

    Cuando un puntero termina su recorrido, la ventana vale 0 y el salto de
    retardo queda enmascarado (crossfade perfecto).
    """

    def __init__(self, sr: int, ratio: float, tam_grano: int = TAM_GRANO_MUESTRAS) -> None:
        self.sr = int(sr)
        self.ratio = float(np.clip(ratio, 0.25, 4.0))
        self.periodo = max(64, int(tam_grano // 2))          # P: período de modulación
        self.retardo_min = float(RETARDO_MINIMO_MUESTRAS)    # D0
        self.capacidad = self.periodo * 2 + 4096             # tamaño línea de retardo
        self.buffer = np.zeros(self.capacidad, dtype=np.float32)
        self.escritas = 0        # muestras absolutas escritas (índice global)
        self.fase = 0.0          # fase de modulación acumulada (mod P)
        self._offsets = (0.0, self.periodo / 2.0)

    @property
    def latencia_muestras(self) -> int:
        return int(self.retardo_min + self.periodo * 0.75)

    def reset(self) -> None:
        self.buffer[:] = 0.0
        self.escritas = 0
        self.fase = 0.0

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        n = len(bloque)
        x = bloque.astype(np.float32, copy=False)

        # 1) Escribir el bloque completo ANTES de leer (lecturas seguras).
        idx_escritura = (self.escritas + np.arange(n)) % self.capacidad
        self.buffer[idx_escritura] = x

        # 2) Fase de modulación por muestra: d(delay)/di = (1 - ratio)
        t = self.fase + (1.0 - self.ratio) * np.arange(n, dtype=np.float64)
        w_abs = self.escritas + np.arange(n)

        salida = np.zeros(n, dtype=np.float32)
        for offset in self._offsets:
            tmod = np.mod(t + offset, self.periodo)            # diente de sierra [0,P)
            delay = self.retardo_min + tmod
            pos = w_abs - delay                                # posición absoluta de lectura
            pos = np.clip(pos, 0.0, float(self.escritas + n - 1))
            p0 = pos.astype(np.int64) % self.capacidad
            p1 = (p0 + 1) % self.capacidad
            frac = (pos - np.floor(pos)).astype(np.float32)
            lectura = self.buffer[p0] * (1.0 - frac) + self.buffer[p1] * frac
            ventana = np.sin(np.pi * tmod / self.periodo) ** 2  # sin², suma exacta = 1
            salida += (lectura * ventana).astype(np.float32)

        self.escritas += n
        self.fase = float(np.mod(self.fase + (1.0 - self.ratio) * n, self.periodo))
        return np.clip(salida, -1.0, 1.0)


# --------------------------------------------------------------------------- #
#  3. FormantShifter (STFT, desplaza la envolvente espectral)
# --------------------------------------------------------------------------- #
class FormantShifter(IEfectoDSP):
    """Desplaza formantes SIN cambiar el tono (tamaño de "garganta").

    Técnica: STFT con ventana Hann (75 % overlap); estima la envolvente
    espectral (media móvil en dominio logarítmico) y la reinterpeta escalada
    por `factor` sobre el eje de frecuencia. La fase no se toca → el tono se
    conserva. Factor > 1 = criatura pequeña; factor < 1 = criatura enorme.
    """

    def __init__(self, sr: int, factor: float) -> None:
        self.sr = int(sr)
        self.factor = float(np.clip(factor, 0.5, 2.0))
        self.ventana = np.hanning(VENTANA_STFT).astype(np.float32)
        self.normalizacion = 1.5  # Σ hann² con hop = W/4 == 1.5
        self.historial = np.zeros(0, dtype=np.float32)
        self.acumulador = np.zeros(VENTANA_STFT, dtype=np.float32)
        self._cola_salida: list[np.ndarray] = []

    @property
    def latencia_muestras(self) -> int:
        return VENTANA_STFT

    def reset(self) -> None:
        self.historial = np.zeros(0, dtype=np.float32)
        self.acumulador = np.zeros(VENTANA_STFT, dtype=np.float32)
        self._cola_salida = []

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = np.concatenate([self.historial, bloque.astype(np.float32, copy=False)])
        indice = 0
        while indice + VENTANA_STFT <= len(x):
            marco = x[indice: indice + VENTANA_STFT]
            self._cola_salida.append(self._procesar_marco(marco))
            indice += SALTOS_STFT
        self.historial = x[indice:]

        pendiente = (np.concatenate(self._cola_salida)
                     if self._cola_salida else np.zeros(0, np.float32))
        self._cola_salida = []
        n = len(bloque)
        if len(pendiente) >= n:
            self._cola_salida = [pendiente[n:]]
            return pendiente[:n]
        faltante = n - len(pendiente)  # arranque: aún no hay marco completo
        return np.concatenate([pendiente, np.zeros(faltante, np.float32)])

    def _procesar_marco(self, marco: np.ndarray) -> np.ndarray:
        espectro = np.fft.rfft(marco * self.ventana)
        magnitud = np.abs(espectro) + 1e-12
        # Envolvente espectral: suavizado log → robusto ante picos armónicos.
        envolvente = np.exp(
            uniform_filter1d(np.log(magnitud), size=SUAVIZADO_ENVOLVENTE_BINS)
        ).astype(np.float32)
        bins = np.arange(len(envolvente), dtype=np.float32)
        envolvente_nueva = np.interp(bins / self.factor, bins, envolvente).astype(np.float32)
        ganancia = np.clip(envolvente_nueva / envolvente, 0.1, 10.0)
        marco_mod = np.fft.irfft(espectro * ganancia, VENTANA_STFT).astype(np.float32)

        # Overlap-add con ventana de síntesis (reconstrucción perfecta /1.5)
        self.acumulador += marco_mod * self.ventana / self.normalizacion
        salida = self.acumulador[:SALTOS_STFT].copy()
        self.acumulador = np.concatenate(
            [self.acumulador[SALTOS_STFT:], np.zeros(SALTOS_STFT, np.float32)]
        )
        return salida


# --------------------------------------------------------------------------- #
#  4. Distorsión (waveshaping tanh + eliminador de DC)
# --------------------------------------------------------------------------- #
class Distorsion(IEfectoDSP):
    def __init__(self, sr: int, drive: float) -> None:
        self.k = 1.0 + float(np.clip(drive, 0.0, 1.0)) * 9.0
        self.normalizacion = 1.0 / float(np.tanh(self.k)) if self.k > 1e-6 else 1.0
        self._r_dc = 0.995  # paso alto de 1 polo (~20 Hz @ 48 kHz)
        self._zi_dc = np.array([0.0])

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = bloque.astype(np.float32, copy=False)
        y = np.tanh(self.k * x) * self.normalizacion
        y, zf = lfilter([1.0, -1.0], [1.0, -self._r_dc], y, zi=self._zi_dc)
        self._zi_dc = zf
        return np.clip(y, -1.0, 1.0).astype(np.float32)

    def reset(self) -> None:
        self._zi_dc = np.array([0.0])

    @property
    def latencia_muestras(self) -> int:
        return 0


# --------------------------------------------------------------------------- #
#  5. Ring modulator (voces robóticas / aberraciones)
# --------------------------------------------------------------------------- #
class RingMod(IEfectoDSP):
    PROFUNDIDAD = 0.85  # mezcla portadora/señal (constante de diseño)

    def __init__(self, sr: int, frecuencia_hz: float) -> None:
        self.sr = int(sr)
        self.frecuencia = float(frecuencia_hz)
        self.muestra = 0

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = bloque.astype(np.float32, copy=False)
        t = (self.muestra + np.arange(len(x))) / float(self.sr)
        portadora = np.sin(2.0 * np.pi * self.frecuencia * t).astype(np.float32)
        self.muestra = (self.muestra + len(x)) % max(1, int(self.sr))  # evita drift
        mezcla = (1.0 - self.PROFUNDIDAD) + self.PROFUNDIDAD * portadora
        return np.clip(x * mezcla, -1.0, 1.0)

    def reset(self) -> None:
        self.muestra = 0

    @property
    def latencia_muestras(self) -> int:
        return 0


# --------------------------------------------------------------------------- #
#  6. EQ de 3 bandas (biquads RBJ con estado entre bloques)
# --------------------------------------------------------------------------- #
class BiquadEQ(IEfectoDSP):
    """Biquad RBJ cookbook: 'low_shelf' | 'peaking' | 'high_shelf'."""

    def __init__(self, sr: int, tipo: str, f0: float, gain_db: float, q: float = Q_EQ) -> None:
        self.sr = int(sr)
        fs = float(sr)
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * f0 / fs
        cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
        alpha = sin_w0 / (2.0 * q)
        raiz_a = 2.0 * np.sqrt(A) * alpha

        if tipo == "low_shelf":
            b = [A * ((A + 1) - (A - 1) * cos_w0 + raiz_a),
                 2 * A * ((A - 1) - (A + 1) * cos_w0),
                 A * ((A + 1) - (A - 1) * cos_w0 - raiz_a)]
            a = [(A + 1) + (A - 1) * cos_w0 + raiz_a,
                 -2 * ((A - 1) + (A + 1) * cos_w0),
                 (A + 1) + (A - 1) * cos_w0 - raiz_a]
        elif tipo == "peaking":
            b = [1 + alpha * A, -2 * cos_w0, 1 - alpha * A]
            a = [1 + alpha / A, -2 * cos_w0, 1 - alpha / A]
        elif tipo == "high_shelf":
            b = [A * ((A + 1) + (A - 1) * cos_w0 + raiz_a),
                 -2 * A * ((A - 1) + (A + 1) * cos_w0),
                 A * ((A + 1) + (A - 1) * cos_w0 - raiz_a)]
            a = [(A + 1) - (A - 1) * cos_w0 + raiz_a,
                 2 * ((A - 1) - (A + 1) * cos_w0),
                 (A + 1) - (A - 1) * cos_w0 - raiz_a]
        else:  # pragma: no cover - tipo controlado por la Fábrica
            raise ValueError(f"Tipo de EQ desconocido: {tipo}")

        a0 = a[0]
        self._b = [float(v / a0) for v in b]
        self._a = [float(v / a0) for v in a]
        self._zi = np.zeros(2)

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        y, zf = lfilter(self._b, self._a, bloque, zi=self._zi)
        self._zi = zf
        return y.astype(np.float32)

    def reset(self) -> None:
        self._zi = np.zeros(2)

    @property
    def latencia_muestras(self) -> int:
        return 0


# --------------------------------------------------------------------------- #
#  7. Reverb (Schroeder/Freeverb: 4 comb + 2 allpass, todo vectorizado)
# --------------------------------------------------------------------------- #
class _Combiltro:
    """Comb Freeverb: salida = línea de retardo con realimentación amortiguada.

    Requiere que el bloque sea más corto que el retardo D (lo garantiza
    `Reverb` troceando la entrada); así la realimentación vive íntegramente
    en el buffer circular y el bloque se procesa 100 % vectorizado.
    """

    def __init__(self, sr: int, delay_ms: float, escala: float,
                 feedback: float, damping: float) -> None:
        self.D = max(16, int(sr * delay_ms / 1000.0 * escala))
        self.feedback = float(feedback)
        self.damp1 = float(damping)       # paso bajo en el lazo
        self.damp2 = 1.0 - self.damp1
        self.buffer = np.zeros(self.D, dtype=np.float32)
        self.posicion = 0
        self._zi = np.zeros(1)

    def procesar(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        idx = (self.posicion + np.arange(n)) % self.D
        y = self.buffer[idx].copy()          # leer ANTES de escribir
        # fs[n] = damp2·y[n] + damp1·fs[n-1]   (recursión vía lfilter con estado)
        fs, zf = lfilter([self.damp2], [1.0, -self.damp1], y, zi=self._zi)
        self._zi = zf
        self.buffer[idx] = (x + fs * self.feedback).astype(np.float32)
        self.posicion = (self.posicion + n) % self.D
        return y

    def reset(self) -> None:
        self.buffer[:] = 0.0
        self.posicion = 0
        self._zi = np.zeros(1)


class _PaseTodo:
    """Filtro all-pass (difusión): y[n] = -g·x[n] + x[n-D] + g·y[n-D]."""

    def __init__(self, sr: int, delay_ms: float, g: float = 0.5) -> None:
        self.D = max(4, int(sr * delay_ms / 1000.0))
        self._b = np.array([-g] + [0.0] * (self.D - 1) + [1.0])
        self._a = np.array([1.0] + [0.0] * (self.D - 1) + [-g])
        self._zi = lfilter_zi(self._b, self._a)

    def procesar(self, x: np.ndarray) -> np.ndarray:
        y, self._zi = lfilter(self._b, self._a, x, zi=self._zi)
        return y.astype(np.float32)

    def reset(self) -> None:
        self._zi = lfilter_zi(self._b, self._a)


class Reverb(IEfectoDSP):
    """Reverb de sala: red Schroeder (4 comb paralelos + 2 allpass en serie).

    * room_size escala la longitud de los retardos (sala grande/pequeña)
      y también la mezcla wet (sala grande suena más presente).
    * damping amortigua los agudos en cada reflexión.
    """

    def __init__(self, sr: int, room_size: float, damping: float) -> None:
        self.sala = float(np.clip(room_size, 0.0, 1.0))
        self.damping = float(np.clip(damping, 0.0, 1.0))
        escala = 0.5 + 1.5 * self.sala          # retardos × [0.5 .. 2.0]
        self.wet = 0.8 * self.sala
        self._combs = [
            _Combiltro(sr, ms, escala, FEEDBACK_COMB, self.damping)
            for ms in RETRASOS_COMB_MS
        ]
        self._pasatodo = [
            _PaseTodo(sr, ms) for ms in RETRASOS_PASATODO_MS
        ]
        # Troceo de seguridad: bloque siempre menor que el retardo mínimo.
        self._tam_bloque_seguro = min(c.D for c in self._combs) - 1

    @property
    def latencia_muestras(self) -> int:
        return 0  # la reverb añade estelas, no retardo algorítmico

    def reset(self) -> None:
        for c in self._combs:
            c.reset()
        for ap in self._pasatodo:
            ap.reset()

    def procesar(self, bloque: np.ndarray, sr: int) -> np.ndarray:
        x = bloque.astype(np.float32, copy=False)
        if len(x) <= self._tam_bloque_seguro:
            return self._procesar_seguro(x)
        partes = [
            self._procesar_seguro(x[i:i + self._tam_bloque_seguro])
            for i in range(0, len(x), self._tam_bloque_seguro)
        ]
        return np.concatenate(partes)

    def _procesar_seguro(self, x: np.ndarray) -> np.ndarray:
        entrada = x * GANANCIA_ENTRADA_REVERB
        cola = np.zeros_like(entrada)
        for comb in self._combs:
            cola += comb.procesar(entrada)
        for pasatodo in self._pasatodo:
            cola = pasatodo.procesar(cola)
        return np.clip((1.0 - self.wet) * x + self.wet * cola * 2.0, -1.0, 1.0)
