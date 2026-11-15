# 006 — Integridad "una voz = un archivo" en el CRUD de voces

- **Fecha**: rama `chore/quality-improvements` (auditoría V6)
- **Estado**: aceptado (endurece la decisión 001)

## Contexto

La decisión 001 (datos en JSON, una voz = un archivo) tenía tres fugas
detectadas en la auditoría:

1. **Renombrar** una voz escribía el JSON nuevo pero dejaba el viejo con
   el MISMO `id`. Al recargar, el orden alfabético de archivos decidía
   cuál ganaba en el dict: renombrar `Zeta` → `Alfa` se revertía solo
   tras reiniciar (reproducido en test).
2. **Colisión de slug**: `Dragón!` y `dragón` producen ambos
   `dragon.json`; la segunda voz pisaba el archivo de la primera.
3. **Id duplicado en disco** (copia manual) se cargaba en silencio (la
   última en orden alfabético ganaba).

## Decisión

- `guardar()` escribe y después **borra los residuos**: cualquier otro
  `*.json` con el mismo `id` distinto del recién escrito. El `id` es la
  identidad de la voz; dos archivos con el mismo `id` son por definición
  la misma voz y uno de ellos es un residuo.
- `_ruta_libre()` desambigua colisiones de slug con sufijo `-2`, `-3`…
  cuando el archivo existente pertenece a **otra** voz (otro `id`).
- `cargar_todas()` ante un `id` duplicado gana el archivo **canónico**
  (nombre de archivo == slug del nombre) y el residuo se reporta como
  aviso con instrucción de limpieza; nunca se borra en la carga (no se
  eliminan archivos del usuario como efecto secundario de leerlos).
- `eliminar()` usa la ruta real rastreada (`_rutas`), no la reconstruida
  por slug (funciona tras renombrar o desambiguar).

## Alternativas descartadas

- **Migrar a SQLite**: resuelve duplicados por esquema, pero rompe el
  contrato "editar voces con el bloc de notas" que la decisión 001 da al
  usuario del proyecto. Cambio desproporcionado para un CRUD de ~20
  archivos.
- **Guardar el nombre de archivo dentro del JSON**: acopla el contenido a
  la ruta y complica las copias manuales (el caso de uso real del DM).

## Coste

- `guardar()` relee los `*.json` de la carpeta para limpiar residuos:
  O(n) lecturas pequeñas por guardado (n ≈ 20 → despreciable en desktop).
- Un usuario que copiara un JSON a mano para "respaldar" la voz verá la
  copia eliminada al volver a guardar esa voz: es el invariante
  documentado (una voz = un archivo), y el aviso de residuo en la carga
  lo explica antes de que ocurra.
