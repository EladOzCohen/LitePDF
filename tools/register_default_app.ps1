# Registers LitePDF.exe for .pdf for the CURRENT USER only (HKCU, no admin needed).
# Adds it to "Open with" and to Settings > Default apps. Windows does not allow a program to make
# itself the default silently, so the final pick is done once by the user in Settings.
# Undo: powershell -File tools\unregister_default_app.ps1
# If you move the dist\LitePDF folder, run this script again.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "dist\LitePDF\LitePDF.exe"
if (-not (Test-Path $exe)) { throw "Build the exe first (tools\build_exe.ps1): $exe not found" }
$cmd = "`"$exe`" `"%1`""
$cls = "HKCU:\Software\Classes"

function Set-Default($path, $value) {
    New-Item -Path $path -Force | Out-Null
    Set-ItemProperty -Path $path -Name "(default)" -Value $value
}

# ProgID
Set-Default "$cls\LitePDF.Document" "PDF document (LitePDF)"
Set-Default "$cls\LitePDF.Document\DefaultIcon" "`"$exe`",0"
Set-Default "$cls\LitePDF.Document\shell\open\command" $cmd

# ProgID friendly name
Set-ItemProperty -Path "$cls\LitePDF.Document" -Name "FriendlyTypeName" -Value "PDF document (LitePDF)"

# App Paths (lets Windows locate the app by name)
Set-Default "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\LitePDF.exe" $exe

# "Open with" entry
Set-Default "$cls\Applications\LitePDF.exe\shell\open\command" $cmd
Set-ItemProperty -Path "$cls\Applications\LitePDF.exe" -Name "FriendlyAppName" -Value "LitePDF"
Set-Default "$cls\Applications\LitePDF.exe\DefaultIcon" "`"$exe`",0"
New-Item -Path "$cls\Applications\LitePDF.exe\SupportedTypes" -Force | Out-Null
Set-ItemProperty -Path "$cls\Applications\LitePDF.exe\SupportedTypes" -Name ".pdf" -Value ""
New-Item -Path "$cls\.pdf\OpenWithProgids" -Force | Out-Null
Set-ItemProperty -Path "$cls\.pdf\OpenWithProgids" -Name "LitePDF.Document" -Value ""

# Default apps capabilities
$cap = "HKCU:\Software\LitePDF\Capabilities"
New-Item -Path $cap -Force | Out-Null
Set-ItemProperty -Path $cap -Name "ApplicationName" -Value "LitePDF"
Set-ItemProperty -Path $cap -Name "ApplicationDescription" -Value "Light PDF reader with Hebrew notes, highlighting, signing and printing"
New-Item -Path "$cap\FileAssociations" -Force | Out-Null
Set-ItemProperty -Path "$cap\FileAssociations" -Name ".pdf" -Value "LitePDF.Document"
New-Item -Path "HKCU:\Software\RegisteredApplications" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\RegisteredApplications" -Name "LitePDF" -Value "Software\LitePDF\Capabilities"

# tell Explorer associations changed
Add-Type -Namespace Win32 -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
[Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Host "Registered LitePDF for the current user: $exe"
