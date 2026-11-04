; Instalador de Publicador para Windows (NSIS)
Unicode true
!include "MUI2.nsh"
Name "Publicador multi-red"
OutFile "Publicador-Setup.exe"
InstallDir "$LOCALAPPDATA\Publicador"
RequestExecutionLevel user
!define MUI_FINISHPAGE_RUN "$INSTDIR\Publicador.exe"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

Section "Instalar"
  SetOutPath "$INSTDIR"
  File "dist\Publicador.exe"
  File "LEEME.md"
  CreateShortcut "$DESKTOP\Publicador.lnk" "$INSTDIR\Publicador.exe"
  CreateDirectory "$SMPROGRAMS\Publicador"
  CreateShortcut "$SMPROGRAMS\Publicador\Publicador.lnk" "$INSTDIR\Publicador.exe"
  CreateShortcut "$SMPROGRAMS\Publicador\Desinstalar.lnk" "$INSTDIR\Desinstalar.exe"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Publicador" "DisplayName" "Publicador multi-red"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Publicador" "UninstallString" "$INSTDIR\Desinstalar.exe"
SectionEnd

Section "Uninstall"
  ; config.json (tus credenciales) se conserva a propósito
  Delete "$INSTDIR\Publicador.exe"
  Delete "$INSTDIR\LEEME.md"
  Delete "$INSTDIR\Desinstalar.exe"
  Delete "$DESKTOP\Publicador.lnk"
  RMDir /r "$SMPROGRAMS\Publicador"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Publicador"
SectionEnd
