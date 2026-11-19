Unicode true
!ifndef APP_EXE
  !define APP_EXE "..\publish\VisionAgent.exe"
!endif
!ifndef OUTPUT_EXE
  !define OUTPUT_EXE "..\installer-output\VisionAgent-Setup.exe"
!endif
!ifndef APP_ICON
  !define APP_ICON "..\Assets\vision-agent.ico"
!endif
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!include "MUI2.nsh"

Name "Vision Agent"
Caption "Cài đặt Vision Agent"
OutFile "${OUTPUT_EXE}"
Icon "${APP_ICON}"
InstallDir "$LOCALAPPDATA\Programs\VisionAgent"
InstallDirRegKey HKCU "Software\VisionTestAI\VisionAgent" "InstallLocation"
RequestExecutionLevel user
ShowInstDetails show
ShowUninstDetails show
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Chào mừng cài đặt Vision Agent"
!define MUI_WELCOMEPAGE_TEXT "Vision Agent theo dõi thư mục XML HIS và gửi dữ liệu tới backend QY.$\r$\n$\r$\nBộ cài sẽ cài ứng dụng cho tài khoản Windows hiện tại."
!define MUI_FINISHPAGE_RUN "$INSTDIR\VisionAgent.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Mở Vision Agent ngay"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "Vietnamese"

Section "Install"
  SetOutPath "$INSTDIR"
  File /oname=VisionAgent.exe "${APP_EXE}"
  WriteRegStr HKCU "Software\VisionTestAI\VisionAgent" "InstallLocation" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Vision Agent"
  CreateShortCut "$SMPROGRAMS\Vision Agent\Vision Agent.lnk" "$INSTDIR\VisionAgent.exe"
  CreateShortCut "$SMPROGRAMS\Vision Agent\Gỡ cài đặt.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Vision Agent\Vision Agent.lnk"
  Delete "$SMPROGRAMS\Vision Agent\Gỡ cài đặt.lnk"
  RMDir "$SMPROGRAMS\Vision Agent"
  DeleteRegKey HKCU "Software\VisionTestAI\VisionAgent"
  Delete "$INSTDIR\VisionAgent.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
