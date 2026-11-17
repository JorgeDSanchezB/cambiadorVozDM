; ============================================================
;  DMVoiceChanger Web - instalador de Windows (NSIS 3)
;  LA MISMA APP WEB (La Forja de Voces) como programa de
;  escritorio: servidor Next.js local (127.0.0.1:3987) con
;  Node.js portable; se abre en el navegador por defecto.
;  Instalación por usuario: NO requiere administrador.
;  Build: NSISDIR=/home/z/nsis/NSIS makensis instalador-web.nsi
; ============================================================

Unicode true
!include "MUI2.nsh"

!define PRODUCTO       "DMVoiceChangerWeb"
!define PRODUCTO_CORTO "DMVoiceChanger Web"
!define PRODUCTO_LARGO "DMVoiceChanger Web — La Forja de Voces"
!define VERSION        "1.0.0"
!define VI_VERSION     "1.0.0.0"
!define EDITOR         "La Forja del DJ"
!define URL_AYUDA      "https://github.com/JorgeDSanchezB/cambiadorVozDM"
!define CLAVE_DESINST  "Software\Microsoft\Windows\CurrentVersion\Uninstall\DMVoiceChangerWeb"
!define PUERTO         "3987"

Name "${PRODUCTO_CORTO}"
OutFile "DMVoiceChangerWeb.exe"
SetCompressor /SOLID lzma
RequestExecutionLevel user

InstallDir "$LOCALAPPDATA\Programs\DMVoiceChangerWeb"
InstallDirRegKey HKCU "Software\${PRODUCTO}" "InstallDir"

VIProductVersion "${VI_VERSION}"
VIAddVersionKey /LANG=1034 "ProductName" "${PRODUCTO_LARGO}"
VIAddVersionKey /LANG=1034 "FileDescription" "Instalador de ${PRODUCTO_CORTO}"
VIAddVersionKey /LANG=1034 "LegalCopyright" "(c) ${EDITOR}"
VIAddVersionKey /LANG=1034 "CompanyName" "${EDITOR}"
VIAddVersionKey /LANG=1034 "FileVersion" "${VI_VERSION}"
VIAddVersionKey /LANG=1034 "ProductVersion" "${VI_VERSION}"

!define MUI_ICON   "DMVoiceChanger.ico"
!define MUI_UNICON "DMVoiceChanger.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Bienvenido al instalador de ${PRODUCTO_CORTO}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instalará ${PRODUCTO_CORTO} en tu equipo.$\r$\n$\r$\nEs LA MISMA app web de La Forja de Voces (voces, editor, forja, cola de escenas, favoritos, packs), funcionando como programa local: un servidor privado en tu PC que se abre en tu navegador. No requiere permisos de administrador ni conexión para las voces DSP.$\r$\n$\r$\nNota: la app se abre en tu navegador (Chrome/Edge/Firefox) en http://127.0.0.1:${PUERTO} — es normal.$\r$\n$\r$\nSi algo no arranca, ejecuta DMVoiceWeb-Depuracion.bat y pega lo que salga.$\r$\n$\r$\n$_CLICK"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE     "Instalación completada"
!define MUI_FINISHPAGE_TEXT      "${PRODUCTO_CORTO} ya está forjado en tu equipo.$\r$\n$\r$\nAl pulsar terminar se abrirá la app en tu navegador (déjale unos segundos la primera vez)."
!define MUI_FINISHPAGE_RUN       "$INSTDIR\arrancar.vbs"
!define MUI_FINISHPAGE_RUN_FUNCTION "LanzarApp"
!define MUI_FINISHPAGE_RUN_TEXT  "Abrir ${PRODUCTO_CORTO} ahora"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

; ---------- Instalación ----------
Section "Instalar" SecInstalar
  ; El desinstalador de la versión antigua (PyQt) es aparte; este convive.
  SetOutPath "$INSTDIR"
  File "payload\DMVoiceChanger.ico"
  File "payload\arrancar.vbs"
  File "payload\detener.vbs"
  File "payload\detener.ps1"
  File "payload\DMVoiceWeb-Depuracion.bat"

  DetailPrint "Copiando Node.js portable..."
  SetOutPath "$INSTDIR\runtime"
  File "payload\runtime\node.exe"

  DetailPrint "Copiando la aplicación web (esto tarda un poco)..."
  SetOutPath "$INSTDIR\app"
  File /r "payload\app\*.*"

  DetailPrint "Creando accesos directos..."
  CreateDirectory "$SMPROGRAMS\${PRODUCTO_CORTO}"
  CreateShortCut "$SMPROGRAMS\${PRODUCTO_CORTO}\${PRODUCTO_CORTO}.lnk" \
                 "wscript.exe" '"$INSTDIR\arrancar.vbs"' \
                 "$INSTDIR\DMVoiceChanger.ico" 0 SW_SHOWNORMAL "" \
                 "La Forja de Voces — cambiador de voz del DM" "$INSTDIR"
  CreateShortCut "$SMPROGRAMS\${PRODUCTO_CORTO}\Detener servidor.lnk" \
                 "wscript.exe" '"$INSTDIR\detener.vbs"' \
                 "$INSTDIR\DMVoiceChanger.ico" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCTO_CORTO}\Modo depuración.lnk" \
                 "$INSTDIR\DMVoiceWeb-Depuracion.bat" "" \
                 "$INSTDIR\DMVoiceChanger.ico" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCTO_CORTO}\Desinstalar.lnk" \
                 "$INSTDIR\uninstall.exe" "" "$INSTDIR\DMVoiceChanger.ico" 0
  CreateShortCut "$DESKTOP\${PRODUCTO_CORTO}.lnk" \
                 "wscript.exe" '"$INSTDIR\arrancar.vbs"' \
                 "$INSTDIR\DMVoiceChanger.ico" 0 SW_SHOWNORMAL "" \
                 "La Forja de Voces — cambiador de voz del DM" "$INSTDIR"

  DetailPrint "Registrando la desinstalación..."
  WriteRegStr HKCU "Software\${PRODUCTO}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayName" "${PRODUCTO_LARGO}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "Publisher" "${EDITOR}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "URLInfoAbout" "${URL_AYUDA}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayIcon" "$INSTDIR\DMVoiceChanger.ico"
  WriteRegStr HKCU "${CLAVE_DESINST}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${CLAVE_DESINST}" "QuietUninstallString" "$INSTDIR\uninstall.exe /S"
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "NoModify" 1
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "NoRepair" 1
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "EstimatedSize" 260000

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; ---------- Lanzamiento desde la página final ----------
Function LanzarApp
  Exec 'wscript.exe "$INSTDIR\arrancar.vbs"'
FunctionEnd

; ---------- Desinstalación ----------
Section "Uninstall"
  DetailPrint "Deteniendo el servidor local si sigue vivo..."
  ExecWait 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\detener.ps1"' $0

  DetailPrint "Eliminando archivos de la aplicación..."
  RMDir /r "$INSTDIR"
  RMDir /r "$SMPROGRAMS\${PRODUCTO_CORTO}"
  Delete "$DESKTOP\${PRODUCTO_CORTO}.lnk"
  DeleteRegKey HKCU "${CLAVE_DESINST}"
  DeleteRegKey HKCU "Software\${PRODUCTO}"
  DetailPrint "Listo. La base de datos de voces queda en %LOCALAPPDATA%\DMVoiceWeb por si reinstalas."
SectionEnd
