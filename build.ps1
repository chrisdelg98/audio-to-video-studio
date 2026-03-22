<#
.SYNOPSIS
    Build completo de Audio to Video Studio.
    Genera el EXE (PyInstaller) y luego el instalador (Inno Setup).

.USAGE
    .\build.ps1                     # build normal
    .\build.ps1 -Version "1.2.0"    # forzar version especifica
    .\build.ps1 -SkipInstaller      # solo EXE, sin instalador
#>

param(
    [string] $Version       = "",
    [switch] $SkipInstaller = $false,
    [switch] $Clean         = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- Rutas -------------------------------------------------------------------
$Root        = $PSScriptRoot
$SpecFile    = Join-Path $Root "AudioToVideoStudio.spec"
$IssFile     = Join-Path $Root "installer\AudioToVideoStudio.iss"
$DistExe     = Join-Path $Root "dist\AudioToVideoStudio.exe"
$VersionFile = Join-Path $Root "config\version.txt"

# --- Helpers -----------------------------------------------------------------
function Write-Step([string]$msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}
function Write-Err([string]$msg) {
    Write-Host "    [ERROR] $msg" -ForegroundColor Red
    exit 1
}

# --- Version -----------------------------------------------------------------
if (-not $Version) {
    if (Test-Path $VersionFile) {
        $Version = (Get-Content $VersionFile -Raw).Trim()
    } else {
        $Version = "1.0.0"
    }
}
Write-Host "`nAudio to Video Studio -- Build v$Version" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor DarkGray

# --- 1. PyInstaller ----------------------------------------------------------
Write-Step "Compilando EXE con PyInstaller..."

$pyArgs = @("AudioToVideoStudio.spec")
if ($Clean) { $pyArgs += "--clean" }

Push-Location $Root
try {
    python -m PyInstaller @pyArgs
    if ($LASTEXITCODE -ne 0) { Write-Err "PyInstaller fallo (exit code $LASTEXITCODE)" }
} finally {
    Pop-Location
}

if (-not (Test-Path $DistExe)) {
    Write-Err "EXE no encontrado en dist\ despues del build"
}

$exeSizeMB = [math]::Round((Get-Item $DistExe).Length / 1MB, 1)
Write-OK "dist\AudioToVideoStudio.exe generado ($exeSizeMB MB)"

# --- 2. Inno Setup (opcional) ------------------------------------------------
if ($SkipInstaller) {
    Write-Host "`nInstalador omitido (-SkipInstaller)." -ForegroundColor DarkGray
    exit 0
}

Write-Step "Buscando Inno Setup..."

$isccCandidates = @(
    "iscc",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$iscc = $null
foreach ($candidate in $isccCandidates) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $iscc = $candidate
        break
    }
    if (Test-Path $candidate -ErrorAction SilentlyContinue) {
        $iscc = $candidate
        break
    }
}

if (-not $iscc) {
    Write-Host "    [SKIP] Inno Setup no encontrado." -ForegroundColor Yellow
    Write-Host "           Instalalo desde: https://jrsoftware.org/isinfo.php" -ForegroundColor DarkGray
    Write-Host "           Luego ejecuta:   iscc installer\AudioToVideoStudio.iss" -ForegroundColor DarkGray
    exit 0
}

Write-Step "Compilando instalador con Inno Setup (v$Version)..."

& $iscc "/DAppVersion=$Version" $IssFile

if ($LASTEXITCODE -ne 0) {
    Write-Err "Inno Setup fallo (exit code $LASTEXITCODE)"
}

$outputDir = Join-Path $Root "installer\Output"
$setupExe  = Get-ChildItem $outputDir -Filter "*Setup*.exe" -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($setupExe) {
    $setupSizeMB = [math]::Round($setupExe.Length / 1MB, 1)
    Write-OK "Instalador: installer\Output\$($setupExe.Name) ($setupSizeMB MB)"
}

Write-Host "`nBuild completado." -ForegroundColor Green
