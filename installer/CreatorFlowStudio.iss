; ============================================================
;  CreatorFlow Studio — Inno Setup Installer Script
;  Requires: Inno Setup 6  (https://jrsoftware.org/isinfo.php)
;
;  Compile:
;    iscc installer\CreatorFlowStudio.iss
;  Output:
;    installer\Output\CreatorFlowStudio_Setup_1.0.0.exe
; ============================================================

#define AppName        "CreatorFlow Studio"
#define AppExeName     "CreatorFlowStudio.exe"
; AppVersion can be overridden from the command line:
;   iscc /DAppVersion=1.2.0 installer\AudioToVideoStudio.iss
#ifndef AppVersion
  #define AppVersion   "1.0.0"
#endif
#define AppPublisher   "chrisdelg98"
#define AppURL         "https://github.com/chrisdelg98/audio-to-video-studio"
#define SourceExe      "..\dist\CreatorFlowStudio.exe"
#define Win7SP1URL     "https://catalog.s.download.windowsupdate.com/msdownload/update/software/svpk/2011/02/windows6.1-kb976932-x64_74865ef2562006e51d7f9333b4a8d45b7a749dab.exe"
#define Win7SHA2URL    "https://catalog.s.download.windowsupdate.com/c/msdownload/update/software/secu/2019/09/windows6.1-kb4474419-v3-x64_b5614c6cea5cb4e198717789633dca16308ef79c.msu"
#define Win7SSUURL     "https://catalog.s.download.windowsupdate.com/c/msdownload/update/software/secu/2019/03/windows6.1-kb4490628-x64_d3de52d6987f7c8bdc2c015dca69eac96047c76e.msu"
#define VCRedistURL    "https://aka.ms/vs/17/release/vc_redist.x64.exe"
#define OllamaURL      "https://ollama.com/download/OllamaSetup.exe"
#define VCRedistX64    "prereqs\vc_redist.x64.exe"
#define VCRedistX86    "prereqs\vc_redist.x86.exe"
#define OllamaSetup    "prereqs\OllamaSetup.exe"

#ifexist "prereqs\vc_redist.x64.exe"
  #define HasBundledVCRedistX64
#endif
#ifexist "prereqs\vc_redist.x86.exe"
  #define HasBundledVCRedistX86
#endif
#ifexist "prereqs\OllamaSetup.exe"
  #define HasBundledOllamaSetup
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Install per-user in LocalAppData so the app can write config/ next to the EXE
DefaultDirName={localappdata}\CreatorFlowStudio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; No admin rights needed (per-user install)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Output
OutputDir=Output
OutputBaseFilename=CreatorFlowStudio_Setup_{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
InternalCompressLevel=ultra64

; Visuals
WizardStyle=modern
WizardSizePercent=110
SetupIconFile=..\logoAtV.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Misc
ShowLanguageDialog=no
; Prevent running multiple instances of the installer
AppMutex=CreatorFlowStudioSetupMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: {#SourceExe}; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion
; Prompt Lab catalog preconfigurado (no sobrescribir instalaciones existentes)
Source: "..\config\prompt_lab.json"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist
; Semilla de catalogo para merge no destructivo en actualizaciones
Source: "..\config\prompt_lab.json"; DestDir: "{app}\config"; DestName: "prompt_lab_seed.json"; Flags: ignoreversion
#ifdef HasBundledVCRedistX64
Source: "{#VCRedistX64}"; DestDir: "{tmp}"; Flags: dontcopy
#endif
#ifdef HasBundledVCRedistX86
Source: "{#VCRedistX86}"; DestDir: "{tmp}"; Flags: dontcopy
#endif
#ifdef HasBundledOllamaSetup
Source: "{#OllamaSetup}"; DestDir: "{tmp}"; Flags: dontcopy
#endif

[Icons]
; Start Menu
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Nota: no eliminamos {app}\config en uninstall para preservar
; configuraciones y presets del usuario entre actualizaciones.

; ============================================================
; Code section — prerequisites + FFmpeg check
; ============================================================
[Code]
var
  ReqPage: TWizardPage;
  ReqMemo: TNewMemo;
  ReqStatus: TNewStaticText;
  ChkAutoPrereqs: TNewCheckBox;
  BtnOpenSP1: TNewButton;
  BtnOpenSHA2: TNewButton;
  BtnOpenVCRedist: TNewButton;
  BtnOpenOllama: TNewButton;
  BtnCopyPS: TNewButton;
  InstallNeedsRestart: Boolean;

function FindOnPath(const ExeName: string): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C where ' + ExeName + ' >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

function IsWindows7: Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  Result := (V.Major = 6) and (V.Minor = 1);
end;

function IsWindows7SP1OrLater: Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  Result := not ((V.Major = 6) and (V.Minor = 1) and (V.ServicePackMajor < 1));
end;

function IsVCRedistInstalled: Boolean;
var
  Installed: Cardinal;
begin
  Result := False;

  if IsWin64 then
  begin
    if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
      if Installed = 1 then
      begin
        Result := True;
        exit;
      end;
  end;

  if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86', 'Installed', Installed) then
    Result := (Installed = 1);
end;

function IsOllamaSupportedOS: Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  Result := (V.Major >= 10);
end;

function IsOllamaInstalled: Boolean;
begin
  Result :=
    FindOnPath('ollama') or
    FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama app.exe')) or
    FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) or
    FileExists(ExpandConstant('{pf}\Ollama\ollama app.exe')) or
    FileExists(ExpandConstant('{pf}\Ollama\ollama.exe'));
end;

function ExecAndWait(const FileName, Params: string): Integer;
var
  ResultCode: Integer;
begin
  if Exec(FileName, Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode
  else
    Result := -1;
end;

procedure OpenURL(const URL: string);
var
  ResultCode: Integer;
begin
  ShellExec('open', URL, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;

procedure CopyTextToClipboardViaClip(const S: string);
var
  TempFile: string;
  ResultCode: Integer;
begin
  TempFile := ExpandConstant('{tmp}\creatorflow_prereq_cmd.txt');
  SaveStringToFile(TempFile, S, False);
  Exec(ExpandConstant('{cmd}'), '/C type "' + TempFile + '" | clip', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function GetVCRedistPowerShellCommand: string;
begin
  Result :=
    '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12' + #13#10 +
    '$d = "$env:USERPROFILE\Downloads"' + #13#10 +
    'Invoke-WebRequest "{#VCRedistURL}" -OutFile "$d\vc_redist.x64.exe"' + #13#10 +
    'Start-Process "$d\vc_redist.x64.exe" -ArgumentList "/quiet /norestart" -Wait';
end;

procedure UpdateReqStatusText;
var
  StatusText: string;
begin
  StatusText := '';

  if IsWindows7 then
  begin
    if IsWindows7SP1OrLater then
      StatusText := StatusText + 'Windows 7 SP1: OK' + #13#10
    else
      StatusText := StatusText + 'Windows 7 SP1: FALTA (requerido)' + #13#10;
  end
  else
    StatusText := StatusText + 'Sistema operativo: OK' + #13#10;

  if IsVCRedistInstalled then
    StatusText := StatusText + 'Visual C++ Runtime: OK'
  else
    StatusText := StatusText + 'Visual C++ Runtime: Falta (recomendado instalar)';

  StatusText := StatusText + #13#10;
  if not IsOllamaSupportedOS then
    StatusText := StatusText + 'Ollama (Prompt Lab IA): No compatible en este sistema'
  else if IsOllamaInstalled then
    StatusText := StatusText + 'Ollama (Prompt Lab IA): OK'
  else
    StatusText := StatusText + 'Ollama (Prompt Lab IA): Falta (opcional, recomendado)';

  ReqStatus.Caption := StatusText;
end;

procedure BtnOpenSP1Click(Sender: TObject);
begin
  OpenURL('{#Win7SP1URL}');
end;

procedure BtnOpenSHA2Click(Sender: TObject);
begin
  OpenURL('{#Win7SHA2URL}');
end;

procedure BtnOpenVCRedistClick(Sender: TObject);
begin
  OpenURL('{#VCRedistURL}');
end;

procedure BtnOpenOllamaClick(Sender: TObject);
begin
  OpenURL('{#OllamaURL}');
end;

procedure BtnCopyPSClick(Sender: TObject);
begin
  CopyTextToClipboardViaClip(GetVCRedistPowerShellCommand());
  MsgBox('Comando PowerShell copiado al portapapeles.', mbInformation, MB_OK);
end;

function TryInstallBundledVCRedist(var ErrorText: string): Boolean;
#if defined(HasBundledVCRedistX64) || defined(HasBundledVCRedistX86)
var
  Code: Integer;
#endif
begin
  Result := True;
  ErrorText := '';

  if IsVCRedistInstalled then
    exit;

  if not ChkAutoPrereqs.Checked then
  begin
    ErrorText :=
      'Falta Visual C++ Runtime.' + #13#10 + #13#10 +
      'Activa la opcion de instalacion automatica en la pagina de prerequisitos o instalo manualmente desde:' + #13#10 +
      '{#VCRedistURL}';
    Result := False;
    exit;
  end;

  if IsWin64 then
  begin
    #ifdef HasBundledVCRedistX64
      ExtractTemporaryFile('vc_redist.x64.exe');
      Code := ExecAndWait(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/quiet /norestart');
      if (Code = 3010) then
        InstallNeedsRestart := True;
      if not ((Code = 0) or (Code = 1638) or (Code = 3010)) then
      begin
        ErrorText :=
          'No se pudo instalar Visual C++ Runtime x64 automaticamente (codigo: ' + IntToStr(Code) + ').' + #13#10 + #13#10 +
          'Descargalo manualmente desde:' + #13#10 +
          '{#VCRedistURL}';
        Result := False;
        exit;
      end;
    #else
      ErrorText :=
        'Este instalador no incluye vc_redist.x64.exe en installer\prereqs.' + #13#10 + #13#10 +
        'Descargalo manualmente desde:' + #13#10 +
        '{#VCRedistURL}';
      Result := False;
      exit;
    #endif
  end
  else
  begin
    #ifdef HasBundledVCRedistX86
      ExtractTemporaryFile('vc_redist.x86.exe');
      Code := ExecAndWait(ExpandConstant('{tmp}\vc_redist.x86.exe'), '/quiet /norestart');
      if (Code = 3010) then
        InstallNeedsRestart := True;
      if not ((Code = 0) or (Code = 1638) or (Code = 3010)) then
      begin
        ErrorText :=
          'No se pudo instalar Visual C++ Runtime x86 automaticamente (codigo: ' + IntToStr(Code) + ').' + #13#10 + #13#10 +
          'Descargalo manualmente desde:' + #13#10 +
          'https://aka.ms/vs/17/release/vc_redist.x86.exe';
        Result := False;
        exit;
      end;
    #else
      ErrorText :=
        'Este instalador no incluye vc_redist.x86.exe en installer\prereqs.' + #13#10 + #13#10 +
        'Descargalo manualmente desde:' + #13#10 +
        'https://aka.ms/vs/17/release/vc_redist.x86.exe';
      Result := False;
      exit;
    #endif
  end;
end;

function TryInstallBundledOllama(var ErrorText: string): Boolean;
#ifdef HasBundledOllamaSetup
var
  Code: Integer;
#endif
begin
  Result := True;
  ErrorText := '';

  if not IsOllamaSupportedOS then
    exit;

  if IsOllamaInstalled then
    exit;

  if not ChkAutoPrereqs.Checked then
    exit;

  #ifdef HasBundledOllamaSetup
    ExtractTemporaryFile('OllamaSetup.exe');
    Code := ExecAndWait(ExpandConstant('{tmp}\OllamaSetup.exe'), '/VERYSILENT /NORESTART');
    if (Code = 3010) then
      InstallNeedsRestart := True;
    if not ((Code = 0) or (Code = 1638) or (Code = 3010)) then
    begin
      ErrorText :=
        'No se pudo instalar Ollama automaticamente (codigo: ' + IntToStr(Code) + ').' + #13#10 + #13#10 +
        'Descargalo manualmente desde:' + #13#10 +
        '{#OllamaURL}';
      Result := False;
      exit;
    end;
  #else
    ErrorText :=
      'Este instalador no incluye OllamaSetup.exe en installer\prereqs.' + #13#10 + #13#10 +
      'Descargalo manualmente desde:' + #13#10 +
      '{#OllamaURL}';
    Result := False;
    exit;
  #endif
end;

procedure InitializeWizard();
var
  MemoMinH: Integer;
  BtnTop: Integer;
  BtnH: Integer;
begin
  InstallNeedsRestart := False;

  ReqPage := CreateCustomPage(
    wpWelcome,
    'Prerequisitos del sistema',
    'El instalador puede preparar dependencias automaticamente y te indicara cada paso.'
  );

  ReqMemo := TNewMemo.Create(ReqPage);
  ReqMemo.Parent := ReqPage.Surface;
  ReqMemo.Left := 0;
  ReqMemo.Top := 0;
  ReqMemo.Width := ReqPage.SurfaceWidth;
  MemoMinH := ScaleY(92);
  ReqMemo.Height := ReqPage.SurfaceHeight - ScaleY(220);
  if ReqMemo.Height < MemoMinH then
    ReqMemo.Height := MemoMinH;
  ReqMemo.ReadOnly := True;
  ReqMemo.WantReturns := True;
  ReqMemo.ScrollBars := ssVertical;
  ReqMemo.Text :=
    'Este instalador verifica compatibilidad y te ayuda con dependencias.' + #13#10 +
    '1) En Windows 7: SP1 es obligatorio.' + #13#10 +
    '2) SHA-2/SSU pueden ser necesarios en Windows 7 para instaladores modernos.' + #13#10 +
    '3) Visual C++ Runtime se instalara automaticamente (si viene incluido).' + #13#10 +
    '4) Ollama es opcional (Prompt Lab IA) y tambien puede instalarse automaticamente.' + #13#10 + #13#10 +
    'Si algo no se puede automatizar, veras enlaces y el comando listo para copiar.';

  ReqStatus := TNewStaticText.Create(ReqPage);
  ReqStatus.Parent := ReqPage.Surface;
  ReqStatus.Left := 0;
  ReqStatus.Top := ReqMemo.Top + ReqMemo.Height + 8;
  ReqStatus.Width := ReqPage.SurfaceWidth;
  ReqStatus.Height := ScaleY(56);
  ReqStatus.AutoSize := False;

  ChkAutoPrereqs := TNewCheckBox.Create(ReqPage);
  ChkAutoPrereqs.Parent := ReqPage.Surface;
  ChkAutoPrereqs.Left := 0;
  ChkAutoPrereqs.Top := ReqStatus.Top + ReqStatus.Height + ScaleY(4);
  ChkAutoPrereqs.Width := ReqPage.SurfaceWidth;
  ChkAutoPrereqs.Checked := True;
  ChkAutoPrereqs.Caption := 'Instalar prerequisitos automaticamente (recomendado)';

  BtnH := ScaleY(24);
  BtnTop := ChkAutoPrereqs.Top + ScaleY(26);

  BtnOpenSP1 := TNewButton.Create(ReqPage);
  BtnOpenSP1.Parent := ReqPage.Surface;
  BtnOpenSP1.Left := 0;
  BtnOpenSP1.Top := BtnTop;
  BtnOpenSP1.Width := 140;
  BtnOpenSP1.Height := BtnH;
  BtnOpenSP1.Caption := 'Abrir SP1';
  BtnOpenSP1.OnClick := @BtnOpenSP1Click;

  BtnOpenSHA2 := TNewButton.Create(ReqPage);
  BtnOpenSHA2.Parent := ReqPage.Surface;
  BtnOpenSHA2.Left := BtnOpenSP1.Left + BtnOpenSP1.Width + 8;
  BtnOpenSHA2.Top := BtnOpenSP1.Top;
  BtnOpenSHA2.Width := 140;
  BtnOpenSHA2.Height := BtnH;
  BtnOpenSHA2.Caption := 'Abrir SHA-2';
  BtnOpenSHA2.OnClick := @BtnOpenSHA2Click;

  BtnOpenVCRedist := TNewButton.Create(ReqPage);
  BtnOpenVCRedist.Parent := ReqPage.Surface;
  BtnOpenVCRedist.Left := BtnOpenSHA2.Left + BtnOpenSHA2.Width + 8;
  BtnOpenVCRedist.Top := BtnOpenSP1.Top;
  BtnOpenVCRedist.Width := 160;
  BtnOpenVCRedist.Height := BtnH;
  BtnOpenVCRedist.Caption := 'Abrir VC++ Runtime';
  BtnOpenVCRedist.OnClick := @BtnOpenVCRedistClick;

  BtnCopyPS := TNewButton.Create(ReqPage);
  BtnCopyPS.Parent := ReqPage.Surface;
  BtnCopyPS.Left := 0;
  BtnCopyPS.Top := BtnOpenSP1.Top + BtnH + ScaleY(8);
  BtnCopyPS.Width := 220;
  BtnCopyPS.Height := BtnH;
  BtnCopyPS.Caption := 'Copiar comando PowerShell';
  BtnCopyPS.OnClick := @BtnCopyPSClick;

  BtnOpenOllama := TNewButton.Create(ReqPage);
  BtnOpenOllama.Parent := ReqPage.Surface;
  BtnOpenOllama.Left := BtnCopyPS.Left + BtnCopyPS.Width + 8;
  BtnOpenOllama.Top := BtnCopyPS.Top;
  BtnOpenOllama.Width := 180;
  BtnOpenOllama.Height := BtnH;
  BtnOpenOllama.Caption := 'Abrir Ollama';
  BtnOpenOllama.OnClick := @BtnOpenOllamaClick;
  BtnOpenOllama.Enabled := IsOllamaSupportedOS;

  if (BtnCopyPS.Top + BtnCopyPS.Height) > ReqPage.SurfaceHeight then
    BtnCopyPS.Top := ReqPage.SurfaceHeight - BtnCopyPS.Height - ScaleY(2);

  if (BtnOpenOllama.Top + BtnOpenOllama.Height) > ReqPage.SurfaceHeight then
    BtnOpenOllama.Top := ReqPage.SurfaceHeight - BtnOpenOllama.Height - ScaleY(2);

  UpdateReqStatusText;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = ReqPage.ID then
  begin
    UpdateReqStatusText;

    if IsWindows7 and (not IsWindows7SP1OrLater) then
    begin
      MsgBox(
        'Windows 7 sin SP1 detectado.' + #13#10 + #13#10 +
        'Debes instalar SP1 (KB976932) para continuar.',
        mbCriticalError,
        MB_OK
      );
      OpenURL('{#Win7SP1URL}');
      Result := False;
      exit;
    end;
  end;

  // Warn about FFmpeg only once, on the ready-to-install page
  if CurPageID = wpReady then begin
    if not FindOnPath('ffmpeg') then begin
      if MsgBox(
        'FFmpeg was not found in your system PATH.' + #13#10 + #13#10 +
        'Audio to Video Studio requires FFmpeg to generate videos.' + #13#10 +
        'You can install it from: https://ffmpeg.org/download.html' + #13#10 + #13#10 +
        'Continue installing anyway?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
var
  Err: string;
begin
  Result := '';

  if IsWindows7 and (not IsWindows7SP1OrLater) then
  begin
    Result :=
      'Windows 7 sin SP1 detectado.' + #13#10 +
      'Instala KB976932 y vuelve a ejecutar el instalador.';
    exit;
  end;

  if not TryInstallBundledVCRedist(Err) then
  begin
    Result := Err;
    exit;
  end;

  if not TryInstallBundledOllama(Err) then
  begin
    Log('Ollama prerequisite warning: ' + Err);
    MsgBox(
      'No se pudo instalar Ollama automaticamente.' + #13#10 + #13#10 +
      'La app se instalara igual, pero Prompt Lab IA necesitara Ollama activo.' + #13#10 +
      'Puedes instalarlo despues desde:' + #13#10 +
      '{#OllamaURL}',
      mbInformation,
      MB_OK
    );
  end;

  NeedsRestart := InstallNeedsRestart;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = ReqPage.ID then
    UpdateReqStatusText;
end;
