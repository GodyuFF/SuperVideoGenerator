# Desktop Electron runtime: python-build-standalone + pip + web + source copy.
#
# Embedded Python from astral python-build-standalone install_only archives:
#   https://github.com/astral-sh/python-build-standalone/releases/download/<release-tag>/
#   Asset: <python-version.txt>-<arch>-install_only.tar.gz
#   Windows x64: x86_64-pc-windows-msvc
#   macOS arm64: aarch64-apple-darwin
#   macOS x64:   x86_64-apple-darwin
#
# Windows torch/whisperx: pip install -r requirements-desktop.txt first;
# if CUDA wheels are missing, also run:
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
# Success criterion: `import whisperx` works (CPU fallback when no GPU).

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path,
    [string]$OutDir = "",
    [switch]$SkipTorch,
    [switch]$SkipPip,
    [switch]$SkipWebBuild,
    [switch]$ForcePythonRefresh
)

$ErrorActionPreference = "Stop"

if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "apps/desktop/runtime"
}

$OutDir = [System.IO.Path]::GetFullPath($OutDir)
$PythonOut = Join-Path $OutDir "python"
$WebOut = Join-Path $OutDir "web"
$SrcOut = Join-Path $OutDir "src"
$ReqDesktop = Join-Path $RepoRoot "requirements-desktop.txt"
$VersionFile = Join-Path $PSScriptRoot "python-version.txt"
$ApiBootSrc = Join-Path $PSScriptRoot "api_boot.py"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-PythonBuildStandaloneArch {
    if ($IsWindows -or $env:OS -match "Windows") {
        return "x86_64-pc-windows-msvc"
    }
    if ($IsMacOS) {
        if ([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -eq [System.Runtime.InteropServices.Architecture]::Arm64) {
            return "aarch64-apple-darwin"
        }
        return "x86_64-apple-darwin"
    }
    throw "prepare-runtime.ps1 supports Windows and macOS build hosts only"
}

function Get-PythonExe {
    param([string]$PythonDir)
    if ($IsWindows -or $env:OS -match "Windows") {
        return Join-Path $PythonDir "python.exe"
    }
    return Join-Path $PythonDir "bin/python3"
}

function Invoke-RobocopyMirror {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @("node_modules", "dist", "__pycache__", ".pytest_cache", "runtime")
    )
    if (-not (Test-Path $Source)) {
        throw "Source directory missing: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $xd = @()
    foreach ($dir in $ExcludeDirs) {
        $xd += "/XD"
        $xd += $dir
    }
    & robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NC /NS /NP @xd | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed: $Source -> $Destination (exit $LASTEXITCODE)"
    }
}

Write-Step "Repo root: $RepoRoot"
Write-Step "Output dir: $OutDir"

if (-not (Test-Path $VersionFile)) {
    throw "Missing python-version.txt: $VersionFile"
}
if (-not (Test-Path $ReqDesktop)) {
    throw "Missing requirements-desktop.txt: $ReqDesktop"
}

$pythonTag = (Get-Content $VersionFile -Raw).Trim()
if ($pythonTag -notmatch '^cpython-[\d.]+[+](\d+)$') {
    throw "Invalid python-version.txt: $pythonTag"
}
$releaseTag = $Matches[1]
$arch = Get-PythonBuildStandaloneArch
$assetName = "$pythonTag-$arch-install_only.tar.gz"
$downloadUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$releaseTag/$assetName"

