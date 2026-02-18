#!/bin/bash
# =============================================================================
# ARIAKE_MNV run.sh
# 環境セットアップ＆Streamlitアプリケーション起動スクリプト
# Generated: 2026-02-04
# =============================================================================
# Usage:
#   ./run.sh              # 通常起動（依存関係インストール＋Streamlit起動）
#   ./run.sh --setup-only # 環境セットアップのみ（Streamlit起動なし）
#   ./run.sh --skip-setup # 依存関係チェックをスキップして即座に起動
# =============================================================================

set -e  # エラー時に即座に終了

# -----------------------------------------------------------------------------
# 設定（requirements.txt の "Python 3.9+ (recommended: 3.10-3.12)" に合わせる）
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_MIN_VERSION="3.9"
# 推奨: 3.10-3.12。venv はこのいずれかで作成する（優先順）
PYTHON_RECOMMENDED_VERSIONS="3.12 3.11 3.10"

# 環境変数のデフォルト値
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}${SCRIPT_DIR}/src"
export ARIAKE_LOG_LEVEL="${ARIAKE_LOG_LEVEL:-INFO}"
export ARIAKE_SAVE_STAGES="${ARIAKE_SAVE_STAGES:-false}"
export ARIAKE_ENABLE_ROI_REFINEMENT="${ARIAKE_ENABLE_ROI_REFINEMENT:-false}"

# Streamlit設定
export STREAMLIT_SERVER_PORT="${STREAMLIT_SERVER_PORT:-8501}"
export STREAMLIT_SERVER_HEADLESS="${STREAMLIT_SERVER_HEADLESS:-true}"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# ヘルパー関数
# -----------------------------------------------------------------------------
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python_version() {
    local python_cmd="$1"
    local version
    version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    
    if [[ -z "$version" ]]; then
        return 1
    fi
    
    # バージョン比較 (3.9以上を要求)
    local major minor
    IFS='.' read -r major minor <<< "$version"
    if [[ $major -lt 3 ]] || [[ $major -eq 3 && $minor -lt 9 ]]; then
        return 1
    fi
    
    echo "$version"
    return 0
}

# 指定バージョンが推奨リストに含まれるか
is_recommended_version() {
    local v="$1"
    local r
    for r in $PYTHON_RECOMMENDED_VERSIONS; do
        if [[ "$v" == "$r" ]]; then
            return 0
        fi
    done
    return 1
}

# requirements.txt に合わせて使用する Python コマンドを探す（推奨 3.12→3.11→3.10、可 3.9）
find_python_for_venv() {
    local cmd
    for ver in $PYTHON_RECOMMENDED_VERSIONS 3.9; do
        cmd="python${ver}"
        if command -v "$cmd" &> /dev/null && check_python_version "$cmd" > /dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    if command -v python3 &> /dev/null && check_python_version python3 > /dev/null; then
        echo "python3"
        return 0
    fi
    if command -v python &> /dev/null && check_python_version python > /dev/null; then
        echo "python"
        return 0
    fi
    return 1
}

# -----------------------------------------------------------------------------
# メイン処理
# -----------------------------------------------------------------------------
cd "$SCRIPT_DIR"

# コマンドライン引数の処理
SETUP_ONLY=false
SKIP_SETUP=false

for arg in "$@"; do
    case $arg in
        --setup-only)
            SETUP_ONLY=true
            ;;
        --skip-setup)
            SKIP_SETUP=true
            ;;
        --help|-h)
            echo "Usage: ./run.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --setup-only    環境セットアップのみ実行"
            echo "  --skip-setup    依存関係チェックをスキップ"
            echo "  --help, -h      このヘルプを表示"
            echo ""
            echo "Environment Variables:"
            echo "  ARIAKE_LOG_LEVEL              ログレベル (default: INFO)"
            echo "  ARIAKE_SAVE_STAGES            処理ステージを保存 (default: false)"
            echo "  ARIAKE_ENABLE_ROI_REFINEMENT  ROI精緻化を有効化 (default: false)"
            echo "  STREAMLIT_SERVER_PORT         Streamlitポート (default: 8501)"
            echo ""
            echo "Python: requirements.txt に合わせ 3.9+ 対応、推奨 3.10-3.12。"
            echo "  既存の .venv が推奨外の場合は推奨バージョンで作り直します。"
            exit 0
            ;;
    esac
done

log_info "ARIAKE_MNV 環境セットアップを開始します..."
log_info "作業ディレクトリ: ${SCRIPT_DIR}"

