; ============================================================
;  DMVoiceChanger - instalador de Windows (NSIS 3)
;  Instalacion por usuario: NO requiere permisos de administrador.
;  Incluye runtime Python embebido (sin instalar nada en el sistema).
;  Build:  NSISDIR=/home/z/nsis/NSIS /home/z/nsis/bin/makensis instalador.nsi
; ============================================================

Unicode true
!include "MUI2.nsh"

!define PRODUCTO       "DMVoiceChanger"
!define PRODUCTO_LARGO "DMVoiceChanger - Cambiador de voz para DM de D&D"
!define VERSION        "1.1.3"
!define VI_VERSION     "1.1.3.0"
!define EDITOR         "La Forja del DJ"
!define URL_AYUDA      "https://github.com/JorgeDSanchezB/cambiadorVozDM"
!define CLAVE_DESINST  "Software\Microsoft\Windows\CurrentVersion\Uninstall\DMVoiceChanger"

Name "${PRODUCTO}"
OutFile "DMVoiceChanger.exe"
SetCompressor /SOLID lzma
RequestExecutionLevel user

InstallDir "$LOCALAPPDATA\Programs\DMVoiceChanger"
InstallDirRegKey HKCU "Software\DMVoiceChanger" "InstallDir"

VIProductVersion "${VI_VERSION}"
VIAddVersionKey /LANG=1034 "ProductName" "${PRODUCTO_LARGO}"
VIAddVersionKey /LANG=1034 "FileDescription" "Instalador de ${PRODUCTO}"
VIAddVersionKey /LANG=1034 "LegalCopyright" "(c) ${EDITOR}"
VIAddVersionKey /LANG=1034 "CompanyName" "${EDITOR}"
VIAddVersionKey /LANG=1034 "FileVersion" "${VI_VERSION}"
VIAddVersionKey /LANG=1034 "ProductVersion" "${VI_VERSION}"

!define MUI_ICON   "DMVoiceChanger.ico"
!define MUI_UNICON "DMVoiceChanger.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Bienvenido al instalador de ${PRODUCTO}"
!define MUI_WELCOMEPAGE_TEXT "Este asistente instalará ${PRODUCTO} en tu equipo.$\r$\n$\r$\nIncluye TODO lo necesario: no requiere Python, ni permisos de administrador, ni configuración.$\r$\n$\r$\nSi la app no abriera nunca, ejecuta ${PRODUCTO}-Depuracion.bat (o mira app\logs\arranque.log; la carpeta logs se crea junto al LEEME.txt).$\r$\n$\r$\n$_CLICK"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE     "Instalación completada"
!define MUI_FINISHPAGE_TEXT      "${PRODUCTO} ya está forjado en tu equipo."
!define MUI_FINISHPAGE_RUN       "$INSTDIR\runtime\pythonw.exe"
!define MUI_FINISHPAGE_RUN_FUNCTION "LanzarApp"
!define MUI_FINISHPAGE_RUN_TEXT  "Iniciar ${PRODUCTO} ahora"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

; ---------- Instalación ----------
Section "Instalar" SecInstalar
  SetOutPath "$INSTDIR"
  File "payload\DMVoiceChanger.ico"
  File "payload\DMVoiceChanger-Depuracion.bat"

  DetailPrint "Copiando el runtime de Python embebido (esto tarda un poco)..."
  SetOutPath "$INSTDIR\runtime"
  File /r "payload\runtime\*.*"

  DetailPrint "Copiando la aplicación..."
  SetOutPath "$INSTDIR\app"
  File /r "payload\app\*.*"

  DetailPrint "Creando accesos directos..."
  CreateDirectory "$SMPROGRAMS\${PRODUCTO}"
  ; IMPORTANTE (lección de la v1.1.1): el script del lanzador se pasa con
  ; RUTA ABSOLUTA y el «Iniciar en» del atajo apunta a runtime\. Con la
  ; combinación anterior (parámetro relativo "lanzar_app.py" + iniciar en
  ; app\) Windows buscaba app\lanzar_app.py, no existía, y pythonw moría
  ; en silencio sin crear ningún registro.
  CreateShortCut "$SMPROGRAMS\${PRODUCTO}\${PRODUCTO}.lnk" \
                 "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\runtime\lanzar_app.py"' \
                 "$INSTDIR\DMVoiceChanger.ico" 0 SW_SHOWNORMAL "" \
                 "Cambiador de voz en tiempo real para DM de D&D" "$INSTDIR\runtime"
  CreateShortCut "$SMPROGRAMS\${PRODUCTO}\Modo depuración.lnk" \
                 "$INSTDIR\DMVoiceChanger-Depuracion.bat" "" \
                 "$INSTDIR\DMVoiceChanger.ico" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCTO}\Desinstalar.lnk" \
                 "$INSTDIR\uninstall.exe" "" "$INSTDIR\DMVoiceChanger.ico" 0
  CreateShortCut "$DESKTOP\${PRODUCTO}.lnk" \
                 "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\runtime\lanzar_app.py"' \
                 "$INSTDIR\DMVoiceChanger.ico" 0 SW_SHOWNORMAL "" \
                 "Cambiador de voz en tiempo real para DM de D&D" "$INSTDIR\runtime"

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
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "EstimatedSize" 230000

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Function LanzarApp
  ; Ruta absoluta al lanzador: con SetOutPath app\ + parámetro relativo
  ; (v1.1.1) Exec resolvía app\lanzar_app.py → no existía → silencio total.
  SetOutPath "$INSTDIR\runtime"
  Exec '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\runtime\lanzar_app.py"'
FunctionEnd

; ---------- Desinstalación ----------
Section "Uninstall"
  DetailPrint "Eliminando archivos de la aplicación..."
  RMDir /r "$INSTDIR"
  RMDir /r "$SMPROGRAMS\${PRODUCTO}"
  Delete "$DESKTOP\${PRODUCTO}.lnk"
  DeleteRegKey HKCU "${CLAVE_DESINST}"
  DeleteRegKey HKCU "Software\${PRODUCTO}"
  DetailPrint "Listo. ¡Hasta la próxima campaña!"
SectionEnd
