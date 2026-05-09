# =============================================================================
# build_win.ps1 — ARIAKE OCTA Windows ビルドスクリプト (PowerShell)
# =============================================================================
# フロー: PyInstaller ビルド -> 成果物の確認 -> ZIP 圧縮
#
# 使い方:
#   .\build_win.ps1                   # 通常ビルド
#   .\build_win.ps1 -Clean            # dist/ build/ を削除してから実行
#   .\build_win.ps1 -Debug            # デバッグコンソールを有効にしてビルド
# =============================================================================

param (
    [switch]$Clean,
    [switch]$Debug
)

# ── 設定 ──────────────────────────────────────────────────────────────────────
$APP_NAME = "ARIAKE_OCTA"
$SCRIPT_DIR = $PSScriptRoot
$DIST_DIR = Join-Path $SCRIPT_DIR "dist"
$BUILD_DIR = Join-Path $SCRIPT_DIR "build"
$SPEC_FILE = Join-Path $SCRIPT_DIR "ARIAKE_OCTA_win.spec"
$PYTHON_EXE = "python" # システムの python または仮想環境内のパス

# 仮想環境の自動検出
if (Test-Path (Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe")) {
    $PYTHON_EXE = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"
    Write-Host "[INFO] Using virtual environment Python: $PYTHON_EXE" -ForegroundColor Cyan
}

# ── ヘッダー ──────────────────────────────────────────────────────────────────
Write-Host "`n"
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║  Windows  ARIAKE OCTA — Windows EXE Builder  ║" -ForegroundColor Blue
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host "`n"

# ── クリーン ──────────────────────────────────────────────────────────────────
if ($Clean) {
    Write-Host "━━ クリーン ━━" -ForegroundColor Yellow
    if (Test-Path $DIST_DIR) { Remove-Item -Path $DIST_DIR -Recurse -Force }
    if (Test-Path $BUILD_DIR) { Remove-Item -Path $BUILD_DIR -Recurse -Force }
    Write-Host "[✓] dist/ build/ を削除しました" -ForegroundColor Green
}

if (-not (Test-Path $DIST_DIR)) { New-Item -ItemType Directory -Path $DIST_DIR }

# ── 必須ツールの確認 ─────────────────────────────────────────────────────────
Write-Host "━━ 必須ツールの確認 ━━" -ForegroundColor Blue
try {
    & $PYTHON_EXE --version | Out-Null
    Write-Host "[✓] Python 確認済み" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python が見つかりません。パスを確認してください。" -ForegroundColor Red
    exit 1
}

# PyInstaller の確認とインストール
& $PYTHON_EXE -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] PyInstaller をインストール中..." -ForegroundColor Yellow
    & $PYTHON_EXE -m pip install pyinstaller --quiet
} else {
    Write-Host "[✓] PyInstaller 確認済み" -ForegroundColor Green
}

# 主要依存パッケージの確認
$pkgs = @("flet", "fastapi", "uvicorn", "multipart", "cv2", "skimage", "PIL", "imagecodecs")
foreach ($pkg in $pkgs) {
    & $PYTHON_EXE -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] $pkg が見つかりません。ビルド前にインストールしてください。" -ForegroundColor Yellow
    }
}

# ── PyInstaller ビルド ────────────────────────────────────────────────────────
Write-Host "`n━━ PyInstaller ビルド ━━" -ForegroundColor Blue
Write-Host "[INFO] 使用 spec: $(Split-Path $SPEC_FILE -Leaf)" -ForegroundColor Cyan

# デバッグモードの反映
if ($Debug) {
    Write-Host "[INFO] Debug mode enabled (console will be visible)" -ForegroundColor Yellow
    $env:PYI_DEBUG = "1"
    # spec ファイル内の DEBUG_MODE = True を一時的に書き換えるのは複雑なので、
    # 必要に応じて spec 側で環境変数を読むように設計するのが望ましいです。
}

& $PYTHON_EXE -m PyInstaller `
    --clean `
    --noconfirm `
    --distpath="$DIST_DIR" `
    --workpath="$BUILD_DIR" `
    "$SPEC_FILE"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] ビルドに失敗しました。" -ForegroundColor Red
    exit 1
}

$EXE_PATH = Join-Path $DIST_DIR "$APP_NAME\$APP_NAME.exe"
if (-not (Test-Path $EXE_PATH)) {
    Write-Host "[ERROR] EXE が見つかりません: $EXE_PATH" -ForegroundColor Red
    exit 1
}

Write-Host "`n[✓] PyInstaller ビルド完了: $EXE_PATH" -ForegroundColor Green

# ── ZIP 圧縮 (オプション) ──────────────────────────────────────────────────────
Write-Host "`n━━ ZIP 圧縮 ━━" -ForegroundColor Blue
$ZIP_OUT = Join-Path $DIST_DIR "$APP_NAME.zip"
if (Test-Path $ZIP_OUT) { Remove-Item $ZIP_OUT }

Compress-Archive -Path (Join-Path $DIST_DIR "$APP_NAME\*") -DestinationPath $ZIP_OUT
Write-Host "[✓] ZIP 作成完了: $ZIP_OUT" -ForegroundColor Green

# ── 完了サマリー ──────────────────────────────────────────────────────────────
Write-Host "`n"
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  ✅  ビルド完了                               ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host "`n"
Write-Host "  出力フォルダ: $DIST_DIR\$APP_NAME"
Write-Host "  実行ファイル: $EXE_PATH"
Write-Host "  配布用 ZIP  : $ZIP_OUT"
Write-Host "`n"
Write-Host "インストール手順:"
Write-Host "  1. $APP_NAME.zip を展開します。"
Write-Host "  2. 展開されたフォルダ内の $APP_NAME.exe を実行します。"
Write-Host "`n"