# -----------------------------------------------------------------------------
# Step 1: 仮想環境の確認・作成（requirements.txt 推奨: 3.10-3.12 で作成し直す）
# -----------------------------------------------------------------------------
VENV_PYTHON="${VENV_DIR}/bin/python"
if [[ -d "$VENV_DIR" ]]; then
    # 壊れた venv（別マシン／別 Python 向け）は削除
    if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -c "import sys" &>/dev/null; then
        log_warn "既存の仮想環境の Python が使えません。作り直します..."
        rm -rf "$VENV_DIR"
    else
        # 動作する venv が推奨バージョンでない場合、推奨が使えれば作り直す
        CURRENT_VER=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [[ -n "$CURRENT_VER" ]] && ! is_recommended_version "$CURRENT_VER"; then
            PYTHON_CMD=$(find_python_for_venv)
            if [[ -n "$PYTHON_CMD" ]]; then
                WANT_VER=$(check_python_version "$PYTHON_CMD")
                # 防御: check_python_version が空を返す理論上のケースでは作り直ししない
                if [[ -n "$WANT_VER" ]] && is_recommended_version "$WANT_VER"; then
                    log_warn "既存の仮想環境は Python ${CURRENT_VER} です。推奨 ${WANT_VER} で作り直します..."
                    rm -rf "$VENV_DIR"
                fi
            fi
        fi
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    log_info "仮想環境を作成します（requirements.txt 推奨: ${PYTHON_RECOMMENDED_VERSIONS}）..."
    
    PYTHON_CMD=$(find_python_for_venv)
    if [[ -z "$PYTHON_CMD" ]]; then
        log_error "Python ${PYTHON_MIN_VERSION}+ が見つかりません（推奨: ${PYTHON_RECOMMENDED_VERSIONS}）"
        exit 1
    fi

    PYTHON_VER=$(check_python_version "$PYTHON_CMD")
    log_info "使用するPython: $PYTHON_CMD (${PYTHON_VER})"
    $PYTHON_CMD -m venv "$VENV_DIR"
    log_info "仮想環境を作成しました: ${VENV_DIR}"
fi

# 仮想環境をアクティベート
log_info "仮想環境をアクティベートします..."
source "${VENV_DIR}/bin/activate"

# Pythonバージョン確認
PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
log_info "Python バージョン: ${PYTHON_VERSION}"

# -----------------------------------------------------------------------------
# Step 2: 依存関係のインストール
# -----------------------------------------------------------------------------
if [[ "$SKIP_SETUP" != true ]]; then
    log_info "pip, setuptools, wheel をアップグレードします..."
    # wheel<0.46 and packaging<24 are required for streamlit 1.28.0 compatibility
    pip install --upgrade pip setuptools 'wheel<0.46' 'packaging>=23.2,<24' --quiet
    
    log_info "依存関係をインストールします..."
    pip install -r requirements.txt --quiet
    
    # 依存関係の整合性チェック
    log_info "依存関係の整合性をチェックします..."
    if pip check > /dev/null 2>&1; then
        log_info "✅ 依存関係に問題はありません"
    else
        log_warn "依存関係に問題が検出されました:"
        pip check
        log_warn "続行しますが、問題が発生する可能性があります"
    fi
fi

# -----------------------------------------------------------------------------
# Step 3: 環境の検証
# -----------------------------------------------------------------------------
log_info "主要モジュールのインポートをテストします..."
python -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/src')

errors = []

# Core imports
try:
    import numpy as np
    print(f'  ✓ numpy {np.__version__}')
except ImportError as e:
    errors.append(f'numpy: {e}')

try:
    import scipy
    print(f'  ✓ scipy {scipy.__version__}')
except ImportError as e:
    errors.append(f'scipy: {e}')

try:
    import cv2
    print(f'  ✓ opencv-python {cv2.__version__}')
except ImportError as e:
    errors.append(f'opencv-python: {e}')

try:
    import skimage
    print(f'  ✓ scikit-image {skimage.__version__}')
except ImportError as e:
    errors.append(f'scikit-image: {e}')

try:
    import streamlit as st
    print(f'  ✓ streamlit {st.__version__}')
except ImportError as e:
    errors.append(f'streamlit: {e}')

try:
    from streamlit_drawable_canvas import st_canvas
    print(f'  ✓ streamlit-drawable-canvas')
except ImportError as e:
    errors.append(f'streamlit-drawable-canvas: {e}')

# Project-specific imports
try:
    from src.ariake_octa.mnv.mnv_pipeline import MNVPipeline
    print(f'  ✓ MNVPipeline')
except ImportError as e:
    errors.append(f'MNVPipeline: {e}')

try:
    from src.ariake_octa.vd.vd_pipeline import VDPipeline
    print(f'  ✓ VDPipeline')
except ImportError as e:
    errors.append(f'VDPipeline: {e}')

if errors:
    print()
    print('⚠️ 以下のインポートに失敗しました:')
    for err in errors:
        print(f'  ✗ {err}')
    sys.exit(1)
else:
    print()
    print('✅ すべてのモジュールが正常にインポートされました')
"

if [[ $? -ne 0 ]]; then
    log_error "モジュールインポートテストに失敗しました"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 4: セットアップのみの場合はここで終了
# -----------------------------------------------------------------------------
if [[ "$SETUP_ONLY" == true ]]; then
    log_info "セットアップが完了しました"
    log_info ""
    log_info "Streamlitを起動するには:"
    log_info "  source .venv/bin/activate"
    log_info "  streamlit run mainstreamer.py"
    exit 0
fi

# -----------------------------------------------------------------------------
# Step 5: Streamlitアプリケーションの起動
# -----------------------------------------------------------------------------
log_info ""
log_info "============================================"
log_info "🚀 Streamlit アプリケーションを起動します..."
log_info "============================================"
log_info ""
log_info "URL: http://localhost:${STREAMLIT_SERVER_PORT}"
log_info "終了するには Ctrl+C を押してください"
log_info ""

exec streamlit run mainstreamer.py \
    --server.port="${STREAMLIT_SERVER_PORT}" \
    --server.headless="${STREAMLIT_SERVER_HEADLESS}" \
    --logger.level=error
