Here are all the generated files.

## DMVoiceChanger.exe (2026-11-16, v1.1.1)

Instalador de Windows para la app de escritorio (`voz_dnd/` del repo
cambiadorVozDM), ~101 MB:

- Instalación **por usuario** (sin permisos de administrador), en
  `%LOCALAPPDATA%\Programs\DMVoiceChanger`.
- Lleva **todo incluido**: runtime Python 3.14 embebido + PyQt6 +
  dependencias + pip — no requiere instalar Python.
- Crea accesos directos (Menú de inicio + Escritorio) y desinstalador real
  en «Aplicaciones instaladas».
- **v1.1.0** (funciones de VoiceStudio): gestor de motores IA en Ajustes
  (botón «Instalar vía ONNX (CPU)» con el pip incluido), packs de voces
  export/import ZIP y fundación de clonación de voz con consentimiento.
- **v1.1.1** (arreglo de arranque): el Python embebido corre en modo
  aislado y `pythonw.exe main.py` moría en silencio («doble clic y nada
  pasa»). Ahora el `._pth` incluye `..\app` y los atajos ejecutan
  `runtime\lanzar_app.py`, que registra cualquier fallo en
  `app\logs\arranque.log` (además de `DMVoiceChanger-Depuracion.bat` con
  consola visible).
- Nota honesta: el modo IA (RVC) no va preinstalado — la app degrada a DSP
  sin él y se instala desde Ajustes si se quiere; la pestaña «Leer» del
  escritorio necesita internet (edge-tts).

Fuente y proceso reproducible: `voz_dnd/packaging-windows/` en el repo
(`instalador.nsi` + `construir_instalador.sh` + README).
