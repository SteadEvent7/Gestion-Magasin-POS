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
Name: "db\sqlite"; Description: "SQLite (recommande - sans serveur externe)"; GroupDescription: "Moteur base de donnees"; Flags: exclusive checkedonce
Name: "db\mysql"; Description: "MySQL (multi-postes / serveur)"; GroupDescription: "Moteur base de donnees"; Flags: exclusive
Name: "db\mysql_install"; Description: "Tenter l'installation automatique de MySQL (winget + internet)"; GroupDescription: "Options MySQL"; Flags: unchecked; Check: IsMySqlSelected

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "schema_mysql.sql"; DestDir: "{app}"; Flags: ignoreversion
Source: "schema_sqlite.sql"; DestDir: "{app}"; Flags: ignoreversion

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

[Code]
var
	MySqlPage: TInputQueryWizardPage;

function IsMySqlSelected: Boolean;
begin
	Result := WizardIsTaskSelected('db\mysql');
end;

function IsMySqlAutoInstallSelected: Boolean;
begin
	Result := WizardIsTaskSelected('db\mysql_install');
end;

procedure AddLine(var A: TArrayOfString; const S: string);
var
	N: Integer;
begin
	N := GetArrayLength(A);
	SetArrayLength(A, N + 1);
	A[N] := S;
end;

function ReadEnvExampleValue(const Key: string; const DefaultValue: string): string;
var
	Lines: TArrayOfString;
	I, P: Integer;
	L, K, V: string;
begin
	Result := DefaultValue;
	if not LoadStringsFromFile(ExpandConstant('{app}\\.env.example'), Lines) then
		Exit;

	for I := 0 to GetArrayLength(Lines) - 1 do
	begin
		L := Trim(Lines[I]);
		if (L = '') or (Copy(L, 1, 1) = '#') or (Copy(L, 1, 1) = ';') then
			Continue;
		P := Pos('=', L);
		if P <= 0 then
			Continue;
		K := Trim(Copy(L, 1, P - 1));
		V := Trim(Copy(L, P + 1, MaxInt));
		if CompareText(K, Key) = 0 then
		begin
			Result := V;
			Exit;
		end;
	end;
end;

procedure WriteEnvFile;
var
	EnvPath, BackupPath: string;
	Lines: TArrayOfString;
begin
	EnvPath := ExpandConstant('{app}\\.env');
	BackupPath := EnvPath + '.bak';

	if FileExists(BackupPath) then
		DeleteFile(BackupPath);
	if FileExists(EnvPath) then
		RenameFile(EnvPath, BackupPath);

	SetArrayLength(Lines, 0);

	if IsMySqlSelected then
	begin
		AddLine(Lines, 'DB_ENGINE=mysql');
		AddLine(Lines, 'SQLITE_DB_PATH=');
		AddLine(Lines, 'DB_HOST=' + Trim(MySqlPage.Values[0]));
		AddLine(Lines, 'DB_PORT=' + Trim(MySqlPage.Values[1]));
		AddLine(Lines, 'DB_USER=' + Trim(MySqlPage.Values[2]));
		AddLine(Lines, 'DB_PASSWORD=' + Trim(MySqlPage.Values[3]));
		AddLine(Lines, 'DB_NAME=' + Trim(MySqlPage.Values[4]));
	end
	else
	begin
		AddLine(Lines, 'DB_ENGINE=sqlite');
		AddLine(Lines, 'SQLITE_DB_PATH=');
		AddLine(Lines, 'DB_HOST=127.0.0.1');
		AddLine(Lines, 'DB_PORT=3306');
		AddLine(Lines, 'DB_USER=root');
		AddLine(Lines, 'DB_PASSWORD=');
		AddLine(Lines, 'DB_NAME=gestion_magasin');
	end;

	AddLine(Lines, 'APP_TITLE=' + ReadEnvExampleValue('APP_TITLE', 'Gestion Magasin POS'));
	AddLine(Lines, 'APP_VERSION=' + ReadEnvExampleValue('APP_VERSION', '{#MyAppVersion}'));
	AddLine(Lines, 'APP_UPDATE_URL=' + ReadEnvExampleValue('APP_UPDATE_URL', ''));

	SaveStringsToFile(EnvPath, Lines, False);
end;

procedure TryInstallMySqlViaWinget;
var
	ResultCode: Integer;
begin
	if not IsMySqlAutoInstallSelected then
		Exit;

	if (not Exec(ExpandConstant('{cmd}'), '/C winget --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
	begin
		MsgBox('winget non detecte. Installez MySQL manuellement puis relancez l''application.', mbInformation, MB_OK);
		Exit;
	end;

	if (not Exec(ExpandConstant('{cmd}'), '/C winget install --id Oracle.MySQL --exact --accept-package-agreements --accept-source-agreements', '', SW_SHOW, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
	begin
		MsgBox('L''installation automatique de MySQL n''a pas abouti. Installez MySQL manuellement, puis lancez l''application.', mbInformation, MB_OK);
		Exit;
	end;

	MsgBox('MySQL semble installe. Au premier lancement, l''application initialisera automatiquement le schema si la connexion MySQL est valide.', mbInformation, MB_OK);
end;

procedure InitializeWizard;
begin
	MySqlPage := CreateInputQueryPage(
		wpSelectTasks,
		'Configuration MySQL',
		'Parametres de connexion MySQL',
		'Renseignez les parametres de votre serveur MySQL. Si vous laissez la valeur par defaut, l''application utilisera localhost:3306.'
	);
	MySqlPage.Add('Hote MySQL:', False);
	MySqlPage.Add('Port MySQL:', False);
	MySqlPage.Add('Utilisateur:', False);
	MySqlPage.Add('Mot de passe:', True);
	MySqlPage.Add('Base de donnees:', False);

	MySqlPage.Values[0] := '127.0.0.1';
	MySqlPage.Values[1] := '3306';
	MySqlPage.Values[2] := 'root';
	MySqlPage.Values[3] := '';
	MySqlPage.Values[4] := 'gestion_magasin';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
	Result := False;
	if (PageID = MySqlPage.ID) and (not IsMySqlSelected) then
		Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
	Result := True;
	if CurPageID = MySqlPage.ID then
	begin
		if Trim(MySqlPage.Values[0]) = '' then
		begin
			MsgBox('Le champ Hote MySQL est obligatoire.', mbError, MB_OK);
			Result := False;
			Exit;
		end;
		if Trim(MySqlPage.Values[1]) = '' then
		begin
			MsgBox('Le champ Port MySQL est obligatoire.', mbError, MB_OK);
			Result := False;
			Exit;
		end;
		if Trim(MySqlPage.Values[2]) = '' then
		begin
			MsgBox('Le champ Utilisateur est obligatoire.', mbError, MB_OK);
			Result := False;
			Exit;
		end;
		if Trim(MySqlPage.Values[4]) = '' then
		begin
			MsgBox('Le champ Base de donnees est obligatoire.', mbError, MB_OK);
			Result := False;
			Exit;
		end;
	end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
	if CurStep = ssPostInstall then
	begin
		WriteEnvFile();
		if IsMySqlSelected then
		begin
			TryInstallMySqlViaWinget();
			MsgBox('Mode MySQL active. Assurez-vous que le serveur est demarre et accessible avec les identifiants saisis.', mbInformation, MB_OK);
		end
		else
		begin
			MsgBox('Mode SQLite active. L''application est prete sans installation de serveur MySQL.', mbInformation, MB_OK);
		end;
	end;
end;
