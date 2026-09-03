# 001 — Datos por archivos JSON, data-driven (sin base de datos)

- **Fecha**: creación de `voz_dnd/`
- **Estado**: aceptado

## Contexto

El cambiador de voz debe exponer voces y parámetros editables sin recompilar,
y sobrevivir a archivos corruptos sin bloquear el arranque.

## Decisión

Persistencia con archivos JSON planos en `data/`, sin servidor ni motor de
base de datos:

- `data/parametros.json` — rangos/etiquetas de cada slider (única fuente de
  verdad de límites).
- `data/voces/*.json` — una voz = un archivo.
- `data/config.json` — ajustes de la app (buffer, dispositivos, atajos).

Los rangos **no** van hardcodeados en el código: viven en
`parametros.json` y los interpreta `CatalogoParametros`.

## Consecuencias

- Añadir una voz = crear un JSON; no tocar código. (Garantía: la voz
  `neutral` debe existir siempre.)
- Tolerancia a fallos por diseño: JSON corrupto/faltante se omite y se avisa
  con banner; nunca bloquea el arranque (`config.py`, `gestor_voces.py`,
  `models.voz_desde_dict` lanzan `VozCorruptaError`).
- Sin migraciones ni servicios externos: portátil y simple para un proyecto de
  mesa local.
