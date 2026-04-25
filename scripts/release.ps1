<#
.SYNOPSIS
    Release one-liner para el sistema Dra Cami Contractual.

.DESCRIPTION
    Hace TODO lo necesario para que aparezca un update en la PC de Cami:

      1. Bumpea la versi�n en tauri.conf.json + Cargo.toml + app/package.json
      2. Hace `git commit` con los cambios de versi�n
      3. Crea el tag `vX.Y.Z`
      4. Hace `git push origin <branch> --follow-tags`

    GitHub Actions detecta el tag y compila + firma + publica el release.
    La PC de Cami detecta el nuevo manifest, le muestra el popup, ella
    clickea "Actualizar" y listo.

.PARAMETER Notes
    Texto que la Dra. ve en el popup de actualizaci�n. Mant�n corto y
    legible (1-2 l�neas en espa�ol). Ejemplo:
        "fix: la tabla rompi� con vigencias mixtas"

.PARAMETER Major
    Bumpea la versi�n MAYOR (1.x.y -> 2.0.0). Usar cuando rompes algo
    o cambias dr�sticamente la UI.

.PARAMETER Minor
    Bumpea la versi�n MENOR (1.0.x -> 1.1.0). Usar para features nuevos.

.PARAMETER Version
    Versi�n exacta (ej. "1.2.3"). Override de los flags Major/Minor.

.PARAMETER DryRun
    No commitea ni pushea, s�lo muestra qu� har�a.

.EXAMPLE
    .\scripts\release.ps1 "fix: el modal no abr�a si la fila era vac�a"
    # Bumpea patch (1.0.0 -> 1.0.1) y release.

.EXAMPLE
    .\scripts\release.ps1 -Minor "agregada columna de adiciones"
    # 1.0.5 -> 1.1.0 con esa nota.

.EXAMPLE
    .\scripts\release.ps1 -Version 2.0.0 "rewrite del frontend"
    # Forzar 2.0.0.

.EXAMPLE
    .\scripts\release.ps1 -DryRun "test"
    # Imprime los cambios pero no toca git.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true, HelpMessage = "Texto que la Dra. ve en el popup")]
    [string]$Notes,

    [Parameter()]
    [switch]$Major,

    [Parameter()]
    [switch]$Minor,

    [Parameter()]
    [string]$Version,

    [Parameter()]
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Resolve repo root regardless of where you call the script from.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TauriConf = Join-Path $RepoRoot "tauri\tauri.conf.json"
$CargoToml = Join-Path $RepoRoot "tauri\Cargo.toml"
$AppPkgJson = Join-Path $RepoRoot "app\package.json"
$PyProject = Join-Path $RepoRoot "pyproject.toml"

function Read-CurrentVersion {
    $json = Get-Content $TauriConf -Raw | ConvertFrom-Json
    return $json.version
}

function Bump-Version([string]$current, [bool]$bumpMajor, [bool]$bumpMinor) {
    if (-not ($current -match '^(\d+)\.(\d+)\.(\d+)$')) {
        throw "Versi�n actual '$current' no parece SemVer (X.Y.Z)."
    }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $patch = [int]$Matches[3]

    if ($bumpMajor) {
        return "$($major + 1).0.0"
    } elseif ($bumpMinor) {
        return "$major.$($minor + 1).0"
    } else {
        return "$major.$minor.$($patch + 1)"
    }
}

function Update-TauriConf([string]$newVer) {
    $content = Get-Content $TauriConf -Raw
    $updated = $content -replace '"version":\s*"\d+\.\d+\.\d+"', "`"version`": `"$newVer`""
    if ($DryRun) { Write-Host "  [DRY] tauri.conf.json -> $newVer" } else {
        Set-Content -Path $TauriConf -Value $updated -NoNewline -Encoding utf8
    }
}

