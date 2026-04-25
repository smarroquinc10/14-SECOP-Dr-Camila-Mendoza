<#
.SYNOPSIS
    Refresca los seeds del dashboard con la data m�s nueva del cache local.

.DESCRIPTION
    Cuando vos corr�s el portal scraper (Playwright + captcha) en el dev
    install, se actualiza `.cache/portal_opportunity.json`. Este script:

      1. Copia ese archivo + el watched_urls.json + el secop_integrado.json
         desde `.cache/` (dev) hacia `app/public/data/` (donde GitHub Pages
         los sirve como assets est�ticos).
      2. Reporta cu�ntas entries gan� o perdi� cada seed vs la versi�n
         vieja.
      3. NO commitea nada — vos despu�s usas `update.bat "msg"` para subir.

    Este script reemplaza el flujo manual de copy-paste.

.EXAMPLE
    .\scripts\refresh-seeds.ps1
    # Re-bakea los 3 seeds desde .cache. Despu�s update.bat "..." para deploy.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$Sources = @(
    @{
        Name = "Watch list (491 URLs de la Dra)"
        From = "$RepoRoot\.cache\watched_urls.json"
        To   = "$RepoRoot\app\public\data\watched_urls.json"
    },
    @{
        Name = "SECOP Integrado snapshot (rpmr-utcd)"
        From = "$RepoRoot\.cache\secop_integrado.json"
        To   = "$RepoRoot\app\public\data\secop_integrado_seed.json"
    },
    @{
        Name = "Portal cache (community.secop, scraped con Playwright)"
        From = "$RepoRoot\.cache\portal_opportunity.json"
        To   = "$RepoRoot\app\public\data\portal_opportunity_seed.json"
    }
)

Write-Host ""
Write-Host "=== Refrescar seeds del dashboard FEAB ===" -ForegroundColor Cyan
Write-Host ""

$delta = @()

foreach ($s in $Sources) {
    Write-Host "→ $($s.Name)"

    if (-not (Test-Path $s.From)) {
        Write-Host "    SKIP: $($s.From) no existe (no corriste el scraper / sync correspondiente)" -ForegroundColor Yellow
        continue
    }

    $oldEntries = 0
    $newEntries = 0

    if (Test-Path $s.To) {
        try {
            $old = Get-Content $s.To -Raw | ConvertFrom-Json
            if ($old -is [System.Collections.IEnumerable] -and -not ($old -is [string])) {
                $oldEntries = $old.Count
            } elseif ($old.PSObject.Properties.Name -contains "by_notice_uid") {
                $oldEntries = ($old.by_notice_uid.PSObject.Properties).Count
            } else {
                $oldEntries = ($old.PSObject.Properties).Count
            }
        } catch {}
    }

    Copy-Item -Path $s.From -Destination $s.To -Force

    try {
        $new = Get-Content $s.To -Raw | ConvertFrom-Json
        if ($new -is [System.Collections.IEnumerable] -and -not ($new -is [string])) {
            $newEntries = $new.Count
        } elseif ($new.PSObject.Properties.Name -contains "by_notice_uid") {
            $newEntries = ($new.by_notice_uid.PSObject.Properties).Count
        } else {
            $newEntries = ($new.PSObject.Properties).Count
        }
    } catch {}

    $diff = $newEntries - $oldEntries
    $diffStr = if ($diff -gt 0) { "+$diff" } elseif ($diff -lt 0) { "$diff" } else { "0" }
    Write-Host "    Entries: $oldEntries → $newEntries ($diffStr)" -ForegroundColor Green
    $delta += "$($s.Name): $oldEntries→$newEntries ($diffStr)"
}

Write-Host ""
Write-Host "=== LISTO ===" -ForegroundColor Green
Write-Host ""
Write-Host "Seeds copiados a app/public/data/. Ahora:"
Write-Host '  .\update.bat "refrescar seeds: ' + ($delta -join '; ') + '"'
Write-Host ""
Write-Host "GitHub Actions deploya en ~3 min. Cami refresca y ve la data nueva."
