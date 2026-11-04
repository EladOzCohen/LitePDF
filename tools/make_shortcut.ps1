# Creates LitePDF.lnk (next to this project's LitePDF.pyw) and assets\litepdf.ico.
# Move / copy the .lnk to the Desktop or pin it to the taskbar / Start menu.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $py)) { throw "pythonw.exe not found at $py" }
$pyConsole = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"

New-Item -ItemType Directory -Force (Join-Path $root "assets") | Out-Null
$ico = Join-Path $root "assets\litepdf.ico"
& $pyConsole -X utf8 (Join-Path $PSScriptRoot "make_icon.py") $ico

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $root "LitePDF.lnk"))
$lnk.TargetPath = $py
$lnk.Arguments = '"' + (Join-Path $root "LitePDF.pyw") + '"'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = $ico
$lnk.Description = "LitePDF - light PDF reader"
$lnk.Save()
Write-Host "Created $root\LitePDF.lnk"
