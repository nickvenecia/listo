; Inno Setup script — builds Listo-Setup.exe (per-user install, no admin needed)
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1C7F2E-4E0B-4E8B-9D0B-1A57F0A11570}
AppName=Listo
AppVersion={#MyAppVersion}
AppPublisher=Bad Filmmaker
DefaultDirName={localappdata}\Programs\Listo
DefaultGroupName=Listo
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Listo-Setup
SetupIconFile=..\..\build\icon.ico
UninstallDisplayIcon={app}\Listo.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\dist\Listo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Listo"; Filename: "{app}\Listo.exe"
Name: "{userdesktop}\Listo"; Filename: "{app}\Listo.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Listo.exe"; Description: "Open Listo now"; Flags: nowait postinstall skipifsilent
