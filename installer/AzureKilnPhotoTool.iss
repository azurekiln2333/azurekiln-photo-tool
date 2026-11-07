; Inno Setup 6 script for AzureKiln Photo Tool.
;
; Build (paths relative to this script's directory unless absolute):
;   iscc /DAppVersion=1.1.0 /DSourceExe=..\dist\AzureKilnPhotoTool.exe ^
;        /DOutputDir=..\release /DOutputBaseFilename=AzureKilnPhotoTool-1.1.0-20261108-windows-x64-setup ^
;        installer\AzureKilnPhotoTool.iss
;
; The installer asks whether to install for the current user only (no admin,
; %LOCALAPPDATA%\Programs) or for all users (UAC, Program Files).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceExe
  #define SourceExe "..\dist\AzureKilnPhotoTool.exe"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "AzureKilnPhotoTool-" + AppVersion + "-windows-x64-setup"
#endif

#define AppName "AzureKiln Photo Tool"
#define AppExeName "AzureKilnPhotoTool.exe"
#define AppPublisher "azurekiln2333"
#define AppURL "https://github.com/azurekiln2333/azurekiln-photo-tool"

[Setup]
; AppId must never change: it lets new versions upgrade the existing installation.
AppId={{4849BC27-0601-4CFA-A871-4F6ACFDFF1F7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\AzureKilnPhotoTool
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; ChineseSimplified.isl ships with newer Inno Setup releases only; include it when present
; so that compilation never fails on an older installation.
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
