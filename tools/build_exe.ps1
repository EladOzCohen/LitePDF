# Builds dist\LitePDF\LitePDF.exe (onedir = fast startup, no console window).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
Set-Location $root
& $py -X utf8 tools\make_icon.py assets\litepdf.ico
& $py -m PyInstaller --noconfirm --clean --windowed --name LitePDF `
    --icon assets\litepdf.ico `
    --version-file tools\version_info.txt `
    --paths src `
    --exclude-module tkinter --exclude-module numpy --exclude-module PIL `
    --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtOpenGL --exclude-module PySide6.QtPdf --exclude-module PySide6.QtWebEngineCore `
    --add-data "assets\litepdf.ico;assets" `
    src\main.py
Write-Host "Done: $root\dist\LitePDF\LitePDF.exe"

# Trim big files a widgets-only app never loads (software OpenGL, QML/Quick, Qt PDF).
$pyside = Join-Path $root "dist\LitePDF\_internal\PySide6"
foreach ($pat in "opengl32sw.dll", "Qt6Quick*.dll", "Qt6Qml*.dll", "Qt6Pdf*.dll", "Qt6VirtualKeyboard*.dll") {
    Get-ChildItem $pyside -Filter $pat -ErrorAction SilentlyContinue | Remove-Item -Force
}
$size = (Get-ChildItem (Join-Path $root "dist\LitePDF") -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Final size: {0:N0} MB" -f $size)
