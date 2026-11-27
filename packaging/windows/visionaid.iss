; Installateur Windows de VisionAId (Inno Setup 6), appelé par packaging/build.py :
;   iscc /DAppVersion=0.1.0 /DSourceDir=dist\VisionAId /DOutputDir=dist /DIconFile=... visionaid.iss
; Fichier en UTF-8 avec BOM (accents lus correctement par Inno Setup).
; Installation pour l'utilisateur courant (pas de droits administrateur nécessaires).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6D3B1C2E-8A4F-4B7C-9E21-5F0A7C3D9B14}
AppName=VisionAId
AppVersion={#AppVersion}
AppPublisher=VisionAId
DefaultDirName={autopf}\VisionAId
DefaultGroupName=VisionAId
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=VisionAId-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\VisionAId.exe
UninstallDisplayName=VisionAId
CloseApplications=yes
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VisionAId"; Filename: "{app}\VisionAId.exe"
Name: "{autoprograms}\Désinstaller VisionAId"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VisionAId"; Filename: "{app}\VisionAId.exe"; Tasks: desktopicon

[UninstallRun]
; fermer VisionAId (et ses processus de guidage) avant de supprimer ses fichiers
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM VisionAId.exe"; Flags: runhidden; RunOnceId: "StopVisionAId"
; données de l'utilisateur : réglages, certificats, journal, caches et modèles (~3 Go)
Filename: "{app}\VisionAId.exe"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "UninstallData"

[UninstallDelete]
; filet de sécurité si --uninstall n'a pas tout supprimé
Type: filesandordirs; Name: "{userappdata}\VisionAId"
Type: filesandordirs; Name: "{app}"

[Run]
Filename: "{app}\VisionAId.exe"; Description: "{cm:LaunchProgram,VisionAId}"; Flags: nowait postinstall skipifsilent
