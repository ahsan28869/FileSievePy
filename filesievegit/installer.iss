; -- installer.iss --
; FileSieve Installer Script
; Publisher: AHS

#define MyAppName "FileSieve"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AHS"
#define MyAppDeveloper "AHS"
#define MyAppExeName "FileSieve.exe"

; Path to the PyArmor onedir output folder
;   - If exe is at dist\main\FileSieve.exe       → use "D:\filesieve\dist\main"
;   - If exe is at dist\FileSieve\FileSieve.exe  → use "D:\filesieve\dist\FileSieve"
#define MyAppDistDir "D:\filesieve\dist\FileSieve"

; Path to the icon
#define MyAppIcon "D:\filesieve\icon.ico"

[Setup]
; Unique GUID — regenerate at https://www.guidgenerator.com/
AppId={{8F4C1D2A-9B3E-4F7A-8C1D-5E6F7A8B9C0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (C) 2026 {#MyAppDeveloper}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Compression
Compression=lzma2/max
SolidCompression=yes

; Require admin rights for Program Files
PrivilegesRequired=admin

; Output
OutputDir=D:\filesieve\installer_output
OutputBaseFilename=FileSieve_Setup_v{#MyAppVersion}

; Icon for installer and Add/Remove Programs
SetupIconFile={#MyAppIcon}

; Modern wizard
WizardStyle=modern

; 64-bit only
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Minimum Windows version
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start FileSieve when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Copy the entire PyArmor onedir output
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Startup shortcut (optional)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\_internal\__pycache__"