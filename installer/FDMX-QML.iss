; Experimental ADM QML preview installer — does not replace the stable Widgets build
#define AppName "ADM QML Preview"
#define AppVersion "6.54"
#define AppPublisher "ADM Project"

[Setup]
AppId={{9C6E51A8-3B29-4F13-8F9D-AD6A16540001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\ADM QML Preview
DefaultGroupName=ADM QML Preview
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ADM-QML-Preview-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\ADM QML.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist-qml\ADM QML\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ADM QML Preview"; Filename: "{app}\ADM QML.exe"; IconFilename: "{app}\ADM QML.exe"
Name: "{autodesktop}\ADM QML Preview"; Filename: "{app}\ADM QML.exe"; IconFilename: "{app}\ADM QML.exe"

[Run]
Filename: "{app}\ADM QML.exe"; Description: "Launch ADM QML Preview"; Flags: postinstall nowait skipifsilent
