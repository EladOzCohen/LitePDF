; LitePDF installer - Inno Setup 6 script.  Build with:  powershell -File tools\build_installer.ps1
;
; What the user gets: a normal Setup wizard (Hebrew or English, by Windows language). One click on Install:
;   - per-user install, no administrator prompt, in %LOCALAPPDATA%\Programs\LitePDF
;   - Start-menu entry, optional desktop shortcut, entry in "Apps > Installed apps" with a real uninstaller
;   - optional: LitePDF appears in "Open with" / Default apps for .pdf files
; Everything the program needs (Python runtime, Qt, PyMuPDF, the C runtime) is already inside the app folder,
; so nothing else has to be installed on the target PC. Setup only checks for 64-bit Windows 10 (1809) or later.

#ifndef AppName
  #define AppName "LitePDF"
#endif
#ifndef AppExe
  #define AppExe "LitePDF.exe"
#endif
#ifndef ProgId
  #define ProgId "LitePDF.Document"
#endif
#ifndef CapKey
  #define CapKey "Software\LitePDF\Capabilities"
#endif
#ifndef RegAppName
  #define RegAppName "LitePDF"
#endif
#ifndef AppId
  #define AppId "{{B7C2D6F4-3A1E-4C59-9E0B-6D2F8A41C7E3}"   ; the doubled { is Inno's escape for a literal {
#endif
#define AppVersion "1.0.0"
#define SrcDir "..\dist\LitePDF"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LitePDF
AppPublisherURL=https://github.com/EladOzCohen/LitePDF
AppSupportURL=https://github.com/EladOzCohen/LitePDF
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=..\assets\litepdf.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=art\wizard-164.bmp,art\wizard-328.bmp
WizardSmallImageFile=art\small-55.bmp,art\small-110.bmp
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany=LitePDF
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[CustomMessages]
english.TaskGroupPdf=PDF files:
english.TaskOpenWith=Add {#AppName} to the "Open with" list for PDF files
english.TaskDefaultApps=Open Windows settings so I can make {#AppName} my default PDF reader
english.UninstallKeepData=Also delete your {#AppName} settings and saved signatures?
hebrew.TaskGroupPdf=קובצי PDF:
hebrew.TaskOpenWith=הוסף את {#AppName} לרשימת "פתח באמצעות" של קובצי PDF
hebrew.TaskDefaultApps=פתח את הגדרות Windows כדי שאוכל להגדיר את {#AppName} כקורא ה-PDF ברירת המחדל
hebrew.UninstallKeepData=למחוק גם את ההגדרות והחתימות השמורות של {#AppName}?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "openwith"; Description: "{cm:TaskOpenWith}"; GroupDescription: "{cm:TaskGroupPdf}"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Excludes: "LitePDF.exe"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcDir}\LitePDF.exe"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; ---- "Open with" / Default apps registration (per user). Windows itself keeps the final choice of the default
; ---- program for .pdf with the user, so we register and then offer to open the Default apps page.
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "PDF document ({#AppName})"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "PDF document ({#AppName})"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "{#CapKey}"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Light PDF reader with Hebrew notes, highlighting, signing and printing"; Tasks: openwith
Root: HKA; Subkey: "{#CapKey}\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgId}"; Tasks: openwith
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#RegAppName}"; ValueData: "{#CapKey}"; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "ms-settings:defaultapps"; Description: "{cm:TaskDefaultApps}"; Flags: shellexec nowait postinstall skipifsilent unchecked; Tasks: openwith

[Code]
// On uninstall: the program is removed completely; the user's own data (settings, saved signatures) is kept
// unless they say otherwise.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UninstallSilent then
      if MsgBox(CustomMessage('UninstallKeepData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(ExpandConstant('{userappdata}\LitePDF'), True, True, True);
        RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\LitePDF\LitePDF');
      end;
  end;
end;
