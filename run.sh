#!/usr/bin/env bash
# =============================================================================
# ARIAKE OCTA Analysis — run.sh (macOS)
# =============================================================================
# Usage:
#   ./run.sh                  # 通常起動（venv作成 → 依存インストール → 起動）
#   ./run.sh --setup-only     # 環境セットアップのみ（Streamlit起動しない）
#   ./run.sh --skip-setup     # 依存チェックをスキップして即起動
#   ./run.sh --reset          # .venv を削除して作り直してから起動
#   ./run.sh --port 8502      # ポート指定
#   ./run.sh --key mypassword # アクセスキー指定
#   ./run.sh --no-browser     # ブラウザ自動起動を無効化
# =============================================================================

set -euo pipefail

# ── カラー出力 ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "\n${BOLD}${BLUE}▶ $*${NC}"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }

# ── デフォルト設定 ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
MAIN_SCRIPT="${SCRIPT_DIR}/mainstreamer.py"
PORT="${STREAMLIT_SERVER_PORT:-8501}"
RESET_VENV=false
SETUP_ONLY=false
SKIP_SETUP=false
OPEN_BROWSER=true
ACCESS_KEY="${ARIAKE_ACCESS_KEY:-ariake2024}"

# sknw==0.15 の numba 依存が Python 3.9 ホイールで解決できるため 3.9 を優先
# (3.12 では llvmlite のソースビルドが失敗するため)
PYTHON_RECOMMENDED="3.9 3.10 3.11"
PYTHON_MIN_MINOR=9

# ── 引数パース ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --reset)        RESET_VENV=true ;;
        --setup-only)   SETUP_ONLY=true ;;
        --skip-setup)   SKIP_SETUP=true ;;
        --no-browser)   OPEN_BROWSER=false ;;
        --port)         PORT="$2"; shift ;;
        --port=*)       PORT="${1#*=}" ;;
        --key)          ACCESS_KEY="$2"; shift ;;
        --key=*)        ACCESS_KEY="${1#*=}" ;;
        -h|--help)
            cat <<'EOF'
Usage: ./run.sh [OPTIONS]

Options:
  --reset          .venv を削除して再作成してから起動
  --setup-only     環境セットアップのみ（起動しない）
  --skip-setup     依存チェックをスキップして即起動
  --no-browser     ブラウザ自動起動を無効化
  --port PORT      Streamlit ポート番号 (default: 8501)
  --key  KEY       ARIAKE_ACCESS_KEY を上書き (default: ariake2024)
  -h, --help       このヘルプを表示

Environment Variables:
  ARIAKE_ACCESS_KEY            アクセスキー (default: ariake2024)
  ARIAKE_LOG_LEVEL             ログレベル (default: INFO)
  ARIAKE_SAVE_STAGES           処理ステージ保存 (default: false)
  ARIAKE_ENABLE_ROI_REFINEMENT ROI精緻化 (default: false)
  STREAMLIT_SERVER_PORT        Streamlit ポート (default: 8501)
EOF
            exit 0 ;;
        *) log_warn "Unknown option: $1" ;;
    esac
    shift
done

# ── ヘッダー ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║  🔬  ARIAKE OCTA Analysis Launcher           ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── macOS 確認 ─────────────────────────────────────────────────────────────────
log_step "システム確認"
if [[ "$(uname -s)" != "Darwin" ]]; then
    log_error "このスクリプトは macOS 専用です (OS: $(uname -s))"
    exit 1
fi
ARCH="$(uname -m)"
MACOS_VER="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
log_info "macOS ${MACOS_VER} / ${ARCH}"
[[ "$ARCH" == "arm64" ]] && log_info "Apple Silicon 検出 — ネイティブビルドを使用します"

# ── ファイル確認 ───────────────────────────────────────────────────────────────
for f in "$REQUIREMENTS" "$MAIN_SCRIPT"; do
    if [[ ! -f "$f" ]]; then
        log_error "必要なファイルが見つかりません: $f"
        exit 1
    fi
done
log_success "必要ファイル確認済み"

# ── Python バージョンユーティリティ ──────────────────────────────────────────────
_python_minor() {
    "$1" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo ""
}
_python_version_str() {
    "$1" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')" 2>/dev/null || echo ""
}
_is_recommended() {
    local v="$1"
    for r in $PYTHON_RECOMMENDED; do [[ "$v" == "$r" ]] && return 0; done
    return 1
}
_find_python() {
    for ver in $PYTHON_RECOMMENDED 3.9; do
        local cmd="python${ver}"
        if command -v "$cmd" &>/dev/null; then
            local minor; minor=$(_python_minor "$cmd")
            [[ -n "$minor" && "$minor" -ge "$PYTHON_MIN_MINOR" ]] && { echo "$cmd"; return 0; }
        fi
    done
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local minor; minor=$(_python_minor "$cmd")
            [[ -n "$minor" && "$minor" -ge "$PYTHON_MIN_MINOR" ]] && { echo "$cmd"; return 0; }
        fi
    done
    return 1
}

