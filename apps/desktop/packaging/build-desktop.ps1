# Build unsigned SuperVideoGenerator desktop installer (Windows x64 NSIS).
# Reuses existing runtime when python.exe is present; otherwise runs full prepare-runtime.

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path,
    [switch]$SkipPrepare,
    [switch]$PackOnly
)

$ErrorActionPreference = "Stop"

$DesktopDir = Join-Path $RepoRoot "apps/desktop"
$RuntimePython = Join-Path $DesktopDir "runtime/python/python.exe"
$PrepareScript = Join-Path $PSScriptRoot "prepare-runtime.ps1"

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}
if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
    $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
}

if (-not $SkipPrepare) {
    if (Test-Path $RuntimePython) {
        Write-Host "==> Reusing existing runtime; refreshing web + source copy" -ForegroundColor Cyan
        & $PrepareScript -RepoRoot $RepoRoot -SkipPip
    }
    else {
        Write-Host "==> No runtime found; running full prepare-runtime" -ForegroundColor Cyan
        & $PrepareScript -RepoRoot $RepoRoot
    }
}
else {
    Write-Host "==> Skipping prepare-runtime (-SkipPrepare)" -ForegroundColor Yellow
}

if (-not (Test-Path $RuntimePython)) {
    throw "Runtime missing after prepare: $RuntimePython"
}

Push-Location $DesktopDir
try {
    Write-Host "==> npm ci (apps/desktop)" -ForegroundColor Cyan
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Write-Host "npm ci failed; falling back to npm install" -ForegroundColor Yellow
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
    }

    if ($PackOnly) {
        Write-Host "==> electron-builder --dir (unpackaged smoke)" -ForegroundColor Cyan
        npm run pack -- --win --x64
    }
    else {
        Write-Host "==> electron-builder NSIS installer" -ForegroundColor Cyan
        npm run dist -- --win --x64
    }
    if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. Output: $DesktopDir\dist" -ForegroundColor Green