function Update-CargoToml([string]$newVer) {
    $content = Get-Content $CargoToml -Raw
    # S�lo el `version = "..."` que est� en `[package]` (no toca dependencias)
    $updated = [regex]::Replace($content,
        '(?m)^(version\s*=\s*)"\d+\.\d+\.\d+"',
        "`$1`"$newVer`"")
    if ($DryRun) { Write-Host "  [DRY] Cargo.toml -> $newVer" } else {
        Set-Content -Path $CargoToml -Value $updated -NoNewline -Encoding utf8
    }
}

function Update-AppPackageJson([string]$newVer) {
    $content = Get-Content $AppPkgJson -Raw
    $updated = $content -replace '"version":\s*"\d+\.\d+\.\d+"', "`"version`": `"$newVer`""
    if ($DryRun) { Write-Host "  [DRY] app/package.json -> $newVer" } else {
        Set-Content -Path $AppPkgJson -Value $updated -NoNewline -Encoding utf8
    }
}

function Update-PyProjectIfPresent([string]$newVer) {
    if (-not (Test-Path $PyProject)) { return }
    $content = Get-Content $PyProject -Raw
    $updated = [regex]::Replace($content,
        '(?m)^(version\s*=\s*)"\d+\.\d+\.\d+"',
        "`$1`"$newVer`"")
    if ($DryRun) { Write-Host "  [DRY] pyproject.toml -> $newVer" } else {
        Set-Content -Path $PyProject -Value $updated -NoNewline -Encoding utf8
    }
}

function Invoke-Git([string[]]$gitArgs) {
    # NOTA: el par�metro NO se llama `$args` porque PowerShell ya tiene esa
    # variable autom�tica y, aunque parezca que la sombra, en algunas
    # ediciones queda vac�a y los `git` lanzados quedan sin argumentos.
    if ($DryRun) {
        Write-Host "  [DRY] git $($gitArgs -join ' ')"
        return
    }
    & git @gitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($gitArgs -join ' ') fall� (exit $LASTEXITCODE)"
    }
}

# --- Main flow ---------------------------------------------------------

Write-Host ""
Write-Host "=== Release Dra Cami Contractual ===" -ForegroundColor Cyan
Write-Host ""

# Verificaciones previas: trabajo limpio en el branch actual.
if (-not $DryRun) {
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD).Trim()
    Write-Host "Branch actual: $branch"
    $dirty = (& git -C $RepoRoot status --porcelain) -ne $null
    if ($dirty) {
        Write-Host "Hay cambios sin commitear. Commitealos antes del release." -ForegroundColor Yellow
        & git -C $RepoRoot status --short
        Write-Host ""
        $resp = Read-Host "�Commitear estos cambios autom�ticamente con el mismo mensaje del release? (s/N)"
        if ($resp -ne "s" -and $resp -ne "S") {
            Write-Host "Abortando." -ForegroundColor Red
            exit 1
        }
        Write-Host "Stageando todo..."
        Invoke-Git @("-C", $RepoRoot, "add", "-A")
        Invoke-Git @("-C", $RepoRoot, "commit", "-m", $Notes)
    }
}

$currentVer = Read-CurrentVersion
Write-Host "Versi�n actual: $currentVer"

if ($Version) {
    if (-not ($Version -match '^\d+\.\d+\.\d+$')) {
        throw "El -Version '$Version' debe ser X.Y.Z (SemVer)."
    }
    $newVer = $Version
} else {
    $newVer = Bump-Version $currentVer $Major.IsPresent $Minor.IsPresent
}

Write-Host "Nueva versi�n:  $newVer" -ForegroundColor Green
Write-Host "Notas:          $Notes"
Write-Host ""
Write-Host "Aplicando bumps de versi�n..."
Update-TauriConf $newVer
Update-CargoToml $newVer
Update-AppPackageJson $newVer
Update-PyProjectIfPresent $newVer

Write-Host ""
Write-Host "Commit + tag + push..."
Invoke-Git @("-C", $RepoRoot, "add",
    "tauri/tauri.conf.json",
    "tauri/Cargo.toml",
    "app/package.json")
if (Test-Path $PyProject) {
    Invoke-Git @("-C", $RepoRoot, "add", "pyproject.toml")
}
Invoke-Git @("-C", $RepoRoot, "commit", "-m", "chore: release v$newVer`n`n$Notes")
Invoke-Git @("-C", $RepoRoot, "tag", "-a", "v$newVer", "-m", $Notes)
Invoke-Git @("-C", $RepoRoot, "push", "--follow-tags")

Write-Host ""
Write-Host "=== LISTO ===" -ForegroundColor Green
Write-Host ""
Write-Host "GitHub Actions est� compilando el MSI. Sigui� en:"
Write-Host "  https://github.com/smarroquinc10/14-SECOP-Dr-Camila-Mendoza/actions"
Write-Host ""
Write-Host "Cuando termine (~12 min), la app de Cami va a detectar el update"
Write-Host "la pr�xima vez que abra el programa o cada 4 horas si lo deja"
Write-Host "abierto. Ver� el popup y solo tendr� que clickear Actualizar."
Write-Host ""
