; FDMX Windows installer — requires dist/FDMX.exe and dist/fdmx_plugin_worker.exe
#define AppName "FDMX"
#define AppVersion "6.36"
#define AppPublisher "FDMX Project"

[Setup]
AppId={{7E58A21D-6D3D-4F12-9C73-2C16A5F03636}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\FDMX
DefaultGroupName=FDMX
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=FDMX-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\FDMX.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\FDMX.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\fdmx_plugin_worker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\FDMX"; Filename: "{app}\FDMX.exe"
Name: "{autodesktop}\FDMX"; Filename: "{app}\FDMX.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FDMX.exe"; Description: "Launch FDMX"; Flags: postinstall nowait skipifsilent
