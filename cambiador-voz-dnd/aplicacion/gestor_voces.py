"""GestorVoces: carga, validación, CRUD y tolerancia a fallos de las voces.

Regla de la "Voz Nueva": el DM añade voces soltando un JSON en data/voces/
o creándolas desde el Editor. Este gestor las descubre al arrancar o al
pulsar "Recargar", SIN recompilar nada.

Tolerancia a fallos: un JSON corrupto se salta, se registra y se notifica por
eventos; la voz Neutral se regenera automáticamente si falta o está rota,
garantizando que el motor SIEMPRE tiene una voz válida.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from dominio.entidades import (
    IVoiceProfile,
    ParametrosDSP,
    PerfilDSP,
)

PLANTILLA_NEUTRAL: dict[str, Any] = {
    "id": IVoiceProfile.ID_NEUTRAL,
    "nombre": "Neutral",
    "tipo": "DSP",
    "icono": "🎙️",
    "color": "#6b7280",
    "parametros_dsp": ParametrosDSP().a_dict(),
}


class GestorVoces:
    def __init__(self, carpeta_voces: Path, catalogo: dict[str, dict],
                 eventos: "queue.SimpleQueue") -> None:  # type: ignore[name-defined]
        import queue  # noqa: F401  (solo tipado)

        self.carpeta = Path(carpeta_voces)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.catalogo = catalogo
        self.eventos = eventos
        self.voces: list[IVoiceProfile] = []

    # ------------------------------------------------------------------ #
    #  Carga
    # ------------------------------------------------------------------ #
    def cargar_todas(self) -> list[IVoiceProfile]:
        """Lee todos los *.json de la carpeta; devuelve la lista válida."""
        voces: list[IVoiceProfile] = []
        for ruta in sorted(self.carpeta.glob("*.json")):
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                perfil = IVoiceProfile.desde_dict(datos)
                errores = perfil.validar(self.catalogo)
                if errores:
                    self.eventos.put((
                        "voz_corrupta",
                        f"{ruta.name}: " + "; ".join(errores),
                    ))
                    continue
                voces.append(perfil)
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                self.eventos.put((
                    "voz_corrupta",
                    f"{ruta.name} está dañado ({exc}). Se ignoró.",
                ))
        self._garantizar_neutral(voces)
        self.voces = voces
        return voces

    def _garantizar_neutral(self, voces: list[IVoiceProfile]) -> None:
        """Si la voz Neutral falta (o estaba corrupta), se regenera en disco."""
        if any(v.id == IVoiceProfile.ID_NEUTRAL for v in voces):
            return
        try:
            ruta = self.carpeta / "neutral.json"
            ruta.write_text(
                json.dumps(PLANTILLA_NEUTRAL, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            voces.insert(0, IVoiceProfile.desde_dict(PLANTILLA_NEUTRAL))
            self.eventos.put(("aviso", "Voz 'Neutral' regenerada automáticamente"))
        except OSError as exc:
            self.eventos.put(("voz_corrupta", f"No se pudo regenerar Neutral: {exc}"))

    def buscar_por_id(self, id_voz: str) -> IVoiceProfile | None:
        return next((v for v in self.voces if v.id == id_voz), None)

    def aplicar_atajos(self, mapa_atajos: dict[str, str]) -> None:
        """Inyecta los atajos de config.json (tecla → id) en cada perfil."""
        for voz in self.voces:
            voz.atajo = next(
                (tecla for tecla, id_voz in mapa_atajos.items() if id_voz == voz.id),
                None,
            )

    # ------------------------------------------------------------------ #
    #  CRUD (Editor de Voces)
    # ------------------------------------------------------------------ #
    def guardar(self, perfil: IVoiceProfile) -> Path:
        """Escribe (o sobrescribe) el JSON de una voz."""
        errores = perfil.validar(self.catalogo)
        if errores:
            raise ValueError("; ".join(errores))
        ruta = self.carpeta / f"{self._slug(perfil.nombre)}.json"
        ruta.write_text(
            json.dumps(perfil.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ruta

    def eliminar(self, id_voz: str) -> bool:
        if id_voz == IVoiceProfile.ID_NEUTRAL:
            self.eventos.put(("aviso", "La voz Neutral no se puede eliminar"))
            return False
        voz = self.buscar_por_id(id_voz)
        if voz is None:
            return False
        ruta = self.carpeta / f"{self._slug(voz.nombre)}.json"
        if ruta.exists():
            ruta.unlink()
        self.voces = [v for v in self.voces if v.id != id_voz]
        return True

    def duplicar(self, id_voz: str, nuevo_nombre: str) -> IVoiceProfile:
        origen = self.buscar_por_id(id_voz)
        if origen is None:
            raise ValueError("Voz de origen no encontrada")
        datos = origen.a_dict()
        datos["nombre"] = nuevo_nombre
        datos["id"] = self._nuevo_id()
        copia = IVoiceProfile.desde_dict(datos)
        self.guardar(copia)
        return copia

    # ------------------------------------------------------------------ #
    #  Utilidades
    # ------------------------------------------------------------------ #
    @staticmethod
    def _slug(nombre: str) -> str:
        sencillo = "".join(c if c.isalnum() or c in "-_ " else "" for c in nombre)
        return sencillo.strip().replace(" ", "_").lower() or "voz"

    @staticmethod
    def _nuevo_id() -> str:
        import uuid

        return str(uuid.uuid4())
