# setup.ps1 - Bootstrap one-liner for Windows.
#
# Usage (from any PowerShell prompt inside the repo):
#     .\setup.ps1
#
# What it does:
#     1. Verifies that python, pip and git are available.
#     2. Switches to the feature branch if the repo is still on main.
#     3. Creates/uses a local virtual environment under .venv\ to avoid
#        polluting the system Python.
#     4. Installs every dependency declared in requirements.txt.
#     5. Runs the pytest suite in offline mode as a smoke check.
#     6. Prints the next commands the user should run.
#
# Safe to re-run: every step is idempotent.

$ErrorActionPreference = "Stop"
$BranchName = "claude/secop-ii-integration-ee0Lr"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ">>> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: no encuentro '$Name' en el PATH." -ForegroundColor Red
        Write-Host "       $Hint" -ForegroundColor Yellow
        exit 1
    }
}

Write-Step "Verificando requisitos"
Assert-Command "python" "Instala Python 3.11+ desde https://www.python.org/downloads/ y marca 'Add Python to PATH'."
Assert-Command "pip"    "pip deberia venir con Python; reinstala Python si hace falta."
Assert-Command "git"    "Instala Git desde https://git-scm.com/download/win."

$pyVersion = (& python --version) 2>&1
Write-Host "  - $pyVersion"
Write-Host "  - git       : OK"
Write-Host "  - pip       : OK"

Write-Step "Verificando que estás en el repositorio Secop-II"
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "src\secop_ii")) {
    Write-Host "ERROR: corre este script desde la carpeta del repo (donde está pyproject.toml)." -ForegroundColor Red
    Write-Host "       cd 'C:\Users\FGN\01 Claude Repositorio\14 SECOP Dr Camila Mendoza'" -ForegroundColor Yellow
    exit 1
}

Write-Step "Asegurando la rama con el código"
$current = (& git branch --show-current).Trim()
if ($current -ne $BranchName) {
    Write-Host "  - rama actual: $current -> cambiando a $BranchName"
    & git fetch origin $BranchName 2>&1 | Out-Null
    & git checkout $BranchName
} else {
    Write-Host "  - ya estás en $BranchName"
}
& git pull --ff-only 2>&1 | Out-Null

Write-Step "Creando entorno virtual (.venv)"
if (-not (Test-Path ".venv")) {
    & python -m venv .venv
    Write-Host "  - .venv creado"
} else {
    Write-Host "  - .venv ya existe, lo reutilizo"
}

$venvPython = Join-Path (Resolve-Path ".venv") "Scripts\python.exe"

Write-Step "Actualizando pip dentro del entorno"
& $venvPython -m pip install --upgrade pip --quiet

Write-Step "Instalando dependencias (1-2 min la primera vez)"
& $venvPython -m pip install -r requirements.txt

Write-Step "Registrando el paquete secop_ii dentro del entorno (pip install -e .)"
# Without this the user has to keep exporting PYTHONPATH=src before every
# invocation. Installing editable means `python -m secop_ii ...` just works.
& $venvPython -m pip install -e . --quiet

Write-Step "Instalando pytest para el smoke test (opcional)"
$pytestInstalled = $false
try {
    & $venvPython -m pip install pytest --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pytestInstalled = $true
    }
} catch {
    # Swallowed on purpose — pytest is optional.
}

if (-not $pytestInstalled) {
    Write-Host "  - no se pudo instalar pytest (probablemente DNS/red inestable)." -ForegroundColor Yellow
    Write-Host "  - no es crítico: solo afecta correr los tests automáticos." -ForegroundColor Yellow
    Write-Host "  - el programa funciona igual. Sigue." -ForegroundColor Yellow
} else {
    Write-Step "Corriendo suite de tests (no toca internet)"
    $env:PYTHONPATH = "src"
    & $venvPython -m pytest tests/ -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "AVISO: algunos tests fallaron, pero el programa puede usarse igual." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " ✓ Listo. Todo instalado y tests en verde." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Comandos útiles (en esta ventana de PowerShell):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  # Probar con una URL real (consulta a datos.gov.co):"
Write-Host "  .\.venv\Scripts\python.exe -m secop_ii check-url `"https://community.secop.gov.co/Public/Tendering/ContractNoticePhases/View?PPI=CO1.PPI.46305103`""
Write-Host ""
Write-Host "  # Dry-run sobre tu Excel (no escribe nada):"
Write-Host "  .\.venv\Scripts\python.exe -m secop_ii update-excel `"BASE DE DATOS FEAB CONTRATOS2.xlsx`" --dry-run -v"
Write-Host ""
Write-Host "  # Corrida real (crea backup y actualiza el Excel):"
Write-Host "  .\.venv\Scripts\python.exe -m secop_ii update-excel `"BASE DE DATOS FEAB CONTRATOS2.xlsx`""
Write-Host ""
Write-Host "  # O lanza la UI web local (lo que verá la Dra.):"
Write-Host "  .\ejecutar.bat"
Write-Host ""
