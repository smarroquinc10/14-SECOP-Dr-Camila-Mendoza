<#
.SYNOPSIS
    Update one-liner para el dashboard FEAB (versi�n web).

.DESCRIPTION
    Hace TODO lo necesario para que tu cambio aparezca en la PC de Cami:

      1. `git add -A`     (stagea todos los cambios)
      2. `git commit -m`  (con tu mensaje)
      3. `git push`       (sube a main)
      4. GitHub Actions detecta el push y deploya a GitHub Pages en ~2-3 min
      5. Cami refresca el browser y ve la nueva versi�n

    Reemplaza al `release.ps1` del MSI. La web no necesita versiones —
    siempre es la �ltima que pushe� Sergio.

.PARAMETER Message
    Mensaje del commit. Mant�n breve y �til.

.EXAMPLE
    .\scripts\update.ps1 "agrandado el font de la fecha"
    # Stagea, commitea, pushea. Cami ve el cambio en ~3 min.

.EXAMPLE
    .\update.bat "fix: el modal no abr�a"
    # Igual via el shim de la ra�z.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true, HelpMessage = "Mensaje del commit")]
    [string]$Message
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=== Update Dra Cami Contractual ===" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar branch — solo informativo, no bloqueante.
$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
Write-Host "Branch actual: $branch"

# 2. Ver qu� hay para commitear (sin pasar por pipeline raro de cmd.exe)
$status = & git -C $RepoRoot status --porcelain 2>$null
if (-not $status) {
    Write-Host "No hay cambios. Nada para hacer." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Cambios a commitear:" -ForegroundColor Yellow
$status -split "`n" | ForEach-Object {
    if ($_) { Write-Host "  $_" }
}

Write-Host ""
Write-Host "Commit + push..."

# 3. Stage + commit (todos los archivos, incluso untracked)
& git -C $RepoRoot add -A 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "git add fall�" }

& git -C $RepoRoot commit -m $Message 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "git commit fall�" }

# 4. Push al branch actual + a main (para triggerar deploy-pages)
& git -C $RepoRoot push 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    & git -C $RepoRoot push --set-upstream origin $branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git push fall�" }
}
# Tambi�n pusheamos a main para que Pages deploye (Pages solo deploya
# desde main por default). Si ya estamos en main, este push es no-op.
if ($branch -ne "main") {
    Write-Host "Tambi�n pusheo a main para triggerar Pages deploy..."
    & git -C $RepoRoot push origin "${branch}:main" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  push a main fall� — probablemente conflicto. Hac� git pull origin main + retry." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== LISTO ===" -ForegroundColor Green
Write-Host ""
Write-Host "GitHub Actions est� compilando + deployando. Sigue en:"
Write-Host "  https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza/actions"
Write-Host ""
Write-Host "En ~2-3 minutos Cami ve el cambio refrescando:"
Write-Host "  https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/"
Write-Host ""
