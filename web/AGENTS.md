# AGENTS.md — versión web (`web/`, rama `feat/web-app`)

Reglas acumuladas del desarrollo de la web, traídas del entorno de
despliegue (sandbox) donde la app corre en el puerto 3000. Complementa el
`AGENTS.md` del raíz (regla de espejo escritorio ↔ web). Antes de tocar,
léelo: hay decisiones de usuario que NO se deben regresionar.

## Sistema visual aprobado — «La Forja del DJ» (no regresionar)

Los visuales quedaron al nivel deseado (estándar tipo Awwwards). Cualquier
cambio futuro debe CONSERVAR estas decisiones; no "mejorarlas" hacia atrás:

- **Tema**: fantasía oscuro cálido — carbón, ámbar de antorcha y oro viejo
  (tokens en `src/app/globals.css`). PROHIBIDO azules/índigos.
- **Tipografía**: Cinzel (`font-display`, woff2 local en `src/app/fonts/`)
  para títulos/marca; Geist Sans para cuerpo; Geist Mono para números,
  atajos y datos técnicos.
- **Profundidad**: tarjetas de vidrio (`bg-card/60 backdrop-blur`; el
  `Card` base de shadcn ya trae `bg-card/75 + backdrop-blur-sm`), bordes
  `border-border/60`, brillos ámbar suaves (`shadow-primary/10–20`), jamás
  sombras duras ni gris plano.
- **Fondo vivo**: `fondo-escena.tsx` (brasas flotantes + viñeta + grano);
  mantener `pointer-events-none` y densidad baja para no robar GPU.
- **Motion**: micro-interacciones discretas (200–400 ms, ease-out): hover
  con elevación, `destello-linea` en bordes superiores, ecualizador en
  vivo. Nada de animaciones que bloqueen la interacción.
- **Héroe**: `heroe.tsx` con titular grande en Cinzel + tarjeta «Voz en
  uso» a la derecha; estelas ornamentales (`─ ◆ ─`) entre secciones.
- **Layout**: `min-h-screen flex flex-col` con pie `mt-auto` (regla fija);
  contenido en `max-w-6xl`; rejillas `sm:grid-cols-2 lg:grid-cols-3`.
- **Accesibilidad**: contraste AA sobre el carbón, `focus-visible` con
  anillo ámbar, targets ≥ 44 px, `aria-label` en botones solo-icono.

## Regla de copy para el usuario final

La UI es para el Dungeon Master que la usa en su mesa: **microcopy breve y
funcional, sin texto interno de desarrollo**. Prohibido mostrar en la
interfaz: ramas de git (`feat/web-app`, `main`), espejos (`voz_dnd`), rutas
de datos (`data/voices/`), detalles de implementación, limitaciones
técnicas o disclaimers largos. Eso vive aquí y en el README, nunca en
pantalla. Los subtítulos de sección solo se justifican si dan una
instrucción accionable («Escribe o carga un .txt.»).

## Orden de pestañas y nombre «Creador» (petición explícita del usuario)

La pestaña del estudio DSP se llama **Creador** (ya no «Editor») y el orden
es: **Voces → Leer → Creador → Ajustes** (el usuario la quiere después de
Leer). El valor interno es `creador` en `page.tsx`; no restaurar el nombre
«Editor».

## Pestaña Leer — modelo mental «¿Quién lee?» (no regresionar)

Hubo confusión con DOS controles que cambiaban el timbre a la vez («Voz del
servidor» + «Aplicar la voz activa»). Rediseño aprobado:

- **Una sola decisión visible**: combobox con búsqueda «¿Quién lee?» con
  los grupos «Narradores» (mujer por defecto / hombre), «Tus voces» (voz
  activa + catálogo) y el elenco de personajes (FakeYou: favoritas + todos,
  SOLO con su nombre de voz — sin @creador ni descripciones, petición
  explícita del usuario). Una línea dinámica bajo el control dice qué se
  escuchará.
- **Card «Favoritos»** (debajo de «Texto a leer», petición explícita del
  usuario): chips de las voces marcadas con estrella (`favoritas` del store
  `personajes`, resueltas contra el catálogo). Al pulsar un chip se usa la
  MISMA ruta de selección (`elegir('fy:<token>')`), o sea que «¿Quién lee?»
  queda elegido automáticamente. Estados: carga, catálogo caído con
  reintento y vacío honesto («Aún no tienes favoritas»). No sustituye al
  grupo «★ Favoritas» del combobox.
- **Pipeline en una frase**: la voz neural del servidor genera el audio
  base y la cadena DSP del personaje se aplica UNA sola vez sobre él.
