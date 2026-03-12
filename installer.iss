; Inno Setup script for Gestion Magasin POS
#define MyAppName "Gestion Magasin POS"
#define MyAppVersion "1.0.2"
#define MyAppPublisher "SteadEvent7"
#define MyAppExeName "GestionMagasinPOS.exe"
#define MyDataRoot "{commonappdata}\GestionMagasinPOS"

[Setup]
AppId={{A0E58D29-5514-4CC2-BE73-66CF94AF11E0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GestionMagasinPOS
DefaultGroupName=Gestion Magasin POS
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Setup_GestionMagasinPOS
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; GroupDescription: "Raccourcis"; Flags: unchecked
Name: "startupicon"; Description: "Lancer automatiquement au demarrage de Windows"; GroupDescription: "Raccourcis"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Dirs]
Name: "{#MyDataRoot}"
Name: "{#MyDataRoot}\backups"
Name: "{#MyDataRoot}\exports"
Name: "{#MyDataRoot}\logs"

[Icons]
Name: "{autoprograms}\Gestion Magasin POS"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Gestion Magasin POS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{commonstartup}\Gestion Magasin POS"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Gestion Magasin POS"; Flags: nowait postinstall skipifsilent
