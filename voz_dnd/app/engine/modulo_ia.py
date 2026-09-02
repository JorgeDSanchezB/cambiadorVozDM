"""Módulo de IA opcional (clonación de voz con RVC).

Filosofía (Fase 4): el modo IA es un MÓDULO QUE NO ROMPE NADA.
- Se importa perezosamente (PyTorch/RVC solo se tocan si el usuario los usa).
- La carga del modelo ocurre en un hilo en segundo plano.
- Si falta cualquier pieza (paquete, GPU, modelo .pth), `error` lo explica
  y el ProcesadorIA degrada a su cadena DSP post sin cortar el audio.

Integración real de RVC: ver README.md § "Modo IA (opcional)". El punto de
conexión está marcado en `inicializar()` y `procesar()`.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from app.domain.models import ParametrosIA

log = logging.getLogger(__name__)

# Latencia inherente estimada del pipeline RVC en tiempo real (muestras).
# La inferencia de HuBERT + generador trabaja por chunks grandes.
LATENCIA_IA_MUESTRAS = 8192


class ModuloIA:
    def __init__(self, params: ParametrosIA, sr: int):
        self._params = params
        self._sr = sr
        self._listo = False
        self.error: str | None = None
        self._modelo = None  # objeto del paquete RVC cuando esté conectado

    # ------------------------------------------------------------------ #
    def esta_listo(self) -> bool:
        return self._listo

    @property
    def latencia_muestras(self) -> int:
        return LATENCIA_IA_MUESTRAS if self._listo else 0

    # ------------------------------------------------------------------ #
    @staticmethod
    def estado_gpu() -> tuple[bool, str]:
        """(hay_gpu, descripción) — se muestra en Ajustes y en la pestaña Voces."""
        try:
            import torch  # import diferido: solo si el usuario tiene IA instalada
        except ImportError:
            return False, "PyTorch no instalado (modo IA opcional)"
        if torch.cuda.is_available():
            return True, f"CUDA · {torch.cuda.get_device_name(0)}"
        return False, "Sin GPU compatible con CUDA"

    # ------------------------------------------------------------------ #
    def inicializar(self) -> None:
        """Carga del modelo. LLAMAR SOLO DESDE UN HILO EN SEGUNDO PLANO."""
        con_gpu, detalle = self.estado_gpu()
        log.info("Modo IA: GPU=%s (%s)", con_gpu, detalle)

        if self._params.usar_gpu and not con_gpu:
            self.error = f"GPU no disponible ({detalle}); la voz IA se degrada a DSP."
            return

        if not self._params.modelo_rvc:
            self.error = "Voz IA sin modelo asignado (parametros_ia.modelo_rvc)."
            return
        if not Path(self._params.modelo_rvc).exists():
            self.error = f"Modelo RVC no encontrado: {self._params.modelo_rvc}"
            return

        try:
            if importlib.util.find_spec("rvc") is None:
                self.error = ("Paquete 'rvc' no instalado. Sigue el README "
                              "(§ Modo IA opcional) para habilitarlo.")
                return

            # ================= PUNTO DE EXTENSIÓN RVC =====================
            # Con el paquete instalado, la integración típica es:
            #   from rvc.infer import VoiceConverter
            #   self._modelo = VoiceConverter(
            #       gpu=bool(self._params.usar_gpu and con_gpu))
            #   self._modelo.cargar_modelo(self._params.modelo_rvc,
            #                              index_rate=self._params.index_rate)
            #   self._listo = True
            # La API exacta depende de la versión de RVC instalada; por eso
            # queda documentada en el README y no se hardcodea aquí.
            # ===============================================================
            self.error = ("Motor RVC detectado pero sin adaptador conectado "
                          "(ver README § Modo IA). Se usa la cadena DSP.")
            return
        except Exception as exc:  # noqa: BLE001 — cualquier fallo degrada
            self.error = f"Fallo al iniciar el motor IA: {exc}"
            log.exception(self.error)

    # ------------------------------------------------------------------ #
    def procesar(self, bloque, sr: int):
        """Inferencia en tiempo real. Solo se llama si `esta_listo()`."""
        if not self._listo or self._modelo is None:
            raise RuntimeError("ModuloIA no está listo.")
        # Punto de conexión real (README § Modo IA): acumular chunk →
        # características HuBERT/F0 → generador → devolver float32 (n, 1).
        raise NotImplementedError("Conectar el paquete 'rvc' aquí.")
