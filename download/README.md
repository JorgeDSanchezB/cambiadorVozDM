Here are all the generated files.

## DMVoiceChanger.exe (2026-11-16, v1.1.0)

Instalador de Windows para la app de escritorio (`voz_dnd/`), ~96 MB:

- Instalación **por usuario** (sin permisos de administrador), en
  `%LOCALAPPDATA%\Programs\DMVoiceChanger`.
- Lleva **todo incluido**: runtime Python 3.14 embebido + PyQt6 +
  dependencias + pip — no requiere instalar Python.
- Crea accesos directos (Menú de inicio + Escritorio) y desinstalador real
  en «Aplicaciones instaladas».
- **Nuevo en 1.1.0** (funciones de VoiceStudio): gestor de motores IA en
  Ajustes (con botón «Instalar vía ONNX (CPU)» que funciona gracias al pip
  incluido), packs de voces export/import ZIP y fundación de clonación de
  voz con consentimiento obligatorio.
- Nota honesta: el modo IA (RVC) no va preinstalado — la app degrada a DSP
  sin él y se instala desde Ajustes si se quiere; la pestaña «Leer» del
  escritorio necesita internet (edge-tts).

Fuente y proceso reproducible: `voz_dnd/packaging-windows/`
(`instalador.nsi` + `construir_instalador.sh` + README).
