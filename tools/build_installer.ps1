# Builds installer\Output\LitePDF-Setup-<version>.exe (needs Inno Setup 6: https://jrsoftware.org/isinfo.php).
#   powershell -File tools\build_installer.ps1            # builds the exe first if dist\ is missing
#   powershell -File tools\build_installer.ps1 -Rebuild   # always rebuild the app first
param([switch]$Rebuild)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php and run again." }

if ($Rebuild -or -not (Test-Path (Join-Path $root "dist\LitePDF\LitePDF.exe"))) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_exe.ps1")
}
& $py -X utf8 (Join-Path $PSScriptRoot "make_installer_art.py") (Join-Path $root "installer\art")

# Inno Setup reads Hebrew text correctly only from a UTF-8 file with a BOM
$iss = Join-Path $root "installer\LitePDF.iss"
$bytes = [System.IO.File]::ReadAllBytes($iss)
if (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) {
    [System.IO.File]::WriteAllBytes($iss, [byte[]](0xEF, 0xBB, 0xBF) + $bytes)
}
& $iscc /Qp $iss
$out = Get-ChildItem (Join-Path $root "installer\Output") -Filter "LitePDF-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ("Installer: {0}  ({1:N1} MB)" -f $out.FullName, ($out.Length / 1MB))
