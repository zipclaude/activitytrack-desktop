; SPDX-License-Identifier: GPL-3.0-or-later
; The Windows installer (docs/DESIGN.md §8): per user, no administrator
; rights, not signed (D10). Built by .gitlab-ci.yml (job windows-installer) with
; AT_VERSION (0.9.4-beta1) and AT_NUMVERSION (0.9.4) in the environment,
; from PyInstaller's dist\ActivityTrack folder.

#define AppVersion GetEnv("AT_VERSION")
#define NumVersion GetEnv("AT_NUMVERSION")

[Setup]
; never change it: updates find the installed copy by it
AppId={{CB58A812-6812-4ADF-B1E1-41EDC4890750}
AppName=ActivityTrack
AppVersion={#AppVersion}
AppVerName=ActivityTrack {#AppVersion}
AppPublisher=ActivityTrack
AppPublisherURL=https://gitlab.com/activitytrack/activitytrack-desktop
AppSupportURL=https://gitlab.com/activitytrack/activitytrack-desktop/-/issues
VersionInfoVersion={#NumVersion}
DefaultDirName={localappdata}\Programs\ActivityTrack
DefaultGroupName=ActivityTrack
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=ActivityTrackDesktop-{#AppVersion}-setup
SetupIconFile=activitytrack-desktop.ico
UninstallDisplayIcon={app}\ActivityTrack.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; a running ActivityTrack is closed for the update, and started again
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
it.AutoStart=Avvia ActivityTrack all'accesso a Windows
en.AutoStart=Start ActivityTrack when signing in to Windows
de.AutoStart=ActivityTrack bei der Windows-Anmeldung starten
es.AutoStart=Iniciar ActivityTrack al iniciar sesión en Windows

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\ActivityTrack\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ActivityTrack"; Filename: "{app}\ActivityTrack.exe"
Name: "{autodesktop}\ActivityTrack"; Filename: "{app}\ActivityTrack.exe"; Tasks: desktopicon

[Registry]
; the same value the application's setting switches (autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ActivityTrack"; ValueData: """{app}\ActivityTrack.exe"" --hidden"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\ActivityTrack.exe"; Description: "{cm:LaunchProgram,ActivityTrack}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the program's folder only: the data (%APPDATA%\activitytrack-desktop) stays
Type: filesandordirs; Name: "{app}"