- **La voz base del servidor** es una sola (tongtong) y NO se expone en la
  UI: es materia prima. Debe coincidir con la base de «Probar voz»
  (`VOZ_SERVIDOR_POR_DEFECTO`).
- Técnica: `OpcionesLectura.parametros?: ParametrosDSP` (undefined = sin
  efectos); `leerConServidor` fija la cadena con `fijarParametrosLectura`
  y la restaura al terminar. NUNCA volver a exponer dos selectores de voz
  simultáneos en esta pestaña.

## Fusión Personajes → Leer (la pestaña Personajes YA NO EXISTE)

Personajes «hacía prácticamente lo mismo que Leer»: se fusionó sin perder
funciones (verificado en navegador):

- **El elenco vive en «¿Quién lee?»** de Leer: valor `fy:<token>`. Al
  elegir un personaje el motor pasa a FakeYou (cola del store `personajes`,
  sin DSP ni velocidad — esos controles se OCULTAN, no se deshabilitan),
  el texto se recorta a 500 (límite FakeYou, con aviso) y el audio sale del
  reproductor `/api/personajes/audio?id=…`. La selección se sincroniza con
  `vozSeleccionadaToken` del store para que `generar()` siga funcionando.
- **Favoritas**: grupo «★ Favoritas» arriba del elenco + botón estrella
  junto a la línea de ayuda para marcar/quitar la voz elegida.
- **Historial** («Generaciones recientes») vive al pie de Leer.
  Reproducir/Detener/Descargar WAV sirven a los dos motores (branch por
  `esFakeYou`).
- **La cuenta de FakeYou** (token de sesión) vive en Ajustes
  (`TarjetaCuentaFakeYou`), porque es un ajuste, no un flujo de lectura.
- Rutas `/api/personajes/*` + `src/lib/fakeyou.ts` + store `personajes.ts`
  con Prisma/SQLite (`FavoritoPersonaje`, `GeneracionPersonaje`). NO
  recrear la pestaña Personajes ni duplicar el catálogo en otro sitio; el
  botón «Elenco de personajes» del héroe lleva a Leer.

## Voces del servidor — decisión por ASR (no reintroducir las 7)

El usuario quiere UNA voz de hombre y UNA de mujer que hablen bien español.
Las 7 voces del SDK se evaluaron objetivamente: TTS de cada una leyendo
«Bienvenidos, aventureros, a la mazmorra del dragón» → transcripción ASR +
análisis de F0 (autocorrelación) para el género:

- `tongtong` 212 Hz (mujer): transcripción EXACTA → **voz base única**.
- `luodo` 270 Hz: «Buying Vinus Adventures» → fonética INGLESA.
- `xiaochen` 126 Hz (único hombre): «Andros Andros a la Mysmora» →
  ininteligible.
- `chuichui` «Bienavidos»; `jam`/`kazi`/`douji` (247/258/192 Hz, mujeres):
  pronunciación irregular.

Resultado en `src/lib/tts.ts`: `VOCES_SERVIDOR` = solo tongtong
(«Narradora · mujer»); el **narrador hombre** es `PRESET_NARRADOR_HOMBRE`
(pitch −5 st, formantes 1.25×, +2.5 dB graves) aplicado a la misma base —
la fonética española sobrevive al cambio de tono (verificado con ASR).
«¿Quién lee?» agrupa: Narradores (mujer/hombre) y Tus voces (activa +
catálogo). Por defecto: narradora. NO volver a ofrecer las otras voces del
SDK en la UI.

Además: `leerConNavegador` espera `voiceschanged` (getVoices() llega vacío
en Chrome al primer intento → el respaldo leía español con voz inglesa) y
prefiere es-ES/es-MX/es-419.

## Catálogo: borrado permanente de 3 voces

El usuario pidió eliminar para siempre **Goku (Mario Castañeda)**,
**IA Demo** y **Mujer Decidida**: se borraron de la FUENTE
(`voz_dnd/data/voces/{goku,ia_demo,mujer_decidida}.json`) y el catálogo web
se REGENERÓ con `scripts/sincronizar_voces.py` (17 voces). No
reintroducirlas ni regenerarlas desde copias viejas.

## Atajos de teclado — asignación MANUAL (no regresionar a solo-lectura)

El usuario no quiere atajos impuestos: la tecla que trae cada voz del
catálogo es SOLO una sugerencia inicial y el dueño es el usuario, desde
**Ajustes › Atajos de teclado** (`tarjeta-atajos.tsx`):

