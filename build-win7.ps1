<#
.SYNOPSIS
    Build Win7-compatible de CreatorFlow Studio.

.DESCRIPTION
    Usa Python 3.8 (x64) en un venv dedicado y dependencias fijadas
    en requirements-win7.txt para generar EXE + instalador.

.USAGE
    .\build-win7.ps1
    .\build-win7.ps1 -Version "1.0.1"
    .\build-win7.ps1 -SkipInstaller
    .\build-win7.ps1 -PythonExe "C:\Python38\python.exe"
#>

param(
    [string] $Version       = "",
    [switch] $SkipInstaller = $false,
    [switch] $Clean         = $true,
    [string] $PythonExe     = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root            = $PSScriptRoot
$SpecFile        = Join-Path $Root "CreatorFlowStudio.spec"
$IssFile         = Join-Path $Root "installer\CreatorFlowStudio.iss"
$DistExe         = Join-Path $Root "dist\CreatorFlowStudio.exe"
$VersionFile     = Join-Path $Root "config\version.txt"
$ReqWin7         = Join-Path $Root "requirements-win7.txt"
$VenvDir         = Join-Path $Root ".venv-win7"
$VenvPython      = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip         = Join-Path $VenvDir "Scripts\pip.exe"

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

function Resolve-Python38 {
    param([string] $ExplicitPython)

    if ($ExplicitPython) {
        if (-not (Test-Path $ExplicitPython)) {
            Write-Err "PythonExe no existe: $ExplicitPython"
        }
        return $ExplicitPython
    }

    $candidates = @()

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $pyPath = (& py -3.8 -c "import sys;print(sys.executable)").Trim()
            if ($pyPath) { $candidates += $pyPath }
        } catch {
            # ignore
        }
    }

    $candidates += @(
        "C:\Python38\python.exe",
        "C:\Python38-32\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python38\python.exe"
    )

    foreach ($c in $candidates) {
        if (-not $c) { continue }
        if (-not (Test-Path $c)) { continue }
        try {
            $ver = (& $c -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
            if ($ver -eq "3.8") {
                return $c
            }
        } catch {
            # ignore and continue
        }
    }

    Write-Err "No se encontro Python 3.8. Instala Python 3.8.10 x64 o usa -PythonExe."
}

if (-not $Version) {
    if (Test-Path $VersionFile) {
        $Version = (Get-Content $VersionFile -Raw).Trim()
    } else {
        $Version = "1.0.0"
    }
}

Write-Host "`nCreatorFlow Studio -- Build WIN7 v$Version" -ForegroundColor Yellow
Write-Host "-------------------------------------------" -ForegroundColor DarkGray

if (-not (Test-Path $ReqWin7)) {
    Write-Err "No existe requirements-win7.txt"
}

$py38 = Resolve-Python38 -ExplicitPython $PythonExe
Write-OK "Python para build Win7: $py38"

Write-Step "Preparando entorno virtual Win7 (.venv-win7)..."
if (-not (Test-Path $VenvPython)) {
    & $py38 -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Err "No se pudo crear .venv-win7" }
}

Write-Step "Instalando dependencias Win7 en el venv..."
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Write-Err "Fallo actualizando pip/setuptools/wheel" }

& $VenvPip install -r $ReqWin7
if ($LASTEXITCODE -ne 0) { Write-Err "Fallo instalando requirements-win7.txt" }

Write-Step "Compilando EXE con PyInstaller (perfil Win7)..."
$pyArgs = @($SpecFile)
if ($Clean) { $pyArgs += "--clean" }

Push-Location $Root
try {
    # PyInstaller often writes informational lines to stderr; temporarily avoid
    # treating native stderr as a terminating PowerShell error.
    $prevEap = $ErrorActionPreference
    $hasNativePref = $false
    $prevNativePref = $null
    if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $hasNativePref = $true
        $prevNativePref = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    $pyExit = 1
    try {
        $ErrorActionPreference = "Continue"
        & $VenvPython -m PyInstaller @pyArgs 2>&1 | ForEach-Object {
            Write-Host $_
        }
        $pyExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
        if ($hasNativePref) {
            $PSNativeCommandUseErrorActionPreference = $prevNativePref
        }
    }

    if ($pyExit -ne 0) { Write-Err "PyInstaller fallo (exit code $pyExit)" }
} finally {
    Pop-Location
}

if (-not (Test-Path $DistExe)) {
    Write-Err "EXE no encontrado en dist\ despues del build"
}

$exeSizeMB = [math]::Round((Get-Item $DistExe).Length / 1MB, 1)
Write-OK "dist\CreatorFlowStudio.exe generado ($exeSizeMB MB)"

if ($SkipInstaller) {
    Write-Host "`nInstalador omitido (-SkipInstaller)." -ForegroundColor DarkGray
    exit 0
}

Write-Step "Buscando Inno Setup..."
$isccCandidates = @(
    "iscc",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

try {
    $regRoots = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )
    foreach ($rk in $regRoots) {
        if (Test-Path $rk) {
            $reg = Get-ItemProperty -Path $rk -ErrorAction SilentlyContinue
            if ($reg) {
                if ($reg.InstallLocation) {
                    $cand = Join-Path $reg.InstallLocation "ISCC.exe"
                    if ($cand -and -not ($isccCandidates -contains $cand)) {
                        $isccCandidates += $cand
                    }
                }
                if ($reg.DisplayIcon) {
                    $iconPath = ($reg.DisplayIcon -split ',')[0].Trim('"')
                    if ($iconPath) {
                        $iconDir = Split-Path $iconPath -Parent
                        if ($iconDir) {
                            $cand = Join-Path $iconDir "ISCC.exe"
                            if ($cand -and -not ($isccCandidates -contains $cand)) {
                                $isccCandidates += $cand
                            }
                        }
                    }
                }
            }
        }
    }
} catch {
    # non-fatal
}

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
    exit 0
}

Write-Step "Compilando instalador Win7 con Inno Setup (v$Version)..."
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

    # Also keep a channel-specific copy to avoid confusion with Win10+ builds.
    $win7Name = [System.IO.Path]::GetFileNameWithoutExtension($setupExe.Name) + "_win7.exe"
    $win7Path = Join-Path $outputDir $win7Name
    Copy-Item -Path $setupExe.FullName -Destination $win7Path -Force
    Write-OK "Copia Win7: installer\Output\$win7Name"
}

Write-Host "`nBuild Win7 completado." -ForegroundColor Green