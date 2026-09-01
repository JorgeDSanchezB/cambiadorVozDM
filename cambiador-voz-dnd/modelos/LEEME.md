# Modelos de IA (Modo Avanzado)

Esta carpeta contiene los componentes del **Modo Avanzado (clonación de voz)**.
Es 100 % opcional: la aplicación funciona completa en Modo DSP sin nada de esto.

## Contenido esperado

| Archivo / carpeta | Descripción |
|---|---|
| `plugin_rvc.py` | Plugin que integra tu pipeline RVC (ver contrato abajo). |
| `*.pth` | Modelos entrenados con RVC (uno por voz IA). |

## Contrato del plugin (`plugin_rvc.py`)

El módulo debe exponer **exactamente dos funciones**:

```python
def cargar(ruta_modelo: str, usar_gpu: bool) -> object:
    """Carga el modelo UNA vez (hilo background) y devuelve un objeto motor.
    Puede almacenar el dispositivo (cuda/cpu), el modelo, el índice, etc."""

def inferir(motor: object,
            chunk: "np.ndarray",        # float32 mono, 4096 muestras (~85 ms)
            pitch_semitonos: int,       # transposición (del JSON: pitch_rvc)
            index_rate: float,          # 0..1 fuerza del índice de timbre
            sr: int) -> "np.ndarray":   # devuelve float32 mono, MISMO largo
    """Transforma un chunk de voz. Debe ser thread-safe con el callback
    de audio (la app serializa las llamadas con un lock)."""
```

## Plantilla mínima

```python
# modelos/plugin_rvc.py
import numpy as np

def cargar(ruta_modelo, usar_gpu):
    import torch
    dispositivo = "cuda" if usar_gpu and torch.cuda.is_available() else "cpu"
    # ... carga aquí tu modelo RVC (ej. con fairseq/rvc-python) ...
    return {"modelo": None, "dispositivo": dispositivo}

def inferir(motor, chunk, pitch_semitonos, index_rate, sr):
    # ... convierte chunk (float32 [-1,1]) a tensor, infiere, devuelve np.float32 ...
    return chunk  # placeholder: identidad
```

## Guías de latencia

- El chunk es de 4096 muestras (~85 ms @48 kHz): la latencia base del Modo IA
  es de ~100–300 ms según GPU. Es inherente al modelo (HuBERT + generador).
- Si la inferencia tarda más del 80 % del tiempo del chunk de forma sostenida
  (típico en CPU), el `ProcesadorIA` se autodesactiva y la app vuelve a la
  cadena DSP automáticamente (se muestra un aviso).
