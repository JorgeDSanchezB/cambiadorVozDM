# 007 — Decisiones de NO cambio (auditoría V6)

- **Fecha**: rama `chore/quality-improvements` (auditoría V6)
- **Estado**: aceptado

En brownfield, "no cambiar" también es una decisión. Se listan las
candidatas evaluadas y descartadas, con el motivo. Cada entrada indica:
problema que resolvería, coste que introduce, alternativa descartada.

## 1. No migrar a base de datos (se mantiene la decisión 001)

- **Problema que resolvería**: integridad referencial, consultas.
- **Coste**: rompe el contrato de usuario "una voz = un JSON editable a
  mano"; añade binario/migraciones a una app de escritorio de mesa.
- **Resolución**: los defectos de integridad reales se corrigieron en el
  CRUD (decisión 006) sin tocar el modelo de persistencia.

## 2. No virtualizar la lista de voces

- **Problema que resolvería**: la regla de la "lista infinita" con n→∞.
- **Coste**: PyQt6 no tiene virtualización estándar; habría que pagarla a
  mano (viewport + reciclaje de filas) o meter una dependencia nueva.
- **Escala real del dominio**: decenas de voces por DM (hoy 20). La lista
  ya tiene scroll, buscador con filtrado instantáneo y estados de
  "sin resultados". El límite práctico (≈500 filas construidas como
  QWidget) está 25× por encima del uso real y documentado aquí como
  techo conocido. Si algún día se acerca, virtualizar es un cambio
  localizado en `PestanaVoces` (la fuente de datos es una lista plana).

## 3. No introducir pytest/coverage/linter/CI como dependencias nuevas

- **Problema que resolvería**: mejor DX de pruebas.
- **Coste**: dependencias nuevas en un repo cuyo dueño verifica hoy con
  `py_compile` + smoke tests; exige decisión de mantenibilidad del
  equipo (regla brownfield: no imponer stack).
- **Resolución**: la suite nueva usa **unittest de la librería estándar**
  (cero dependencias): `python -m unittest discover -s tests`. Adoptar
  pytest/ruff queda como decisión abierta del equipo, no de esta rama.

## 4. No añadir tests de GUI (PyQt6) a la suite

- **Motivo**: requieren instalables de sistema (libEGL/Qt) que no están
  garantizados en los entornos donde corre el proyecto. La suite cubre
  dominio + motor (headless). La verificación GUI sigue siendo manual en
  el PC Windows del usuario (ver `docs/current-state.md`).

## 5. No mover `VOCES_TTS_SUGERIDAS` a un JSON de datos

- **Problema que resolvería**: cero datos de negocio en código.
- **Coste**: otra pieza de configuración que cargar/validar para una
  lista de 7 sugerencias de UI que cambia con la disponibilidad de
  edge-tts (fuente externa). No es un límite ni una regla de negocio:
  es un menú por defecto. Se queda en código, documentado aquí.

## 6. Constantes DSP de `efectos.py` se quedan como constantes de diseño

`EQ_FREC_LOW_HZ`, `REVERB_COMBOS_MS`, etc. son parámetros **de diseño
acústico** del algoritmo, nombrados y documentados en cabecera, no
límites de negocio editables por el usuario. Moverlas a `parametros.json`
mezclaría "lo que el DM ajusta" con "cómo funciona el efecto". No cambio.

## 7. Los hermanos antiguos no se tocan

- `cambiador-voz-dnd/` es la versión legada documentada como "no editar"
  (ver `docs/current-state.md`). Archivarla o borrarla es decisión del
  dueño del repo (rompe clones existentes); se propone en el informe, no
  se ejecuta.
- La raíz (scaffold Next.js + `.zscripts/`) es infraestructura de
  despliegue de la plantilla del harness: fuera del alcance de esta rama.

## 8. No se versiona el contrato de `config.json` (sigue `version: 1`)

Los cambios de esta rama son **aditivos y retrocompatibles**: un
`config.json` antiguo carga igual (los avisos nuevos son informativos).
No se necesita migración ni bump de versión.

## 9. Commits locales, sin push

`AGENTS.md` prohíbe tocar git sin autorización explícita. El usuario
autorizó en el encargo de esta tarea una rama de trabajo con commits
atómicos; se creó `chore/quality-improvements` con commits locales
revertibles. **No se hace push ni se abre PR** (requiere credenciales y
decisión del dueño; comandos exactos en el informe final).
