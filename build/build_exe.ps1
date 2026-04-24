# Build the Windows .exe with PyInstaller.
#
# Usage (from a PowerShell prompt at the repo root):
#     pip install -r requirements.txt pyinstaller
#     .\build\build_exe.ps1
#
# Output:
#     dist\CRM SECOP II\CRM SECOP II.exe
#
# Notes:
# * --onedir is required: Streamlit reads static assets from disk, and
#   --onefile extracts them to a temp dir which Streamlit does not always
#   locate correctly.
# * --collect-all streamlit pulls in the runtime package (including the
#   static/ folder and pkg metadata) automatically.
# * --windowed hides the console window so the end user only sees the
#   browser that the launcher opens.

param(
    [string]$AppName = "CRM SECOP II",
    [string]$IconPath = "build\icon.ico"
)

$ErrorActionPreference = "Stop"

$iconArg = @()
if (Test-Path $IconPath) {
    $iconArg = @("--icon", $IconPath)
}

$addDataSep = ";"  # Windows uses ';'; Linux/Mac would use ':'.

pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "$AppName" `
    @iconArg `
    --collect-all streamlit `
    --collect-all altair `
    --collect-all pyarrow `
    --collect-data streamlit `
    --copy-metadata streamlit `
    --add-data "src\secop_ii\ui\streamlit_app.py${addDataSep}secop_ii\ui" `
    --hidden-import secop_ii.ui.streamlit_app `
    --hidden-import secop_ii.orchestrator `
    --hidden-import secop_ii.extractors `
    --hidden-import secop_ii.extractors.modificatorios `
    --paths src `
    src\secop_ii\launcher.py

Write-Host ""
Write-Host "Listo. Ejecutable en: dist\$AppName\$AppName.exe"
Write-Host "Empaqueta toda la carpeta dist\$AppName\ en un ZIP para entregar."