# ── --reset ────────────────────────────────────────────────────────────────────
if [[ "$RESET_VENV" == true && -d "$VENV_DIR" ]]; then
    log_step ".venv をリセット"
    rm -rf "$VENV_DIR"
    log_success ".venv を削除しました"
fi

# ── 仮想環境の確認・作成 ──────────────────────────────────────────────────────
log_step "仮想環境の確認"
VENV_PYTHON="${VENV_DIR}/bin/python"

if [[ -d "$VENV_DIR" ]]; then
    # 壊れた venv を検出
    if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -c "import sys" &>/dev/null; then
        log_warn "仮想環境が壊れています。再作成します..."
        rm -rf "$VENV_DIR"
    else
        # 推奨バージョン以外なら、推奨が使えれば作り直す
        CURRENT_MINOR=$(_python_minor "$VENV_PYTHON")
        CURRENT_SHORT="3.${CURRENT_MINOR}"
        if ! _is_recommended "$CURRENT_SHORT"; then
            BETTER_PY=$(_find_python 2>/dev/null || echo "")
            if [[ -n "$BETTER_PY" ]]; then
                BETTER_MINOR=$(_python_minor "$BETTER_PY")
                BETTER_SHORT="3.${BETTER_MINOR}"
                if _is_recommended "$BETTER_SHORT"; then
                    log_warn "現在の venv は Python ${CURRENT_SHORT} です。推奨 ${BETTER_SHORT} で再作成します..."
                    rm -rf "$VENV_DIR"
                fi
            fi
        fi
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    PYTHON_CMD=$(_find_python) || {
        log_error "Python 3.${PYTHON_MIN_MINOR}+ が見つかりません"
        log_error "Homebrew でインストール: brew install python@3.12"
        exit 1
    }
    PY_VER=$(_python_version_str "$PYTHON_CMD")
    log_info "Python ${PY_VER} (${PYTHON_CMD}) で仮想環境を作成中..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    log_success "仮想環境を作成しました: ${VENV_DIR}"
fi

# アクティベート
source "${VENV_DIR}/bin/activate"
ACTIVE_PY_VER=$(_python_version_str python)
log_success "仮想環境をアクティベート (Python ${ACTIVE_PY_VER})"

# ── 依存関係インストール ───────────────────────────────────────────────────────
if [[ "$SKIP_SETUP" != true ]]; then
    log_step "依存関係のインストール"

    log_info "pip / setuptools / wheel をアップグレード中..."
    # wheel<0.46 & packaging<24 は streamlit 1.28.0 の互換性要件
    pip install --upgrade pip setuptools "wheel<0.46" "packaging>=23.2,<24" --quiet

    # Python 3.9 ではすべての依存パッケージ（sknw/numba/llvmlite 含む）に
    # ビルド済みホイールが存在するためソースビルドは発生しない
    log_info "requirements.txt をインストール中..."
    pip install -r "$REQUIREMENTS" --quiet

    log_info "依存関係の整合性チェック中..."
    if pip check > /dev/null 2>&1; then
        log_success "依存関係に問題ありません"
    else
        log_warn "依存関係に軽微な警告があります（続行します）:"
        pip check 2>&1 | grep -v "llvmlite\|numba" || true
    fi
fi

# ── モジュールインポートテスト ─────────────────────────────────────────────────
# mainstreamer.py の実際のインポートパスに完全準拠:
#   from core.mnv_pipeline import MNVPipeline
#   from core.vd_analysis import VDAnalyzer
#   from core.pattern_metrics import _compute_stability_raw
#   from utils.vd_display_helpers import get_vd_metrics_for_file
#   from scrollfree_roi_ui import ScrollFreeROICanvas
log_step "モジュールインポートテスト"

python - <<PYEOF
import sys, os
sys.path.insert(0, '${SCRIPT_DIR}')
sys.path.insert(0, '${SCRIPT_DIR}/src')
os.chdir('${SCRIPT_DIR}')

errors = []
warnings_list = []