- Cada voz (base, oculta-restaurable y personalizada) tiene un chip con su
  tecla; al pulsarlo entra en **modo captura** (una sola voz a la vez,
  `capturandoAtajoId` del store): la próxima F1–F12, con o sin Shift, queda
  asignada. Esc cancela; Borrar/Backspace quita el atajo; clic fuera
  cancela.
- **Las voces nuevas entran solas**: toda voz creada en el Creador aparece
  automáticamente en la card con «Sin atajo» y es asignable igual que las
  base (verificado: crear → asignar Shift+F12 → dispara → persiste en su
  propio dato). La lista de la card SIEMPRE es el store `voces` completo.
- **Capacidad explícita**: el mapa tiene 24 teclas (F1–F12 y
  Shift+F1–F12); la card muestra «N de 24 teclas libres» contando también
  las voces ocultas (las conservan para cuando se restauren).
- **Tecla de propiedad exclusiva**: si otra voz ya la tenía, se le quita
  (con toast de aviso). El gancho global (`use-atajos.ts`) queda
  silenciado durante la captura y detecta el combo con `normalizarAtajo`
  (`src/lib/voces.ts`).
- **Persistencia**: voces base → overrides en localStorage
  `voz_dnd_web.atajos` (string = tecla propia, null explícito = quitada;
  el catálogo generado NUNCA se toca). Voces personalizadas → el atajo
  vive en su propio dato (`voz_dnd_web.voces_personalizadas`). Aplicados
  en `init()` también sobre las ocultas para que conserven su tecla al
  restaurarse.
- Botón «Restaurar sugerencia inicial»: borra overrides y deja las
  personalizadas sin tecla. «Restablecer datos locales» también limpia
  `voz_dnd_web.atajos`.
- NO volver a convertir la card en una lista de solo lectura con badges.
## Forja por descripción (Creador) — Voice Design estilo VoiceStudio

Petición explícita del usuario (idea de VoiceStudio, implementación propia):
en Creador hay una card «Forja por descripción» ENCIMA del editor. Describe
la voz con palabras → la IA del servidor propone nombre + icono + color +
cadena DSP completa → «Guardar voz en la forja» la crea como voz
personalizada (con icono/color del LLM) y la deja como voz activa.

- Ruta: `POST /api/creador/describir` (z-ai-web-dev-sdk, SOLO servidor).
  Contrato de salida: `{ ok, voz: { nombre, icono, color, resumen,
  parametros_dsp } }`.
- **El servidor SIEMPRE acota y redondea los 10 parámetros contra
  `data/parametros.json`** (acotarParametros). La IA nunca decide los
  límites; si falta un parámetro → 502 con mensaje honesto.
- Quirk del SDK: el prompt de sistema se envía con role `assistant`
  (convención documentada del skill LLM), no `system`.
- `crearVozPersonalizada(nombre, params, extras?)` acepta `extras`
  `{ icono?, color? }` opcional con validación (icono ≤ 2 grafemas, color
  `#rrggbb`); sin extras se comporta como antes (★ + paleta).
- La card vive en `tarjeta-forja-descripcion.tsx`; el editor de sliders
  queda debajo intacto. No mover la card ni volver a un solo paso sin
  guardar.
## Cola de escenas (Leer) — narración por lotes estilo Batch Queue

Petición explícita del usuario (idea de VoiceStudio): card «Cola de escenas»
en Leer, DEBAJO de «Síntesis de voz» y SOLO cuando no hay voz FakeYou
elegida. Varios textos → un WAV por escena (archivo por capítulo), con la
voz elegida y su cadena DSP.

- Persistencia: `voz_dnd_web.cola_escenas` en localStorage, lectura
  tolerante a datos corruptos (como el resto de datos); estados de render
  NO persisten (vuelven a «En la cola» al recargar).
- Corazón técnico: `renderizarLecturaAWav()` en `lib/tts.ts` (refactor:
  `descargarWavLectura` ahora delega en ella y se comporta IGUAL que
  antes). La cola la llama escena a escena con nombre de archivo propio
  (`escena_<n>_<titulo>_<marca>`) y ~900 ms entre descargas (los
  navegadores bloquean ráfagas de descargas múltiples).
- Mantener SIEMPRE: render secuencial de fragmentos (fix 005, nunca
  superponer) y aborto limpio con AbortController propio de la cola.
- Con FakeYou o motor «navegador» la card se muestra con mensaje honesto y
  deshabilitada (no renderiza WAV).
- Botón «Enviar el texto a leer» manda el texto del cuadro principal como
  nueva escena. Máximo 30 escenas.
