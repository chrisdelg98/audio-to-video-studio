; ============================================================
;  Audio to Video Studio — Inno Setup Installer Script
;  Requires: Inno Setup 6  (https://jrsoftware.org/isinfo.php)
;
;  Compile:
;    iscc installer\AudioToVideoStudio.iss
;  Output:
;    installer\Output\AudioToVideoStudio_Setup_1.0.0.exe
; ============================================================

#define AppName        "Audio to Video Studio"
#define AppExeName     "AudioToVideoStudio.exe"
; AppVersion can be overridden from the command line:
;   iscc /DAppVersion=1.2.0 installer\AudioToVideoStudio.iss
#ifndef AppVersion
  #define AppVersion   "1.0.0"
#endif
#define AppPublisher   "chrisdelg98"
#define AppURL         "https://github.com/chrisdelg98/audio-to-video-studio"
#define SourceExe      "..\dist\AudioToVideoStudio.exe"

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
DefaultDirName={localappdata}\AudioToVideoStudio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; No admin rights needed (per-user install)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Output
OutputDir=Output
OutputBaseFilename=AudioToVideoStudio_Setup_{#AppVersion}
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
AppMutex=AudioToVideoStudioSetupMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: {#SourceExe}; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Desktop (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the config folder created by the app at runtime
Type: filesandordirs; Name: "{app}\config"

; ============================================================
; Code section — FFmpeg check at startup
; ============================================================
[Code]
function FindOnPath(const ExeName: string): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C where ' + ExeName + ' >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

procedure InitializeWizard();
begin
  // Welcome message modification (no-op, placeholder)
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
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