def chk(label, fn, required=True):
    try:
        fn()
        print(f'  ✓ {label}')
    except ImportError as e:
        (errors if required else warnings_list).append(f'{label}: {e}')
    except Exception as e:
        warnings_list.append(f'{label}: {e}')

# 必須: Core Scientific Stack
chk('numpy',                  lambda: __import__('numpy'))
chk('scipy',                  lambda: __import__('scipy'))
chk('pandas',                 lambda: __import__('pandas'))
chk('opencv-python (cv2)',    lambda: __import__('cv2'))
chk('Pillow',                 lambda: __import__('PIL'))
chk('scikit-image',           lambda: __import__('skimage'))
chk('networkx',               lambda: __import__('networkx'))
chk('shapely',                lambda: __import__('shapely'))
chk('matplotlib',             lambda: __import__('matplotlib'))
chk('psutil',                 lambda: __import__('psutil'))

# 必須: Streamlit & UI
chk('streamlit',              lambda: __import__('streamlit'))
chk('streamlit-drawable-canvas',
                              lambda: __import__('streamlit_drawable_canvas'))

# プロジェクト固有 (mainstreamer.py と同一パス, optional)
chk('scrollfree_roi_ui',
    lambda: __import__('scrollfree_roi_ui'), required=False)
chk('core.mnv_pipeline',
    lambda: __import__('core.mnv_pipeline'), required=False)
chk('core.vd_analysis',
    lambda: __import__('core.vd_analysis'), required=False)
chk('core.pattern_metrics',
    lambda: __import__('core.pattern_metrics'), required=False)
chk('utils.vd_display_helpers',
    lambda: __import__('utils.vd_display_helpers'), required=False)

print()
if errors:
    print('❌ インポートエラー:')
    for e in errors: print(f'   ✗ {e}')
    sys.exit(1)
if warnings_list:
    print('⚠️  任意モジュール未検出 (実行時に動的フォールバックが有効):')
    for w in warnings_list: print(f'   ! {w}')
print('✅ 必須モジュールのインポート確認完了')
PYEOF

if [[ $? -ne 0 ]]; then
    log_error "必須モジュールのインポートに失敗しました"
    exit 1
fi

# ── セットアップのみモード ─────────────────────────────────────────────────────
if [[ "$SETUP_ONLY" == true ]]; then
    echo ""
    log_success "セットアップ完了"
    echo ""
    log_info "手動起動コマンド:"
    echo "  source .venv/bin/activate"
    echo "  streamlit run mainstreamer.py --server.port ${PORT}"
    exit 0
fi

# ── 環境変数の設定 ─────────────────────────────────────────────────────────────
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ARIAKE_ACCESS_KEY="${ACCESS_KEY}"
export ARIAKE_LOG_LEVEL="${ARIAKE_LOG_LEVEL:-INFO}"
export ARIAKE_SAVE_STAGES="${ARIAKE_SAVE_STAGES:-false}"
export ARIAKE_ENABLE_ROI_REFINEMENT="${ARIAKE_ENABLE_ROI_REFINEMENT:-false}"
export STREAMLIT_SERVER_PORT="${PORT}"

# ── .streamlit/config.toml が無ければ生成 ────────────────────────────────────
STREAMLIT_CONFIG_DIR="${SCRIPT_DIR}/.streamlit"
STREAMLIT_CONFIG="${STREAMLIT_CONFIG_DIR}/config.toml"
if [[ ! -f "$STREAMLIT_CONFIG" ]]; then
    mkdir -p "$STREAMLIT_CONFIG_DIR"
    cat > "$STREAMLIT_CONFIG" <<'TOML'
[server]
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
serverAddress = "localhost"

[theme]
base = "light"
TOML
    log_info ".streamlit/config.toml を自動生成しました"
fi

# ── 起動 ──────────────────────────────────────────────────────────────────────
log_step "Streamlit 起動"
echo ""
echo -e "  ${BOLD}URL  :${NC} ${CYAN}http://localhost:${PORT}${NC}"
echo -e "  ${BOLD}終了 :${NC} ${YELLOW}Ctrl + C${NC}"
echo ""

# macOS ブラウザ自動起動（サーバーが立ち上がるまで少し待つ）
if [[ "$OPEN_BROWSER" == true ]]; then
    ( sleep 3 && open "http://localhost:${PORT}" ) &
fi

# exec で置き換えることで Ctrl+C がそのまま Streamlit へ伝播する
exec streamlit run "$MAIN_SCRIPT" \
    --server.port="${PORT}" \
    --server.headless="true" \
    --logger.level="error" \
    --server.fileWatcherType="none"
