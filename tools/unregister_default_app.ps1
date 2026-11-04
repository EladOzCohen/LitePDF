# Removes everything register_default_app.ps1 added (current user only).
$cls = "HKCU:\Software\Classes"
Remove-Item "$cls\LitePDF.Document" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$cls\Applications\LitePDF.exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-ItemProperty "$cls\.pdf\OpenWithProgids" -Name "LitePDF.Document" -ErrorAction SilentlyContinue
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\LitePDF.exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "HKCU:\Software\LitePDF" -Recurse -Force -ErrorAction SilentlyContinue
Remove-ItemProperty "HKCU:\Software\RegisteredApplications" -Name "LitePDF" -ErrorAction SilentlyContinue
Write-Host "LitePDF registration removed. (If it was your default PDF app, pick another in Settings > Default apps.)"
