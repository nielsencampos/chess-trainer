; Inno Setup script for the Windows installer (built in CI by .github/workflows/desktop.yml).
;   iscc /DAppVersion=0.1.0 /DSourceDir=build\dist\chess-trainer /DOutputDir=build\out ^
;        /DOutputName=chess-trainer-v0.1.0-windows-x64-setup desktop\windows\chess-trainer.iss
; A per-user install, no administrator needed: the program goes to
; %LOCALAPPDATA%\Programs\Chess Trainer. The data stays in %LOCALAPPDATA%\chess-trainer, which
; the uninstaller never touches. Files an installer writes carry no "downloaded from the
; internet" mark, which a zip extracted by Explorer passes on to every file.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change the AppId: Windows recognizes upgrades and the uninstaller by it.
AppId={{5B0C8E2A-4F1D-4C7E-9A3B-2D6F8E1C7A40}
AppName=Chess Trainer
AppVersion={#AppVersion}
AppPublisher=chess-trainer
AppPublisherURL=https://github.com/nielsencampos/chess-trainer
DefaultDirName={autopf}\Chess Trainer
DefaultGroupName=Chess Trainer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\chess-trainer.exe
UninstallDisplayName=Chess Trainer
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Chess Trainer"; Filename: "{app}\chess-trainer.exe"
Name: "{autodesktop}\Chess Trainer"; Filename: "{app}\chess-trainer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\chess-trainer.exe"; Description: "{cm:LaunchProgram,Chess Trainer}"; Flags: nowait postinstall skipifsilent
