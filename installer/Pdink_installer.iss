#define MyAppName "Pdink"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Omar Mannaa"
#define MyAppURL "https://github.com/omaragain/pdink"
#define MyAppExeName "Pdink.exe"
#define MyAppUserModelId "OmarMannaa.Pdink"

[Setup]
AppId={{A2076D02-D741-4E0C-A47A-0D0DB74FDF41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Pdink
DefaultGroupName=Pdink
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=Pdink-Setup-{#MyAppVersion}
SetupIconFile=..\assets\Pdink.ico
UninstallDisplayIcon={app}\Pdink.exe
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoVersion={#MyAppVersion}.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Files]
Source: "..\dist\Pdink\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pdink"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\Pdink.ico"; IconIndex: 0; AppUserModelID: "{#MyAppUserModelId}"
Name: "{autodesktop}\Pdink"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\Pdink.ico"; IconIndex: 0; AppUserModelID: "{#MyAppUserModelId}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Pdink"; Flags: nowait postinstall skipifsilent
