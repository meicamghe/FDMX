; GNS Downloader Windows installer — compressed onedir distribution
#define AppName "GNS Downloader"
#define AppVersion "6.37"
#define AppPublisher "GNS Downloader Project"

[Setup]
SetupIconFile=gns-downloader.ico
AppId={{7E58A21D-6D3D-4F12-9C73-2C16A5F03636}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\GNS Downloader
DefaultGroupName=GNS Downloader
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=GNS-Downloader-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\GNS Downloader.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\GNS Downloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\GNS Downloader"; Filename: "{app}\GNS Downloader.exe"; IconFilename: "{app}\GNS Downloader.exe"
Name: "{autodesktop}\GNS Downloader"; Filename: "{app}\GNS Downloader.exe"; IconFilename: "{app}\GNS Downloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GNS Downloader.exe"; Description: "Launch GNS Downloader"; Flags: postinstall nowait skipifsilent
