#define MyAppName "Vision Agent"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "VisionTestAI"
#define MyAppExeName "VisionAgent.exe"

[Setup]
AppId={{8AD4EEB0-7152-4F49-9D2A-AEF83C548D91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VisionAgent
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer-output
OutputBaseFilename=VisionAgent-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=classic
SetupIconFile=..\Assets\vision-agent.ico
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Tạo lối tắt trên màn hình"; GroupDescription: "Tùy chọn:"; Flags: unchecked

[Files]
Source: "..\publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở Vision Agent"; Flags: nowait postinstall skipifsilent