$py = Get-PythonExe $PythonOut
if ((Test-Path $py) -and -not $ForcePythonRefresh) {
    Write-Step "Reuse existing embedded Python: $py"
} else {
    Write-Step "Download embedded Python: $assetName"
    New-Item -ItemType Directory -Force -Path $PythonOut | Out-Null
    $tarPath = Join-Path $env:TEMP $assetName
    if (-not (Test-Path $tarPath)) {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $tarPath -UseBasicParsing
    }

    Write-Step "Extract to $PythonOut"
    if (Test-Path $PythonOut) {
        Remove-Item -Recurse -Force $PythonOut
    }
    New-Item -ItemType Directory -Force -Path $PythonOut | Out-Null
    tar -xzf $tarPath -C $PythonOut

    $nestedPython = Join-Path $PythonOut "python"
    if (Test-Path $nestedPython) {
        Get-ChildItem -Path $nestedPython -Force | Move-Item -Destination $PythonOut -Force
        Remove-Item -Path $nestedPython -Recurse -Force
    }

    $py = Get-PythonExe $PythonOut
    if (-not (Test-Path $py)) {
        throw "Python executable not found after extract: $py"
    }

    Write-Step "ensurepip + upgrade pip"
    & $py -m ensurepip --upgrade
    & $py -m pip install --upgrade pip wheel setuptools
}

if (-not $SkipPip) {
    Write-Step "pip install -r requirements-desktop.txt"
    & $py -m pip install -r $ReqDesktop

    if (-not $SkipTorch) {
        Write-Step "verify torch / whisperx (Windows may install CUDA wheels)"
        $torchOk = $false
        try {
            & $py -c 'import torch; import whisperx; print("torch", torch.__version__)'
            $torchOk = $LASTEXITCODE -eq 0
        } catch {
            $torchOk = $false
        }

        if (-not $torchOk -and ($IsWindows -or $env:OS -match 'Windows')) {
            Write-Host "Installing torch/torchaudio from cu124 index..." -ForegroundColor Yellow
            & $py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
            & $py -c 'import torch; import whisperx; print("torch", torch.__version__)'
            if ($LASTEXITCODE -ne 0) {
                throw "torch/whisperx import failed; see pip logs"
            }
        } elseif (-not $torchOk) {
            throw "torch/whisperx import failed; see pip logs"
        }
    } else {
        Write-Host "SkipTorch: skipping torch/whisperx verification" -ForegroundColor Yellow
    }
} else {
    Write-Host "SkipPip: skipping pip install" -ForegroundColor Yellow
}

if (-not $SkipWebBuild) {
    Write-Step "Build frontend apps/web"
    Push-Location (Join-Path $RepoRoot "apps/web")
    try {
        npm ci
        npm run build
    } finally {
        Pop-Location
    }
} else {
    Write-Host "SkipWebBuild: skipping npm build" -ForegroundColor Yellow
}

$WebDist = Join-Path $RepoRoot "apps/web/dist"
if (-not (Test-Path (Join-Path $WebDist "index.html"))) {
    throw "Frontend build missing: $WebDist/index.html (run npm build or drop -SkipWebBuild)"
}

Write-Step "Copy web/dist -> runtime/web"
if (Test-Path $WebOut) {
    Remove-Item -Recurse -Force $WebOut
}
Copy-Item -Path $WebDist -Destination $WebOut -Recurse -Force

Write-Step "Copy core/ and apps/ -> runtime/src/"
if (Test-Path $SrcOut) {
    Remove-Item -Recurse -Force $SrcOut
}
New-Item -ItemType Directory -Force -Path $SrcOut | Out-Null
Invoke-RobocopyMirror -Source (Join-Path $RepoRoot "core") -Destination (Join-Path $SrcOut "core")
Invoke-RobocopyMirror -Source (Join-Path $RepoRoot "apps") -Destination (Join-Path $SrcOut "apps")

Write-Step "Copy api_boot.py and write requirements.lock"
Copy-Item -Path $ApiBootSrc -Destination (Join-Path $OutDir "api_boot.py") -Force
& $py -m pip freeze | Set-Content -Path (Join-Path $OutDir "requirements.lock") -Encoding utf8

Write-Step "Done"
Write-Host "  Python: $py"
Write-Host "  Web:    $(Join-Path $WebOut 'index.html')"
Write-Host "  Boot:   $(Join-Path $OutDir 'api_boot.py')"
