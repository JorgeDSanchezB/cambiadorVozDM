Here are all the generated files.

## DMVoiceChangerWeb.exe (2026-11-17, v1.0.1) — EL INSTALADOR OFICIAL

**La app web (La Forja de Voces) convertida en programa de Windows.**
~54 MB descargados, ~257 MB instalados. v1.0.1 corrige el
«No se encuentra …\arrancar.vbs» de la v1.0.0 (exe obsoleto sin los
lanzadores): reinstala ENCIMA de la v1.0.0 sin desinstalar y abre
el atajo «DMVoiceChanger Web»:

- **Tiene TODO lo de la web**: las 17 voces de personajes con iconos y
  colores, editor DSP completo, pestaña Leer con favoritos + cola de
  escenas + render WAV, forja por descripción, packs de voces
  export/import, atajos de teclado, grabación de sesión, temas.
- Instalación **por usuario** (sin permisos de administrador), en
  `%LOCALAPPDATA%\Programs\DMVoiceChangerWeb`.
- Lleva **Node.js 22 portable + la app compilada**: no instala ni toca
  nada del sistema. El servidor local escucha SOLO en 127.0.0.1:3987 y la
  app se abre en tu navegador (Chrome/Edge/Firefox).
- Sin conexión siguen funcionando: voces, editor, micrófono, grabación,
  cola de escenas (TTS del navegador). Con conexión: catálogo FakeYou.
- La **forja por descripción** usa la IA cuando el servicio responde y,
  si no, la nueva **forja heurística** (reglas de oficio) — nunca se
  queda en error seco.
- Tus datos: favoritos/historial en `%LOCALAPPDATA%\DMVoiceWeb\voces.db`
  (sobreviven a desinstalar); voces y ajustes en el localStorage del
  navegador (igual que la web).
- Si algo no arranca: menú inicio → DMVoiceChanger Web → **Modo
  depuración** (consola visible con el error).

Fuente y proceso reproducible: `packaging-web/` en el repo
(`instalador-web.nsi` + `construir_instalador_web.sh` + README).

## DMVoiceChanger.exe (2026-11-17, v1.1.3) — LEGADO (PyQt, descartado)

La versión de escritorio PyQt6 (`voz_dnd/`), mantenida solo como archivo.
**Descartada como entregable** el 2026-11-17: nunca alcanzó la paridad con
la web (ver `packaging-web/README.md`). No la instales salvo curiosidad
histórica; el instalador oficial es el de arriba.

- Instalación por usuario, runtime Python 3.14 embebido + PyQt6 + pip.
- v1.1.0: gestor de motores IA, packs ZIP, fundación de clonación.
- v1.1.1–v1.1.3: cadena de arreglos de arranque (._pth aislado → atajo
  con ruta relativa → crash de `PestanaAjustes` al construir la UI).
