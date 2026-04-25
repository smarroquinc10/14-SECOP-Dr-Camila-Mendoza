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

# 1. Verificar que estamos en main (o que el branch va a triggerar el workflow)
$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Branch actual: $branch"
if ($branch -ne "main") {
    $resp = Read-Host "No est�s en 'main'. �Push a main desde este branch igual? (s/N)"
    if ($resp -ne "s" -and $resp -ne "S") {
        Write-Host "Abortando." -ForegroundColor Red
        exit 1
    }
}

# 2. Ver qu� hay para commitear
$status = & git -C $RepoRoot status --porcelain
if (-not $status) {
    Write-Host "No hay cambios. Nada para hacer." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Cambios a commitear:" -ForegroundColor Yellow
& git -C $RepoRoot status --short

Write-Host ""
Write-Host "Commit + push..."

# 3. Stage + commit
& git -C $RepoRoot add -A
if ($LASTEXITCODE -ne 0) { throw "git add fall�" }

& git -C $RepoRoot commit -m $Message
if ($LASTEXITCODE -ne 0) { throw "git commit fall�" }

# 4. Push (al branch actual; si no es main, igual el workflow Pages
#    triggerea para `claude/**` por la config en deploy-pages.yml)
& git -C $RepoRoot push
if ($LASTEXITCODE -ne 0) {
    # Si fall�, intent� con upstream
    & git -C $RepoRoot push --set-upstream origin $branch
    if ($LASTEXITCODE -ne 0) { throw "git push fall�" }
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
