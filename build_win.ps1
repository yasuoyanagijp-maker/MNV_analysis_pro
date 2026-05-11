# build_win.ps1 - ARIAKE OCTA Windows Build Script
# Default: incremental (no PyInstaller --clean). Use -Clean for "from scratch" — can take much longer (30 min–hours on slow PCs / AV).
param (
    [switch]$Clean,
    [switch]$Debug
)

$APP_NAME = "ARIAKE_OCTA"
$SCRIPT_DIR = $PSScriptRoot
$DIST_DIR = Join-Path $SCRIPT_DIR "dist"
$BUILD_DIR = Join-Path $SCRIPT_DIR "build"
$SPEC_FILE = Join-Path $SCRIPT_DIR "ARIAKE_OCTA_win.spec"
$PYTHON_EXE = "python"

if (Test-Path (Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe")) {
    $PYTHON_EXE = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"
    Write-Host "[INFO] Using virtual environment Python: $PYTHON_EXE"
}

if ($Clean) {
    Write-Host "[INFO] Cleaning..."
    if (Test-Path $DIST_DIR) { Remove-Item -Path $DIST_DIR -Recurse -Force }
    if (Test-Path $BUILD_DIR) { Remove-Item -Path $BUILD_DIR -Recurse -Force }
}

if (-not (Test-Path $DIST_DIR)) { New-Item -ItemType Directory -Path $DIST_DIR | Out-Null }

Write-Host "[INFO] Checking tools..."
try {
    & $PYTHON_EXE --version | Out-Null
} catch {
    Write-Host "[ERROR] Python not found."
    exit 1
}

# Warm import: first PyInstaller load touches platform.win32_ver() and can sit silent ~1-2 min on slow PCs.
$env:PYTHONUNBUFFERED = "1"
Write-Host "[INFO] Loading PyInstaller (please wait)."
Write-Host "[HINT] In this terminal, Ctrl+C stops the build—it is not Copy. Use Ctrl+Shift+C or right-click to copy (Windows Terminal)."
& $PYTHON_EXE -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller failed to start. Try: pip install -U pyinstaller"
    exit 1
}

if ($Debug) {
    Write-Host "[INFO] Debug mode enabled"
    $env:PYI_DEBUG = "1"
}

$pyiArgs = @("--noconfirm", "--distpath=$DIST_DIR", "--workpath=$BUILD_DIR", $SPEC_FILE)
if ($Clean) {
    Write-Host "[INFO] Clean PyInstaller cache (--clean) + removed dist/build folders above."
    $pyiArgs = @("--clean") + $pyiArgs
} else {
    Write-Host "[INFO] Incremental build (omit -Clean for speed). First line of Analysis may take several minutes."
}

Write-Host "[INFO] Starting PyInstaller..."

& $PYTHON_EXE -m PyInstaller @pyiArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Build failed."
    exit 1
}

$EXE_PATH = Join-Path $DIST_DIR "$APP_NAME\$APP_NAME.exe"
if (-not (Test-Path $EXE_PATH)) {
    Write-Host "[ERROR] EXE not found at $EXE_PATH"
    exit 1
}

Write-Host "[SUCCESS] Build completed: $EXE_PATH"

Write-Host "[INFO] Creating ZIP..."
$ZIP_OUT = Join-Path $DIST_DIR "$APP_NAME.zip"
if (Test-Path $ZIP_OUT) { Remove-Item $ZIP_OUT }
Compress-Archive -Path (Join-Path $DIST_DIR "$APP_NAME\*") -DestinationPath $ZIP_OUT
Write-Host "[SUCCESS] ZIP created: $ZIP_OUT"
