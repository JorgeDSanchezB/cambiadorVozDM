"""Persistencia de config.json (contrato de la Fase 3).

Tolerancia a fallos: si el archivo está corrupto o le faltan claves, se
completa con valores por defecto, se respalda el archivo dañado y se
devuelven avisos para la UI. Nunca se impide arrancar la aplicación.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

BUFFERS_VALIDOS = (128, 256, 512, 1024)
SAMPLE_RATES_VALIDOS = (44100, 48000)


@dataclass
class ConfigAudio:
    sample_rate: int = 48000
    buffer_size: int = 256
    dispositivo_entrada: int | None = None
    dispositivo_salida: int | None = None


@dataclass
class ConfigGrabacion:
    carpeta_destino: str = ""            # "" → ~/Music/SesionesDnD
    formato: str = "mp3"
    bitrate_kbps: int = 192
    patron_nombre: str = "voz_{fecha}_{hora}"


@dataclass
class ConfigMotor:
    modo: str = "DSP"
    permitir_ia: bool = True
    tam_grano_pitch: int = 512      # 512 → ~12 ms de latencia de pitch (buena relación calidad/latencia)
    ffmpeg_ruta: str = ""


@dataclass
class ConfigUI:
    vista_botones: bool = True


@dataclass
class ConfigApp:
    version: int = 1
    audio: ConfigAudio = field(default_factory=ConfigAudio)
    grabacion: ConfigGrabacion = field(default_factory=ConfigGrabacion)
    motor: ConfigMotor = field(default_factory=ConfigMotor)
    ui: ConfigUI = field(default_factory=ConfigUI)
    atajos: dict[str, str] = field(default_factory=dict)   # tecla → id de voz


def _mezclar(cls, datos: dict):
    """Crea `cls` desde un dict ignorando claves desconocidas o mal tipadas."""
    instancia = cls()
    if not isinstance(datos, dict):
        return instancia
    for f in fields(cls):
        if f.name not in datos:
            continue
        valor = datos[f.name]
        actual = getattr(instancia, f.name)
        try:
            if isinstance(actual, bool):
                setattr(instancia, f.name, bool(valor))
            elif actual is None or isinstance(actual, int):
                # campos int y campos int|None (dispositivos)
                setattr(instancia, f.name, int(valor) if valor is not None else None)
            elif isinstance(actual, float):
                setattr(instancia, f.name, float(valor))
            elif isinstance(actual, str):
                setattr(instancia, f.name, str(valor))
        except (TypeError, ValueError):
            log.warning("config.json: valor inválido para %s.%s=%r; se usa el defecto",
                        cls.__name__, f.name, valor)
    return instancia


class RepoConfig:
    def __init__(self, ruta: Path):
        self._ruta = ruta

    def cargar(self) -> tuple[ConfigApp, list[str]]:
        avisos: list[str] = []
        if not self._ruta.exists():
            return ConfigApp(), ["No existía config.json: se creó con valores por defecto."]
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            respaldo = self._ruta.with_suffix(".corrupto.json")
            try:
                shutil.copy2(self._ruta, respaldo)
            except OSError:
                respaldo = None
            log.exception("config.json corrupto (respaldo: %s)", respaldo)
            aviso = ("config.json corrupto: se usaron valores por defecto.")
            if respaldo:
                aviso += f" Copia dañada guardada en {respaldo.name}."
            return ConfigApp(), [aviso]

        cfg = ConfigApp(
            audio=_mezclar(ConfigAudio, datos.get("audio", {})),
            grabacion=_mezclar(ConfigGrabacion, datos.get("grabacion", {})),
            motor=_mezclar(ConfigMotor, datos.get("motor", {})),
            ui=_mezclar(ConfigUI, datos.get("ui", {})),
        )
        atajos = datos.get("atajos", {})
        if isinstance(atajos, dict):
            cfg.atajos = {str(k): str(v) for k, v in atajos.items()
                          if isinstance(v, str)}
        else:
            avisos.append("config.json: la sección 'atajos' era inválida; se ignoró.")

        if cfg.audio.buffer_size not in BUFFERS_VALIDOS:
            avisos.append(f"Buffer {cfg.audio.buffer_size} no válido; se usó 256.")
            cfg.audio.buffer_size = 256
        if cfg.audio.sample_rate not in SAMPLE_RATES_VALIDOS:
            avisos.append(f"Sample rate {cfg.audio.sample_rate} no válido; se usó 48000.")
            cfg.audio.sample_rate = 48000
        return cfg, avisos

    def guardar(self, cfg: ConfigApp) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = asdict(cfg)
        self._ruta.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("config.json guardado")
