"""
ARIAKE OCTA Analysis - Scrollable Version

スクロール可能なUI:
1. メインエリア・アプリ全体がスクロール可能
2. サイドバーは独立してスクロール
3. コンテンツ量に応じて画面をスクロールして閲覧可能
"""

import csv
import hmac
import io
import json
import os
import re
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

# プロジェクトルート設定
ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
for p in [str(ROOT), str(SRC_PATH)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Core MNV Pipeline (ROI対応). SMALL_IMAGE_THRESHOLD は小画像判定に使用（mnv_pipeline と共通）
try:
    from core.mnv_pipeline import MNVPipeline as CoreMNVPipeline, SMALL_IMAGE_THRESHOLD

    HAS_MNV_PIPELINE = True
except ImportError:
    CoreMNVPipeline = None
    SMALL_IMAGE_THRESHOLD = 800  # fallback when core not available
    HAS_MNV_PIPELINE = False

# VD Analyzer
try:
    from core.vd_analysis import VDAnalyzer

    HAS_VD_ANALYZER = True
except ImportError:
    VDAnalyzer = None
    HAS_VD_ANALYZER = False

# Stability raw metrics for CSV export (MNV pipeline の radial_profile から算出)
try:
    from core.pattern_metrics import _compute_stability_raw

    HAS_STABILITY_RAW = True
except ImportError:
    _compute_stability_raw = None
    HAS_STABILITY_RAW = False

# VD display helpers (utils is under src/)
try:
    from utils.vd_display_helpers import get_vd_metrics_for_file, get_vd_summary_value
except ImportError:
    try:
        from src.utils.vd_display_helpers import get_vd_metrics_for_file, get_vd_summary_value
    except ImportError:
        get_vd_metrics_for_file = get_vd_summary_value = None

# スクロールレスROI UI
from scrollfree_roi_ui import ScrollFreeROICanvas, inject_scrollfree_css

APP_NAME = "ARIAKE OCTA"

# ページ設定 - 必ず最初に
st.set_page_config(
    page_title=APP_NAME,
    page_icon="🔬",
    layout="wide",  # 重要
    initial_sidebar_state="collapsed",  # ログイン後はメイン画面を広く表示
)

# CSSインジェクション
inject_scrollfree_css()

# スクロール可能なレイアウトCSS
st.markdown(
    """
    <style>
    /* アプリ全体 - スクロール可能に */
    .appview-container {
        overflow: auto !important;
    }
    
    /* サイドバーのスクロール制御 */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        height: calc(100vh - 60px) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    
    /* メインエリア - スクロール可能 */
    .main .block-container {
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    
    /* コンテンツエリアの内部スクロール */
    .scrollable-content {
        height: calc(100vh - 200px) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-right: 0.5rem;
    }
    
    /* スクロールバーのスタイリング */
    .scrollable-content::-webkit-scrollbar {
        width: 6px;
    }
    
    .scrollable-content::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }
    
    .scrollable-content::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 10px;
    }
    
    .scrollable-content::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    
    /* ボタン行の固定 */
    .action-buttons {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 0.5rem 0;
        border-top: 1px solid #e2e8f0;
        margin-top: 0.5rem;
        z-index: 100;
    }

    .sidebar-section-title {
        font-weight: 700;
        margin-top: 0.25rem;
        margin-bottom: 0.25rem;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# ============================================================================
# セッション状態の初期化
# ============================================================================
def initialize_session_state():
    """セッション状態を初期化"""
    defaults = {
        "mode": "idle",
        "file_queue": [],
        "current_index": 0,
        "per_file_results": {},
        "qc_status": {},
        "persistent_output_dir": None,
        "analysis_type": "MNV",
        "processing_mode": "File Upload",
        "vd_side": "right",
        "sup_suffix": "1.tif",
        "deep_suffix": "2.tif",
        "vd_use_intref": False,
        "vd_intref_percentile": 40.0,
        "vd_intref_center_ratio": 0.5,
        "analyst_name": "Python Streamlit Analysis",
        "session_id": "",
        "analysis_started_at": "",
        "analysis_ended_at": "",
        "analysis_duration_sec": 0.0,
        "analysis_start_epoch": 0.0,
        "analysis_end_logged": False,
        "input_path": "",
        "output_path": "",
        "browsing_for": None,
        "current_browse_path": str(Path.home()),
        "processing_mode_select": "File Upload",
        "folder_exports_saved": False,
        "pending_input_folder_text": None,
        "pending_output_folder_text": None,
        "vd_visualizations": {},
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = not is_auth_enabled()


def ensure_persistent_output_dir() -> Path:
    """
    永続的な出力ディレクトリを確保
    
    Patient IDを含むセッションフォルダー名を生成:
    - 単一患者: session_<patient_id>_<session_id>
    - 複数患者: session_batch_<session_id>
    
    セッションIDを使用することで、フォルダー名とCSVファイル名のタイムスタンプを統一
    
    注意: file_queueが設定されていない場合（folder_selectedイベント時など）は、
    後で再計算される可能性があるため、ここではbatchとして扱う。
    ただし、既にpersistent_output_dirが設定されている場合は、file_queueが更新されても
    フォルダー名は変更されない（一度作成されたフォルダー名は維持される）。
    """
    persistent_dir = st.session_state.get("persistent_output_dir")
    if persistent_dir:
        # 既に設定されている場合は、そのまま返す
        return Path(persistent_dir)
    
    output_path = str(st.session_state.get("output_path", "")).strip()
    if output_path:
        base = Path(output_path).expanduser()
    else:
        base = ROOT / "output"
    base.mkdir(parents=True, exist_ok=True)
    
    # セッションIDを取得（既に生成されている場合はそれを使用、なければ生成）
    session_id = st.session_state.get("session_id")
    if not session_id:
        session_id = _generate_session_id()
        st.session_state.session_id = session_id
    
    # ファイルキューからpatientIDを抽出（共通prefixを使用）
    file_queue = st.session_state.get("file_queue", [])
    patient_ids = set()
    
    if file_queue and len(file_queue) > 0:
        # ファイル名リストを作成
        filenames = [f.get("name", "") for f in file_queue if f.get("name")]
        
        if filenames and len(filenames) > 0:
            # 共通prefixを抽出
            common_prefix = extract_common_prefix_from_filenames(filenames)
            if common_prefix and len(common_prefix) > 0:
                # 共通prefixが見つかった場合、それを患者IDとして使用
                patient_ids.add(common_prefix)
            else:
                # 共通prefixが見つからない場合、各ファイルから個別に抽出
                for filename in filenames:
                    patient_id = extract_patient_id_from_filename(filename, filenames)
                    if patient_id:
                        patient_ids.add(patient_id)
    
    if len(patient_ids) == 1:
        # 単一患者の場合
        patient_id = list(patient_ids)[0]
        # ファイル名に使用できない文字を置換（スラッシュ、バックスラッシュ、コロンなど）
        safe_patient_id = re.sub(r'[<>:"/\\|?*]', '_', patient_id)
        session_dir = base / f"session_{safe_patient_id}_{session_id}"
    else:
        # 複数患者またはファイルキューが空の場合
        session_dir = base / f"session_batch_{session_id}"
    
    session_dir.mkdir(parents=True, exist_ok=True)
    st.session_state.persistent_output_dir = str(session_dir)

    return Path(st.session_state.persistent_output_dir)


def ensure_base_output_dir() -> Path:
    """ベース出力ディレクトリを確保"""
    base = ROOT / "output"
    base.mkdir(exist_ok=True)
    return base


def _generate_session_id() -> str:
    """短いセッションIDを生成"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    """Timezone付きISO時刻"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_access_key() -> str:
    """アクセスキー（環境変数優先）"""
    return os.getenv("ARIAKE_ACCESS_KEY", "ariake2024")


def is_auth_enabled() -> bool:
    """認証有効フラグ"""
    return bool(get_access_key())


def get_analyst_name() -> str:
    """解析者名の正規化"""
    raw = str(st.session_state.get("analyst_name", "")).strip()
    return raw if raw else "Unknown"


def get_analysis_metadata() -> Dict[str, Any]:
    """CSV出力向けのセッションメタ情報"""
    return {
        "Analyst": get_analyst_name(),
        "Started At": st.session_state.get("analysis_started_at", ""),
        "Ended At": st.session_state.get("analysis_ended_at", ""),
        "Duration Sec": st.session_state.get("analysis_duration_sec", 0.0),
        "Session ID": st.session_state.get("session_id", ""),
    }


def extract_common_prefix_from_filenames(filenames: list[str]) -> str:
    """
    ファイル名リストから共通prefixを抽出
    
    例:
    - ['Reg-Avg-Stack_Visit1_image3.tif', 'Reg-Avg-Stack_Visit2_image3.tif'] 
      -> 'Reg-Avg-Stack'
    - ['patientA_xxx_xxx3.tif', 'patientA_yyy_yyy3.tif'] 
      -> 'patientA'
    
    Parameters
    ----------
    filenames : list[str]
        ファイル名のリスト
    
    Returns
    -------
    str
        共通prefix（見つからない場合は空文字列）
    """
    if not filenames or len(filenames) < 2:
        return ""
    
    # 拡張子を除いたstemを取得
    stems = [Path(f).stem for f in filenames]
    
    # 最長共通prefixを計算（Vertical Scanning方式）
    if not stems:
        return ""
    
    # 最初の文字列を基準にする
    first_stem = stems[0]
    if not first_stem:
        return ""
    
    # 各文字位置をチェック
    common_length = 0
    for i in range(len(first_stem)):
        char = first_stem[i]
        # すべての文字列で同じ位置の文字が一致するかチェック
        if all(i < len(stem) and stem[i] == char for stem in stems):
            common_length = i + 1
        else:
            break
    
    if common_length == 0:
        return ""
    
    common_prefix = first_stem[:common_length]
    
    # アンダースコアやハイフンで区切られた部分までを取得
    # 例: 'Reg-Avg-Stack_Visit1' -> 'Reg-Avg-Stack' (最後の区切り文字の前まで)
    # ただし、共通prefixが完全に一致する場合はそのまま返す
    if common_length == len(first_stem):
        return common_prefix
    
    # 共通prefixの最後の区切り文字（_ または -）の位置を探す
    # これにより、'Reg-Avg-Stack_' のような不完全な区切りを避ける
    last_separator = -1
    for sep in ['_', '-']:
        pos = common_prefix.rfind(sep)
        if pos > last_separator:
            last_separator = pos
    
    if last_separator > 0:
        # 区切り文字の前までを返す（区切り文字自体は含めない）
        return common_prefix[:last_separator]
    
    return common_prefix


def extract_patient_id_from_filename(filename: str, file_list: Optional[list[str]] = None) -> str:
    """
    ファイル名から患者ID候補を抽出
    
    複数ファイルがある場合、共通prefixを使用して患者IDを抽出します。
    単一ファイルの場合、または共通prefixが見つからない場合は従来の方法を使用します。
    
    Parameters
    ----------
    filename : str
        ファイル名
    file_list : Optional[list[str]]
        同じ患者の可能性があるファイル名のリスト（Folder Batchモードで使用）
    
    Returns
    -------
    str
        患者ID
    """
    # 複数ファイルがある場合、共通prefixを試みる
    if file_list and len(file_list) > 1:
        common_prefix = extract_common_prefix_from_filenames(file_list)
        if common_prefix:
            return common_prefix
    
    # 従来の方法（単一ファイルまたは共通prefixが見つからない場合）
    stem = Path(filename).stem
    if "__" in stem:
        tail = stem.split("__", 1)[1]
        token = tail.split("_", 1)[0].strip()
        if token:
            return token
    return stem


def filter_mnv_files_for_roi_selection(
    image_files: list[Path],
    analysis_type: str = "MNV",
) -> list[Path]:
    """
    MNV解析のFolder Batchモードで、ROI指定画面に表示するファイルをフィルタリング

    ルール:
    - MNV解析の場合: `*3.tif` で終わるファイルのみを含める
    - `*1.tif`, `*2.tif`, `*4.tif` で終わるファイルは除外
    - `image3` を含むファイルは含める、`image1`, `image2`, `image4` を含むファイルは除外
    - VD解析の場合はフィルタリングしない（既存の動作を維持）

    Parameters
    ----------
    image_files : list[Path]
        フォルダー内の全画像ファイルのリスト
    analysis_type : str
        解析タイプ（"MNV" または "VD"）

    Returns
    -------
    list[Path]
        フィルタリング後のファイルリスト
    """
    if analysis_type != "MNV":
        # VD解析の場合はフィルタリングしない
        return image_files

    filtered_files = []
    exclude_patterns = [
        # サフィックスパターン: *1.tif, *2.tif, *4.tif など
        (r"1\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        (r"2\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        (r"4\.(tif|tiff|png|jpg|jpeg)$", re.IGNORECASE),
        # image1, image2, image4 を含むファイル名
        (r"image[124]", re.IGNORECASE),
    ]

    for file_path in image_files:
        filename = file_path.name
        should_exclude = False

        # 除外パターンをチェック
        for pattern, flags in exclude_patterns:
            if re.search(pattern, filename, flags):
                should_exclude = True
                break

        if should_exclude:
            continue

        # 3.tif で終わる、または image3 を含むファイルを含める
        if (
            re.search(r"3\.(tif|tiff|png|jpg|jpeg)$", filename, re.IGNORECASE)
            or re.search(r"image3", filename, re.IGNORECASE)
        ):
            filtered_files.append(file_path)

    return filtered_files


def find_fd_pair_image(
    current_filename: str,
    folder_path: Path,
    fd_suffixes: tuple = ("4.tif", "4.tiff", "4.png", "4.jpg", "4.jpeg"),
) -> Optional[str]:
    """
    現在のMNV画像ファイル名から対応するFD用画像（4.*）を見つける

    VD解析の `_find_file_pairs()` ロジックを参考に実装。
    ファイル名からpatient_idを抽出し、同じフォルダー内で
    patient_id + "4.*" のパターンでファイルを探す。

    Parameters
    ----------
    current_filename : str
        現在処理中のMNV画像ファイル名（例: "patient_001_MNV.tif" または "Reg-Avg-Stack_Visit1_image3.tif"）
    folder_path : Path
        画像が存在するフォルダーパス
    fd_suffixes : tuple
        FD画像のサフィックス候補（デフォルト: 4.tif, 4.tiff, 4.png, 4.jpg, 4.jpeg）

    Returns
    -------
    Optional[str]
        見つかった場合、FD画像のパス（文字列）。見つからない場合 None
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return None

    filename_stem = Path(current_filename).stem
    filename_ext = Path(current_filename).suffix

    # パターン1: image3/image4 を含むファイル名の場合（例: Reg-Avg-Stack_Visit1_image3.tif）
    # FD用画像は4.*のため、image4 に置き換えたファイル名を優先して探す
    image3_match = re.search(r"image3", filename_stem, re.IGNORECASE)
    image4_match = re.search(r"image4", filename_stem, re.IGNORECASE)
    
    if image3_match or image4_match:
        # FD用画像（4.*）を優先: image4 に置き換えたファイル名を探す
        base_name_image4 = re.sub(r"image[34]", "image4", filename_stem, flags=re.IGNORECASE)
        candidate_image4 = folder_path / f"{base_name_image4}{filename_ext}"
        if candidate_image4.exists() and candidate_image4.is_file():
            return str(candidate_image4)
        # 見つからない場合のみ image3 を探す（フォールバック）
        base_name = re.sub(r"image[34]", "image3", filename_stem, flags=re.IGNORECASE)
        candidate_image3 = folder_path / f"{base_name}{filename_ext}"
        if candidate_image3.exists() and candidate_image3.is_file():
            return str(candidate_image3)

    # パターン2: 通常のpatient_idベースの探索（VD解析と同様）
    patient_id = extract_patient_id_from_filename(current_filename)

    # サフィックスを最長一致優先でソート（4.tiff を 4.tif より先に判定）
    fd_suffixes_sorted = sorted(fd_suffixes, key=len, reverse=True)

    # 各サフィックスでファイルを探索
    for suffix in fd_suffixes_sorted:
        # パターン2-1: {patient_id}_{suffix} (例: patient_001_4.tif)
        candidate1 = folder_path / f"{patient_id}_{suffix}"
        if candidate1.exists() and candidate1.is_file():
            return str(candidate1)

        # パターン2-2: {patient_id}{suffix} (例: patient_0014.tif)
        candidate2 = folder_path / f"{patient_id}{suffix}"
        if candidate2.exists() and candidate2.is_file():
            return str(candidate2)

        # パターン2-3: {patient_id}_FD_{suffix} (例: patient_001_FD_4.tif)
        candidate3 = folder_path / f"{patient_id}_FD_{suffix}"
        if candidate3.exists() and candidate3.is_file():
            return str(candidate3)

    return None


def mode_label(mode: str) -> str:
    """UI表示用モードラベル"""
    labels = {
        "idle": "Idle",
        "mnv_roi": "MNV ROI Selection",
        "mnv_qc": "MNV QC Review",
        "vd_qc": "VD QC Review",
        "summary": "Summary",
    }
    return labels.get(mode, mode)


def _get_log_file_path(force_session: bool = False) -> Path:
    """ログファイルパスを取得"""
    if force_session:
        log_root = ensure_persistent_output_dir() / "exports" / "logs"
    else:
        persistent = st.session_state.get("persistent_output_dir")
        if persistent:
            log_root = Path(persistent) / "exports" / "logs"
        else:
            log_root = ensure_base_output_dir() / "exports" / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    return log_root / "events.jsonl"


def log_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    force_session: bool = False,
) -> None:
    """JSONL形式で監査イベントを追記"""
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        session_id = _generate_session_id()
        st.session_state.session_id = session_id

    event: Dict[str, Any] = {
        "timestamp": now_iso(),
        "event_type": event_type,
        "session_id": session_id,
        "analyst_name": get_analyst_name(),
        "analysis_type": st.session_state.get("analysis_type", "MNV"),
    }
    if payload:
        event.update(payload)

    try:
        log_path = _get_log_file_path(force_session=force_session)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # ログ失敗で解析を止めない
        pass


# ============================================================================
# 入力画像リサイズ（幅1024ピクセルに正規化）
# ============================================================================
TARGET_IMAGE_WIDTH = 1024


def _resize_image_to_width(
    image: np.ndarray, target_width: int = TARGET_IMAGE_WIDTH
) -> np.ndarray:
    """
    Resize image to target width preserving aspect ratio.

    Uses INTER_CUBIC for upscaling, INTER_AREA for downscaling.

    Parameters
    ----------
    image : np.ndarray
        Grayscale image (H, W) or RGB (H, W, 3).
    target_width : int
        Target width in pixels.

    Returns
    -------
    np.ndarray
        Resized image.
    """
    h, w = image.shape[:2]
    if w == target_width:
        return image.copy()

    scale = target_width / w
    new_w = target_width
    new_h = int(round(h * scale))

    if scale > 1.0:
        interp = cv2.INTER_CUBIC
    else:
        interp = cv2.INTER_AREA

    return cv2.resize(image, (new_w, new_h), interpolation=interp)


def _resize_roi_mask_to_match(
    roi_mask: np.ndarray, new_shape: Tuple[int, int]
) -> np.ndarray:
    """Resize ROI mask to match image shape. Uses INTER_NEAREST."""
    return cv2.resize(
        roi_mask, (new_shape[1], new_shape[0]), interpolation=cv2.INTER_NEAREST
    )


# ============================================================================
# MNV解析実行
# ============================================================================
def run_mnv_analysis(
    filename: str,
    image_bytes: bytes,
    roi_mask: np.ndarray,
    scale_mm: float = 6.0,
    flow_deficit_image_path: Optional[str] = None,
) -> bool:
    """
    Core MNV Pipelineで解析を実行（ユーザー描画ROI使用）

    Parameters
    ----------
    filename : str
        画像ファイル名
    image_bytes : bytes
        画像データ
    roi_mask : np.ndarray
        ROIマスク
    scale_mm : float
        画像の実寸法（mm）
    flow_deficit_image_path : Optional[str]
        Flow Deficit用画像パス（Folder Batchモードで4.*画像が見つかった場合）

    Returns
    -------
    bool
        成功時True
    """
    started_at = now_iso()
    start_epoch = time.time()

    try:
        file_stem = Path(filename).stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 画像を読み込み
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image_array = np.array(pil_image)
        original_width = image_array.shape[1]

        # 解像度に応じたリサイズ判定（閾値は core.mnv_pipeline.SMALL_IMAGE_THRESHOLD と共通）:
        # 幅 >= 閾値: 1024px にリサイズ（従来動作）。幅 < 閾値: リサイズせず元解像度で処理。
        if original_width >= SMALL_IMAGE_THRESHOLD:
            resized_image = _resize_image_to_width(image_array, TARGET_IMAGE_WIDTH)
            resized_roi = _resize_roi_mask_to_match(
                roi_mask, resized_image.shape[:2]
            )
        else:
            # 小画像: リサイズせず元の解像度で処理
            resized_image = image_array.copy()
            # ROI マスクのサイズが画像と一致しない場合のみリサイズ
            if roi_mask.shape[:2] != image_array.shape[:2]:
                resized_roi = _resize_roi_mask_to_match(
                    roi_mask, image_array.shape[:2]
                )
            else:
                resized_roi = roi_mask.copy()

        with tempfile.TemporaryDirectory(prefix=f"mnv_{file_stem}_{ts}_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            # リサイズ後の画像を保存（pipelineはimage_pathを要求）
            ext = Path(filename).suffix or ".tif"
            image_path = tmp_path / f"input_image{ext}"
            cv2.imwrite(str(image_path), resized_image)

            if not HAS_MNV_PIPELINE or CoreMNVPipeline is None:
                # フォールバック: 簡易メトリクスのみ（リサイズ後の画像を使用）
                w = resized_image.shape[1]
                mm_per_pixel_sq = (scale_mm / w) ** 2
                roi_pixels = resized_roi.sum() / 255
                results = {
                    "mnv_area_mm2": roi_pixels * mm_per_pixel_sq,
                    "vessel_density": 0.0,
                    "mnv_subtype": "Unknown (pipeline unavailable)",
                }
            else:
                pipeline = CoreMNVPipeline(
                    scale_mm=scale_mm,
                    save_stages=False,
                    verbose=False,
                    enable_roi_refinement=True,
                )
                results = pipeline.analyze(
                    image_path=str(image_path),
                    output_dir=str(tmp_path),
                    flow_deficit_image_path=flow_deficit_image_path,
                    roi_mask=resized_roi,
                )

        # per_file_resultsに格納（QC画面用: リサイズ後の画像・ROIで解析済み）
        st.session_state.per_file_results[filename] = {
            "type": "MNV",
            "metrics": results,
            "roi_mask": resized_roi,
            "output_dir": "",
            "success": True,
        }
        ended_at = now_iso()
        duration_sec = round(max(time.time() - start_epoch, 0.0), 3)
        log_event(
            "file_process_result",
            {
                "pipeline": "MNV",
                "filename": filename,
                "status": "ok",
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
            },
            force_session=True,
        )
        return True

    except Exception as e:
        st.session_state.per_file_results[filename] = {
            "type": "MNV",
            "success": False,
            "error": str(e),
            "roi_mask": roi_mask,
        }
        ended_at = now_iso()
        duration_sec = round(max(time.time() - start_epoch, 0.0), 3)
        log_event(
            "file_process_result",
            {
                "pipeline": "MNV",
                "filename": filename,
                "status": "failed",
                "error": str(e),
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
            },
            force_session=True,
        )
        st.error(f"解析エラー: {e}")
        return False


# ============================================================================
# VD解析実行（バッチ）
# ============================================================================
def run_vd_batch(
    file_queue: list,
    scale_mm: float,
    vd_side: str = "right",
    sup_suffix: str = "1.tif",
    deep_suffix: str = "2.tif",
    save_stages: bool = False,
    analyst_name: str = "Python Streamlit Analysis",
    vd_use_intref: bool = False,
    vd_intref_percentile: float = 40.0,
    vd_intref_center_ratio: float = 0.5,
    single_image_mode: bool = False,
) -> bool:
    """
    VD解析をバッチ実行（全ファイルをinput_dirに配置してVDAnalyzer実行）

    Parameters
    ----------
    single_image_mode : bool
        True: File Upload用。各画像を単体でFAZ同定→VD解析（ペア不要）

    Returns
    -------
    bool
        成功時True
    """
    if not HAS_VD_ANALYZER or VDAnalyzer is None:
        st.error("VD Analyzer is not available.")
        return False

    started_at = now_iso()
    start_epoch = time.time()

    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.vd_visualizations = {}
        vd_vis_by_file: Dict[str, Dict[str, Any]] = {}

        with tempfile.TemporaryDirectory(prefix=f"vd_batch_{ts}_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_dir = tmp_path / "input"
            output_dir = tmp_path / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            # 全ファイルをinputに保存
            for f in file_queue:
                name = f["name"]
                data = f.get("bytes", b"")
                if not data:
                    continue
                p = input_dir / name
                with open(p, "wb") as out:
                    out.write(data)

            vd_analyzer = VDAnalyzer(
                input_dir=str(input_dir),
                output_dir=str(output_dir),
                scale_mm=scale_mm,
                side=vd_side,
                sup_suffix=sup_suffix,
                deep_suffix=deep_suffix,
                save_stages=save_stages,
                analyst_name=analyst_name,
                # Keep tuned preprocessing explicit for reproducibility.
                faz_li_threshold_scale=0.07,
                use_optimized_preprocessing=True,
                # Baseline by default; enable intref only when requested.
                use_faz_intensity_refinement=vd_use_intref,
                faz_intensity_percentile=vd_intref_percentile,
                faz_center_roi_ratio=vd_intref_center_ratio,
                # FAZ boundary regularization: keep explicit for reproducibility
                # even if VDAnalyzer defaults change later.
                faz_distance_trim_ratio=0.14,
                faz_distance_min_px=1,
                single_image_mode=single_image_mode,
            )

            vd_results = vd_analyzer.analyze()
            superficial_files = vd_results.get("superficial_files", [])
            patient_ids = vd_results.get("patient_ids", [])
            for i, sf in enumerate(superficial_files):
                pid = (
                    str(patient_ids[i])
                    if i < len(patient_ids) and patient_ids[i] is not None
                    else extract_patient_id_from_filename(sf)
                )
                sup_img = output_dir / f"{pid}_superficial_visualization.png"
                deep_img = output_dir / f"{pid}_deep_visualization.png"
                vis_payload: Dict[str, Any] = {"patient_id": pid}
                if sup_img.exists():
                    vis_payload["superficial"] = sup_img.read_bytes()
                if deep_img.exists():
                    vis_payload["deep"] = deep_img.read_bytes()
                vd_vis_by_file[sf] = vis_payload

        if not superficial_files:
            st.warning(
                "画像が見つかりません。"
                if single_image_mode
                else "ペアが見つかりません。サフィックスを確認してください。"
            )
            ended_at = now_iso()
            duration_sec = round(max(time.time() - start_epoch, 0.0), 3)
            log_event(
                "analysis_error",
                {
                    "pipeline": "VD",
                    "status": "no_pairs",
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_sec": duration_sec,
                },
                force_session=True,
            )
            return False

        # per_file_results に各患者の結果を格納（superficial filename をキーに）
        for i, sf in enumerate(superficial_files):
            st.session_state.vd_visualizations[sf] = vd_vis_by_file.get(
                sf, {"patient_id": extract_patient_id_from_filename(sf)}
            )

            st.session_state.per_file_results[sf] = {
                "type": "VD",
                "metrics": vd_results,
                "success": True,
            }
            st.session_state.qc_status[sf] = "pending"

        # VD用の表示順リスト（superficial files）。コピーを保存して参照の不整合を防ぐ
        vd_list = list(superficial_files)
        st.session_state.vd_file_list = vd_list
        st.session_state.vd_file_count = len(vd_list)  # 件数は別保持（session_stateのリスト永続化不具合対策）
        st.session_state.vd_results = vd_results
        ended_at = now_iso()
        duration_sec = round(max(time.time() - start_epoch, 0.0), 3)
        for sf in superficial_files:
            log_event(
                "file_process_result",
                {
                    "pipeline": "VD",
                    "filename": sf,
                    "status": "ok",
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_sec": duration_sec,
                },
                force_session=True,
            )
        log_event(
            "vd_batch_completed",
            {
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
                "pair_count": len(superficial_files),
            },
            force_session=True,
        )
        return True

    except Exception as e:
        ended_at = now_iso()
        duration_sec = round(max(time.time() - start_epoch, 0.0), 3)
        log_event(
            "analysis_error",
            {
                "pipeline": "VD",
                "status": "failed",
                "error": str(e),
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
            },
            force_session=True,
        )
        st.error(f"VD解析エラー: {e}")
        return False


# ============================================================================
# MNV全メトリクスCSV出力（ImageJ createMeasurementsTable形式互換）
# ============================================================================

# MNV結果CSV・結果テーブルの列順（指定順）
IMAGEJ_CSV_COLUMNS = [
    "ID",
    "File",
    "Subtype",
    "Pathophysiology",
    "Maturity Index",
    "Caliber Uniformity Score",
    "Network Complexity Score",
    "MNV Area (mm2)",
    "Vsl Area (mm2)",
    "Vsl Density (Vessel Area/MNV (%))",
    "Vessel density index adjusted by signal intensity (aVDI)",
    "MNV Area adjusted by signal intensity (aMNV)",
    "Vsl Length (mm)",
    "Junction Density (n/mm)",
    "End Pts Density (n/mm)",
    "Multi-Branch Pts Density (n/mm)",
    "Branch Density (n/mm)",
    "Dilated vessel (%)",
    "Arteriolarization Segment Count",
    "Arteriolarization Total Length (mm)",
    "Arteriolarization Max Segment Length (mm)",
    "Arteriolarization Density (/mm²)",
    "Arteriolarization Connectivity Index (mm/segment)",
    "Local Diameter Variation (max CV%)",
    "Center Branches",
    "Center Total Length (mm)",
    "Center Tortuosity",
    "Center FD (Box-Counting)",
    "Center Euler Number",
    "Center Loop Number",
    "Periphery Branches",
    "Periphery Total Length (mm)",
    "Periphery Tortuosity",
    "Periphery FD (Box-Counting)",
    "Periphery Euler Number",
    "Periphery Loop Number",
    "MNV mean gray intensity (AU)",
    "Fractal Dim",
    "Tortuosity",
    "MNV intensity Variation (CV)",
    "NV Diameter (CV)",
    "(Skel) Vsl Diameter",
    "End Pts",
    "Vsl Branches",
    "Vsl Junctions",
    "Triple Pts",
    "Quadruple Pts",
    "Raw Vsl Length",
    "Raw Vsl Diameter",
    "Quality of analysis",
    "FD% (R1)",
    "FD Avg Area µm² (R1)",
    "FD number (R1)",
    "FD density /mm² (R1)",
    "FD% (R2)",
    "FD Avg Area µm² (R2)",
    "FD number (R2)",
    "FD density /mm² (R2)",
    "FD% (R3)",
    "FD Avg Area µm² (R3)",
    "FD number (R3)",
    "FD density /mm² (R3)",
    "FD quality flag (0=OK 1=abnormal)",
    "Exclude from FD analysis",
    "FD quality reason",
    "ROI coverage (%)",
    "ROI coverage low quality (0=OK 1=low)",
    "FD box sizes",
    "N FD box sizes",
    "FD scale insufficient (0=OK 1=insufficient)",
]

# FD関連13列（行除外は現在行わず全行出力するため未使用・参照用）
FD_ZERO_EXCLUDE_COLUMNS = [
    "FD% (R1)",
    "FD Avg Area µm² (R1)",
    "FD number (R1)",
    "FD density /mm² (R1)",
    "FD% (R2)",
    "FD Avg Area µm² (R2)",
    "FD number (R2)",
    "FD density /mm² (R2)",
    "FD% (R3)",
    "FD Avg Area µm² (R3)",
    "FD number (R3)",
    "FD density /mm² (R3)",
    "FD quality flag (0=OK 1=abnormal)",
]

MNV_EXPORT_META_COLUMNS = [
    "Analyst",
    "Started At",
    "Ended At",
    "Duration Sec",
    "Session ID",
]

# Pipeline metrics key -> ImageJ column マッピング
# Note: total_length_mm = arteriolarization (high skew) total length only.
#       vessel_length_mm = full skeleton length (Vsl Length / Raw Vsl Length).
_PIPELINE_TO_IMAGEJ = {
    "mnv_subtype": "Subtype",
    "pathophysiology": "Pathophysiology",
    "mnv_area_mm2": "MNV Area (mm2)",
    "vessel_area_mm2": "Vsl Area (mm2)",
    "vessel_density": "Vsl Density (Vessel Area/MNV (%))",
    "vessel_length_mm": "Vsl Length (mm)",
    "high_skew_percentage": "Dilated vessel (%)",
    "maturity_index": "Maturity Index",
    "stability_score": "Caliber Uniformity Score",
    "complexity_score": "Network Complexity Score",
    "junction_density": "Junction Density (n/mm)",
    "endpoint_density": "End Pts Density (n/mm)",
    "multiple_density": "Multi-Branch Pts Density (n/mm)",
    "branch_density": "Branch Density (n/mm)",
    "segment_count": "Arteriolarization Segment Count",
    "total_length_mm": "Arteriolarization Total Length (mm)",
    "max_segment_length_mm": "Arteriolarization Max Segment Length (mm)",
    "density": "Arteriolarization Density (/mm²)",
    "connectivity_index": "Arteriolarization Connectivity Index (mm/segment)",
    "localized_diameter_variation": "Local Diameter Variation (max CV%)",
    "center_branch_count": "Center Branches",
    "vessel_length_center": "Center Total Length (mm)",
    "tortuosity_center": "Center Tortuosity",
    "fractal_dimension_center": "Center FD (Box-Counting)",
    "euler_center": "Center Euler Number",
    "loop_center": "Center Loop Number",
    "periphery_branch_count": "Periphery Branches",
    "vessel_length_periphery": "Periphery Total Length (mm)",
    "tortuosity_periphery": "Periphery Tortuosity",
    "fractal_dimension_periphery": "Periphery FD (Box-Counting)",
    "euler_periphery": "Periphery Euler Number",
    "loop_periphery": "Periphery Loop Number",
    "mean_intensity": "MNV mean gray intensity (AU)",
    "fractal_dimension": "Fractal Dim",
    "tortuosity": "Tortuosity",
    "standard_deviation": "MNV intensity Variation (CV)",
    "cv_diameter": "NV Diameter (CV)",
    "mean_diameter_um": "(Skel) Vsl Diameter",
    "num_endpoints": "End Pts",
    "num_branches": "Vsl Branches",
    "num_junctions": "Vsl Junctions",
    "num_triple_points": "Triple Pts",
    "num_quadruple_points": "Quadruple Pts",
    "FD_percent_R1": "FD% (R1)",
    "FD_average_area_R1": "FD Avg Area µm² (R1)",
    "FD_number_R1": "FD number (R1)",
    "FD_density_R1": "FD density /mm² (R1)",
    "FD_percent_R2": "FD% (R2)",
    "FD_average_area_R2": "FD Avg Area µm² (R2)",
    "FD_number_R2": "FD number (R2)",
    "FD_density_R2": "FD density /mm² (R2)",
    "FD_percent_R3": "FD% (R3)",
    "FD_average_area_R3": "FD Avg Area µm² (R3)",
    "FD_number_R3": "FD number (R3)",
    "FD_density_R3": "FD density /mm² (R3)",
}


def _metrics_to_imagej_row(
    filename: str, idx: int, qc_status: str, success: bool, metrics: dict
) -> dict:
    """
    Core Pipeline metricsをImageJ形式の行に変換

    ImageJ互換（ARIAKE_OCTA_color_code_J.ijm.original）:
    - vessel_density: ratio (vessel_Areas/MNV_Areas)、CSVにはそのまま出力
    - mean_intensity: MNVmean/MNVmax（ROI内の正規化平均）
    - aVDI = vessel_density * mean_intensity * 100
    - aMNV = (1 - aVDI/100) * vessel_area_mm2
    """
    row = {col: "" for col in IMAGEJ_CSV_COLUMNS}
    row["ID"] = str(idx + 1)
    row["File"] = filename
    row["Subtype"] = metrics.get("mnv_subtype", "")
    row["Quality of analysis"] = qc_status if success else "Error"

    # 直接マッピング
    # numpy スカラー (np.int64 等) も許容: isinstance(val, int) が False になるため
    def _to_csv_value(val):
        if val is None:
            return None
        if isinstance(val, str):
            return val
        try:
            import numpy as np

            if isinstance(val, np.integer):
                return int(val)
            if isinstance(val, np.floating):
                return float(val)
        except ImportError:
            pass
        if isinstance(val, (int, float)):
            return val
        return None

    for pk, ij_col in _PIPELINE_TO_IMAGEJ.items():
        if pk in metrics and ij_col in row:
            csv_val = _to_csv_value(metrics[pk])
            if csv_val is not None:
                row[ij_col] = csv_val

    # Vsl Length (mm): Corrected優先 / Raw Vsl Length: 常にRaw（ImageJ互換）
    corrected_len = metrics.get("corrected_vessel_length_mm")
    vlen = metrics.get("vessel_length_mm")
    if corrected_len is not None and isinstance(corrected_len, (int, float)):
        row["Vsl Length (mm)"] = corrected_len
    elif vlen is not None and isinstance(vlen, (int, float)):
        row["Vsl Length (mm)"] = vlen
    if vlen is not None and isinstance(vlen, (int, float)):
        row["Raw Vsl Length"] = vlen

    # 派生メトリクス (ImageJ createVisualizationRGB 4208-4212行)
    # vessel_density: ratio (vessel_Areas/MNV_Areas), mean_intensity: MNVmean/MNVmax
    # aVDI = vessel_densities * mean_intensity * 100
    # aMNV = (1 - vessel_density_index/100) * vessel_Areas
    vd = metrics.get("vessel_density")
    mi = metrics.get("mean_intensity")
    va = metrics.get("vessel_area_mm2")
    if vd is not None and mi is not None:
        try:
            vd_val = float(vd)  # ratio 0-1
            mi_val = float(mi)  # MNVmean/MNVmax
            vdi = vd_val * mi_val * 100  # ImageJ式
            row["Vessel density index adjusted by signal intensity (aVDI)"] = vdi
            if va is not None:
                try:
                    va_val = float(va)
                    imv = (1 - vdi / 100) * va_val  # ImageJ式
                    row["MNV Area adjusted by signal intensity (aMNV)"] = imv
                except (TypeError, ValueError):
                    pass
        except (TypeError, ValueError):
            pass

    # Raw Vsl Diameter: 1000 * vessel_area_mm2 / vessel_length_mm (ImageJ式)
    if va is not None and vlen is not None and vlen > 0:
        try:
            raw_dia = 1000 * float(va) / float(vlen)
            row["Raw Vsl Diameter"] = raw_dia
        except (TypeError, ValueError):
            pass

    # Center/Periphery FD from classification_results (Step 6 refined_skeleton)
    if "fractal_dimension_center" in metrics:
        row["Center FD (Box-Counting)"] = metrics.get("fractal_dimension_center")
    if "fractal_dimension_periphery" in metrics:
        row["Periphery FD (Box-Counting)"] = metrics.get("fractal_dimension_periphery")

    # num_loops/euler_numberの簡易Center/Periphery分割（Pipelineが個別を持たない場合）
    num_loops = metrics.get("num_loops")
    euler_number = metrics.get("euler_number")
    if num_loops is not None and row["Center Loop Number"] == "":
        row["Center Loop Number"] = num_loops // 2
        row["Periphery Loop Number"] = num_loops - (num_loops // 2)
    if euler_number is not None and row["Center Euler Number"] == "":
        row["Center Euler Number"] = euler_number // 2
        row["Periphery Euler Number"] = euler_number - (euler_number // 2)

    # Phase1/2/3 品質フラグ（0/False もそのまま出力するため None の場合のみ ""）
    def _csv_val(val):
        v = _to_csv_value(val)
        return v if v is not None else ""

    if "fd_quality_flag" in metrics:
        row["FD quality flag (0=OK 1=abnormal)"] = _csv_val(metrics["fd_quality_flag"])
    if "exclude_from_fd_analysis" in metrics:
        row["Exclude from FD analysis"] = _csv_val(
            metrics["exclude_from_fd_analysis"]
        )
    if "fd_quality_reason" in metrics:
        row["FD quality reason"] = str(metrics["fd_quality_reason"])
    if "roi_coverage" in metrics:
        row["ROI coverage (%)"] = _csv_val(metrics["roi_coverage"])
    if "roi_coverage_low_quality" in metrics:
        row["ROI coverage low quality (0=OK 1=low)"] = _csv_val(
            metrics["roi_coverage_low_quality"]
        )
    if "fd_box_sizes" in metrics:
        row["FD box sizes"] = str(metrics["fd_box_sizes"])
    if "n_fd_box_sizes" in metrics:
        row["N FD box sizes"] = _csv_val(metrics["n_fd_box_sizes"])
    if "fd_scale_insufficient" in metrics:
        row["FD scale insufficient (0=OK 1=insufficient)"] = _csv_val(
            metrics["fd_scale_insufficient"]
        )

    return row


def _is_fd_row_all_zero(row: dict) -> bool:
    """
    FD_ZERO_EXCLUDE_COLUMNSの13列がすべて明示的に0または"0"ならTrue。
    現在は行除外に使っておらず全行出力のため未使用（将来のオプション用）。
    """
    for col in FD_ZERO_EXCLUDE_COLUMNS:
        v = row.get(col, "")
        if v is None or v == "":
            return False
        try:
            if float(v) != 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def export_mnv_results_to_csv() -> tuple:
    """
    per_file_resultsからMNV全メトリクスをImageJ形式CSVで出力。
    解析した全ファイル分の行を出力する（行の除外は行わない）。

    Returns
    -------
    tuple[Optional[bytes], str]
        (CSVバイト列, 推奨ファイル名)。解析対象が0件の場合は (None, "").
    """
    qc_status = st.session_state.get("qc_status", {})
    per_file_results = st.session_state.get("per_file_results", {})
    file_queue = st.session_state.get("file_queue", [])
    names_from_queue = set()
    for f in file_queue:
        n = f.get("name") if isinstance(f, dict) else (f if isinstance(f, str) else None)
        if n:
            names_from_queue.add(str(n))
    all_filenames = set(qc_status.keys()) | names_from_queue
    rows = []
    for idx, filename in enumerate(sorted(all_filenames)):
        res = per_file_results.get(filename, {})
        success = res.get("success", False)
        metrics = res.get("metrics", {})
        row = _metrics_to_imagej_row(
            filename=filename,
            idx=idx,
            qc_status=qc_status.get(filename, "unknown"),
            success=success,
            metrics=metrics,
        )
        rows.append(row)

    # 解析した全行を出力する（FDの13列がすべて0でも行は除外しない）。
    # 0件になるのは解析対象ファイルが存在しない場合のみ。
    if not rows:
        return None, ""

    export_columns = IMAGEJ_CSV_COLUMNS + MNV_EXPORT_META_COLUMNS
    meta = get_analysis_metadata()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=export_columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        row_out = {k: row.get(k, "") for k in IMAGEJ_CSV_COLUMNS}
        row_out.update(meta)
        writer.writerow({k: row_out.get(k, "") for k in export_columns})

    # セッションIDを使用してタイムスタンプを統一（フォルダー名と一致させる）
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_suffix = ts
    else:
        # セッションIDからタイムスタンプ部分を抽出（形式: YYYYMMDD_HHMMSS_xxxxx）
        parts = session_id.split("_")
        if len(parts) >= 2:
            timestamp_suffix = f"{parts[0]}_{parts[1]}"
        else:
            timestamp_suffix = session_id
    
    # Patient IDを含むファイル名を生成（共通prefixを使用）
    patient_ids = set()
    if all_filenames:
        # 共通prefixを抽出
        common_prefix = extract_common_prefix_from_filenames(list(all_filenames))
        if common_prefix:
            # 共通prefixが見つかった場合、それを患者IDとして使用
            patient_ids.add(common_prefix)
        else:
            # 共通prefixが見つからない場合、各ファイルから個別に抽出
            for filename in all_filenames:
                patient_id = extract_patient_id_from_filename(filename, list(all_filenames))
                patient_ids.add(patient_id)
    
    if len(patient_ids) == 1:
        # 単一患者の場合
        patient_id = list(patient_ids)[0]
        safe_patient_id = re.sub(r'[<>:"/\\|?*]', '_', patient_id)
        suggested_name = f"MNV_{safe_patient_id}_{timestamp_suffix}.csv"
    else:
        # 複数患者の場合
        suggested_name = f"MNV_batch_{timestamp_suffix}.csv"
    
    return buf.getvalue().encode("utf-8-sig"), suggested_name


def build_vd_results_csv() -> tuple[Optional[bytes], Optional[str]]:
    """VD結果CSVを構築"""
    vd_results = st.session_state.get("vd_results")
    if not (vd_results and vd_results.get("patient_ids")):
        return None, None

    vd_df = pd.DataFrame(
        {
            "Patient ID": vd_results.get("patient_ids", []),
            "Superficial Image ID": vd_results.get("superficial_files", []),
            "Deep Image ID": vd_results.get("deep_files", []),
            "FAZ (mm^2)": vd_results.get("faz_areas", []),
            "Circularity": vd_results.get("faz_circularities", []),
            "Superficial": vd_results.get("superficial_whole", []),
            "Superior Area (Superficial)": vd_results.get("superficial_superior", []),
            "Temporal Area (Superficial)": vd_results.get("superficial_temporal", []),
            "Nasal Area (Superficial)": vd_results.get("superficial_nasal", []),
            "Inferior Area (Superficial)": vd_results.get("superficial_inferior", []),
            "Deep": vd_results.get("deep_whole", []),
            "Superior Area (Deep)": vd_results.get("deep_superior", []),
            "Temporal Area (Deep)": vd_results.get("deep_temporal", []),
            "Nasal Area (Deep)": vd_results.get("deep_nasal", []),
            "Inferior Area (Deep)": vd_results.get("deep_inferior", []),
            "Fractal Dimension (Superficial)": vd_results.get(
                "fractal_dimension_superficial", []
            ),
            "Fractal Dimension (Deep)": vd_results.get(
                "fractal_dimension_deep", []
            ),
            "Tortuosity (Superficial)": vd_results.get(
                "tortuosity_superficial", []
            ),
            "Tortuosity (Deep)": vd_results.get("tortuosity_deep", []),
        }
    )
    vd_meta = get_analysis_metadata()
    vd_df["Analyst"] = vd_meta["Analyst"]
    vd_df["Started At"] = vd_meta["Started At"]
    vd_df["Ended At"] = vd_meta["Ended At"]
    vd_df["Duration Sec"] = vd_meta["Duration Sec"]
    vd_df["Session ID"] = vd_meta["Session ID"]

    vd_csv = vd_df.to_csv(index=False).encode("utf-8-sig")
    
    # セッションIDを使用してタイムスタンプを統一（フォルダー名と一致させる）
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_suffix = ts
    else:
        # セッションIDからタイムスタンプ部分を抽出（形式: YYYYMMDD_HHMMSS_xxxxx）
        parts = session_id.split("_")
        if len(parts) >= 2:
            timestamp_suffix = f"{parts[0]}_{parts[1]}"
        else:
            timestamp_suffix = session_id
    
    # Patient IDを含むファイル名を生成
    patient_ids = vd_results.get("patient_ids", [])
    unique_patient_ids = set([pid for pid in patient_ids if pid])
    
    if len(unique_patient_ids) == 1:
        # 単一患者の場合
        patient_id = list(unique_patient_ids)[0]
        safe_patient_id = re.sub(r'[<>:"/\\|?*]', '_', str(patient_id))
        return vd_csv, f"VD_{safe_patient_id}_{timestamp_suffix}.csv"
    else:
        # 複数患者の場合
        return vd_csv, f"VD_batch_{timestamp_suffix}.csv"


STABILITY_CSV_COLUMNS = [
    "File",
    "size_class",
    "stab_cv",
    "stab_mean_adjacent_change",
    "stab_residual_cv",
    "stab_range_percent",
]


def build_stability_csv() -> Tuple[Optional[bytes], str]:
    """
    Stability関連4指標のCSVを構築（MNV解析済みファイルのみ）。
    per_file_results から size_class と radial_profile を取得し、
    stab_cv, stab_mean_adjacent_change, stab_residual_cv, stab_range_percent を算出して出力。

    Returns
    -------
    tuple[Optional[bytes], str]
        (CSVバイト列, 推奨ファイル名)。対象0件の場合は (None, "").
    """
    if not HAS_STABILITY_RAW or _compute_stability_raw is None:
        return None, ""
    qc_status = st.session_state.get("qc_status", {})
    per_file_results = st.session_state.get("per_file_results", {})
    file_queue = st.session_state.get("file_queue", [])
    names_from_queue = set()
    for f in file_queue:
        n = f.get("name") if isinstance(f, dict) else (f if isinstance(f, str) else None)
        if n:
            names_from_queue.add(str(n))
    all_filenames = sorted(set(qc_status.keys()) | names_from_queue)
    rows = []
    for filename in all_filenames:
        res = per_file_results.get(filename, {})
        if (res.get("type") != "MNV") or not res.get("success", False):
            continue
        metrics = res.get("metrics", {})
        size_class = metrics.get("size_class", "")
        radial_profile = metrics.get("radial_profile")
        diameters = None
        if isinstance(radial_profile, dict):
            diameters = radial_profile.get("diameters")
        if diameters is not None:
            diameters = np.asarray(diameters, dtype=float)
        if diameters is None or (hasattr(diameters, "size") and diameters.size == 0):
            row = {
                "File": filename,
                "size_class": size_class,
                "stab_cv": "",
                "stab_mean_adjacent_change": "",
                "stab_residual_cv": "",
                "stab_range_percent": "",
            }
        else:
            raw = _compute_stability_raw(diameters)
            row = {
                "File": filename,
                "size_class": size_class,
                "stab_cv": raw.get("cv", ""),
                "stab_mean_adjacent_change": raw.get("mean_adjacent_change", ""),
                "stab_residual_cv": raw.get("residual_cv", ""),
                "stab_range_percent": raw.get("range_percent", ""),
            }
        rows.append(row)
    if not rows:
        return None, ""
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_suffix = ts
    else:
        parts = session_id.split("_")
        timestamp_suffix = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else session_id
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=STABILITY_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in STABILITY_CSV_COLUMNS})
    suggested_name = f"Stability_{timestamp_suffix}.csv"
    return buf.getvalue().encode("utf-8-sig"), suggested_name


def save_mnv_rgb_images(export_root: Path, file_list: list[str]) -> list[str]:
    """MNV結果のRGB画像を保存"""
    saved_paths: list[str] = []
    rgb_dir = export_root / "MNV_RGB"
    rgb_dir.mkdir(parents=True, exist_ok=True)
    per_file_results = st.session_state.get("per_file_results", {})

    for filename in file_list:
        res = per_file_results.get(filename, {})
        if res.get("type") != "MNV":
            continue
        # ファイルリスト全体から共通prefixを抽出して使用
        patient_id = extract_patient_id_from_filename(filename, file_list)
        patient_dir = rgb_dir / patient_id
        patient_dir.mkdir(parents=True, exist_ok=True)
        metrics = res.get("metrics", {}) or {}
        rgb = metrics.get("rgb")
        if not isinstance(rgb, np.ndarray):
            continue

        arr = rgb
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        if arr.ndim == 3 and arr.shape[2] > 3:
            arr = arr[:, :, :3]
        if arr.ndim not in (2, 3):
            continue

        out_path = patient_dir / f"{Path(filename).stem}_MNV_RGB.png"
        try:
            Image.fromarray(arr).save(out_path)
            saved_paths.append(str(out_path))
        except Exception:
            continue

    return saved_paths


def save_vd_visualization_images(export_root: Path) -> list[str]:
    """VD可視化画像を保存"""
    saved_paths: list[str] = []
    vis_dir = export_root / "VD_visualization"
    vis_dir.mkdir(parents=True, exist_ok=True)
    vd_visualizations = st.session_state.get("vd_visualizations", {}) or {}

    for filename, payload in vd_visualizations.items():
        if not isinstance(payload, dict):
            continue
        patient_id = str(payload.get("patient_id") or extract_patient_id_from_filename(filename))
        patient_dir = vis_dir / patient_id
        patient_dir.mkdir(parents=True, exist_ok=True)

        superficial = payload.get("superficial")
        if isinstance(superficial, (bytes, bytearray)):
            sup_out = patient_dir / f"{patient_id}_superficial_visualization.png"
            sup_out.write_bytes(bytes(superficial))
            saved_paths.append(str(sup_out))

        deep = payload.get("deep")
        if isinstance(deep, (bytes, bytearray)):
            deep_out = patient_dir / f"{patient_id}_deep_visualization.png"
            deep_out.write_bytes(bytes(deep))
            saved_paths.append(str(deep_out))

    return saved_paths


def export_log_variants(export_root: Path) -> list[str]:
    """events.jsonl から csv/txt を生成"""
    saved_paths: list[str] = []
    logs_dir = export_root / "logs"
    jsonl_path = logs_dir / "events.jsonl"
    if not jsonl_path.exists():
        return saved_paths

    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    events: list[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not events:
        return saved_paths

    csv_columns = sorted({k for ev in events for k in ev.keys()})
    csv_path = logs_dir / "events.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        for ev in events:
            writer.writerow(ev)
    saved_paths.append(str(csv_path))

    txt_path = logs_dir / "events.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for ev in events:
            ts = ev.get("timestamp", "")
            et = ev.get("event_type", "")
            analyst = ev.get("analyst_name", "")
            f.write(f"[{ts}] {et} (analyst={analyst})\n")
    saved_paths.append(str(txt_path))
    return saved_paths


def build_mnv_rgb_zip_bytes(file_list: list[str]) -> Tuple[Optional[bytes], str]:
    """
    MNV結果のRGB画像をメモリ上でZIPにまとめる（File Upload用ダウンロード）

    Returns
    -------
    tuple[Optional[bytes], str]
        (ZIPバイト列, 推奨ファイル名)。画像が1枚もない場合は (None, "").
    """
    per_file_results = st.session_state.get("per_file_results", {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        count = 0
        for filename in file_list:
            res = per_file_results.get(filename, {})
            if res.get("type") != "MNV":
                continue
            metrics = res.get("metrics", {}) or {}
            rgb = metrics.get("rgb")
            if not isinstance(rgb, np.ndarray):
                continue
            arr = rgb
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.ndim == 3 and arr.shape[2] > 3:
                arr = arr[:, :, :3]
            if arr.ndim not in (2, 3):
                continue
            png_buf = io.BytesIO()
            Image.fromarray(arr).save(png_buf, format="PNG")
            png_buf.seek(0)
            name_in_zip = f"{Path(filename).stem}_MNV_RGB.png"
            zf.writestr(name_in_zip, png_buf.read())
            count += 1
    if count == 0:
        return None, ""
    buf.seek(0)
    session_id = st.session_state.get("session_id", "")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S") if not session_id else session_id.replace(":", "").replace("-", "")[:15]
    return buf.getvalue(), f"MNV_RGB_{ts}.zip"


def get_log_download_bytes() -> Tuple[Optional[bytes], Optional[bytes], Optional[bytes], str]:
    """
    現在セッションのログを読み、JSONL/CSV/TXTのバイト列を返す（File Upload用ダウンロード）

    Returns
    -------
    tuple[jsonl_bytes, csv_bytes, txt_bytes, base_name]
        base_name は推奨ファイル名のプレフィックス（拡張子なし）
    """
    persistent = st.session_state.get("persistent_output_dir")
    if not persistent:
        return None, None, None, ""
    logs_dir = Path(persistent) / "exports" / "logs"
    jsonl_path = logs_dir / "events.jsonl"
    if not jsonl_path.exists():
        return None, None, None, ""
    try:
        jsonl_bytes = jsonl_path.read_bytes()
    except Exception:
        return None, None, None, ""
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    events: list[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not events:
        return jsonl_bytes, None, None, "events"
    csv_columns = sorted({k for ev in events for k in ev.keys()})
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=csv_columns, extrasaction="ignore")
    writer.writeheader()
    for ev in events:
        writer.writerow(ev)
    csv_bytes = csv_buf.getvalue().encode("utf-8-sig")
    txt_buf = io.StringIO()
    for ev in events:
        ts = ev.get("timestamp", "")
        et = ev.get("event_type", "")
        analyst = ev.get("analyst_name", "")
        txt_buf.write(f"[{ts}] {et} (analyst={analyst})\n")
    txt_bytes = txt_buf.getvalue().encode("utf-8")
    session_id = st.session_state.get("session_id", "")
    base = f"events_{session_id}" if session_id else "events"
    return jsonl_bytes, csv_bytes, txt_bytes, base


def build_vd_visualization_zip_bytes() -> Tuple[Optional[bytes], str]:
    """
    VD可視化画像をメモリ上でZIPにまとめる（File Upload用ダウンロード）
    vd_visualizations の構造は save_vd_visualization_images と同一。

    Returns
    -------
    tuple[Optional[bytes], str]
        (ZIPバイト列, 推奨ファイル名)。画像が1枚もない場合は (None, "").
    """
    vd_visualizations = st.session_state.get("vd_visualizations", {}) or {}
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, payload in vd_visualizations.items():
            if not isinstance(payload, dict):
                continue
            patient_id = str(
                payload.get("patient_id") or extract_patient_id_from_filename(filename)
            )
            for key, ext in (("superficial", "superficial_visualization.png"), ("deep", "deep_visualization.png")):
                raw = payload.get(key)
                if isinstance(raw, (bytes, bytearray)):
                    arcname = f"{patient_id}/{patient_id}_{ext}"
                    zf.writestr(arcname, bytes(raw))
                    count += 1
    if count == 0:
        return None, ""
    buf.seek(0)
    session_id = st.session_state.get("session_id", "")
    # ZIPファイル名用: session_id の日時部分を使う（無ければ現在時刻）
    ts = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        if not session_id
        else session_id.replace(":", "").replace("-", "")[:15]
    )
    return buf.getvalue(), f"VD_visualization_{ts}.zip"


def build_zip_from_export_subdir(
    export_root: Path, subdir_name: str, zip_basename: str
) -> Tuple[Optional[bytes], str]:
    """
    export_root 配下の指定サブディレクトリをZIPにまとめる（Folder Batch用ダウンロード）
    対象が無い・存在しない・IO エラー時も例外を投げず (None, "") を返す。

    Returns
    -------
    tuple[Optional[bytes], str]
        (ZIPバイト列, 推奨ファイル名)。ディレクトリが無いか空の場合は (None, "").
    """
    try:
        dir_path = Path(export_root) / subdir_name
        if not dir_path.is_dir():
            return None, ""
        buf = io.BytesIO()
        count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(dir_path.rglob("*")):
                if f.is_file():
                    arcname = f.relative_to(dir_path)
                    zf.write(f, str(arcname))
                    count += 1
        if count == 0:
            return None, ""
        buf.seek(0)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return buf.getvalue(), f"{zip_basename}_{ts}.zip"
    except Exception:
        return None, ""


# ============================================================================
# スクロールレスMNV ROI選択画面
# ============================================================================
def show_scrollfree_mnv_roi_screen():
    """スクロールレスMNV ROI選択画面"""
    files = st.session_state.file_queue
    idx = st.session_state.current_index

    if idx >= len(files):
        st.session_state.mode = "summary"
        st.rerun()
        return

    file_info = files[idx]
    filename = file_info["name"]
    image_bytes = file_info["bytes"]

    # プログレス表示（コンパクト）
    progress_pct = ((idx + 1) / len(files)) * 100
    st.progress(progress_pct / 100)

    # ヘッダー（コンパクト）
    st.markdown(
        f'<div class="compact-header">MNV — Draw ROI (image {idx+1} of {len(files)})</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"File: {filename}")

    st.caption("Draw the lesion ROI on the canvas below (Draw panel), then click **Analyze**.")
    canvas = ScrollFreeROICanvas()
    roi_mask = canvas.render_compact(
        image_bytes=image_bytes,
        key_suffix=f"mnv_{idx}",
        max_canvas_height=450,
    )

    st.divider()
    st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(
            "Analyze",
            type="primary",
            use_container_width=True,
            disabled=(roi_mask is None),
            key=f"mnv_roi_analyze_{idx}_{filename}",
        ):
            if roi_mask is not None:
                scale_mm = st.session_state.get("scale_mm", 6.0)
                # Folder Batchモードの場合、FD用画像（4.*）を探索
                fd_image_path = None
                if st.session_state.get("processing_mode") == "Folder Batch":
                    input_folder = st.session_state.get("input_path", "")
                    if input_folder:
                        try:
                            folder_path = Path(input_folder).expanduser()
                            fd_image_path = find_fd_pair_image(filename, folder_path)
                            # パスが存在することを確認
                            if fd_image_path and Path(fd_image_path).exists():
                                log_event(
                                    "fd_image_found",
                                    {
                                        "mnv_filename": filename,
                                        "fd_image_path": fd_image_path,
                                    },
                                    force_session=False,
                                )
                            else:
                                # パスが存在しない場合は None に設定
                                if fd_image_path:
                                    log_event(
                                        "fd_image_path_not_exists",
                                        {
                                            "mnv_filename": filename,
                                            "fd_image_path": fd_image_path,
                                        },
                                        force_session=False,
                                    )
                                else:
                                    log_event(
                                        "fd_image_not_found",
                                        {
                                            "mnv_filename": filename,
                                            "searched_folder": str(folder_path),
                                        },
                                        force_session=False,
                                    )
                                fd_image_path = None
                        except Exception as e:
                            # FD画像探索のエラーは解析を止めない
                            log_event(
                                "fd_image_search_error",
                                {
                                    "mnv_filename": filename,
                                    "error": str(e),
                                },
                                force_session=False,
                            )
                            fd_image_path = None
                if run_mnv_analysis(
                    filename, image_bytes, roi_mask, scale_mm, flow_deficit_image_path=fd_image_path
                ):
                    st.session_state.mode = "mnv_qc"
                    st.rerun()
                    return

    with col2:
        if st.button(
            "Skip",
            use_container_width=True,
            key=f"mnv_roi_skip_{idx}_{filename}",
        ):
            st.session_state.qc_status[filename] = "skipped"
            st.session_state.current_index += 1
            st.rerun()
            return

    with col3:
        if st.button(
            "Cancel",
            use_container_width=True,
            key=f"mnv_roi_cancel_{idx}_{filename}",
        ):
            st.session_state.mode = "idle"
            st.rerun()
            return

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# スクロールレスQC画面
# ============================================================================
def show_scrollfree_qc_screen():
    """スクロールレスQC画面"""
    files = st.session_state.file_queue
    idx = st.session_state.current_index

    if idx >= len(files):
        st.session_state.mode = "summary"
        st.rerun()
        return

    file_info = files[idx]
    filename = file_info["name"]

    res = st.session_state.per_file_results.get(filename)
    if res is None:
        st.session_state.mode = "mnv_roi"
        st.rerun()
        return

    st.markdown(
        f'<div class="compact-header">MNV QC — Image {idx+1} of {len(files)}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"File: {filename}")

    metrics = res.get("metrics", {})
    success = res.get("success", True)

    if not success and res.get("error"):
        st.error(f"解析エラー: {res['error']}")

    # VDと同様の左右2カラム: 左=RGB, 右=FD可視化 or distanceカラー
    st.markdown("##### Result images")
    qc_max_width = 450
    qc_max_height = 400

    def _resize_for_qc(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[0], img.shape[1]
        scale = min(
            qc_max_width / w if w > 0 else 1,
            qc_max_height / h if h > 0 else 1,
            1.0,
        )
        if scale < 1.0:
            new_w, new_h = int(round(w * scale)), int(round(h * scale))
            return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return img

    mnv_qc_left, mnv_qc_right = st.columns(2)
    with mnv_qc_left:
        rgb = res.get("metrics", {}).get("rgb")
        if rgb is not None and isinstance(rgb, np.ndarray):
            rgb_display = _resize_for_qc(rgb)
            st.image(
                rgb_display,
                caption="MNV RGB overlay",
                use_column_width=True,
            )
        else:
            st.info("RGB not available.")

    with mnv_qc_right:
        # 【データフローの検証】パイプラインから取得したfd_visualizationを確認
        metrics = res.get("metrics", {})
        fd_vis = metrics.get("fd_visualization")
        
        # デバッグ: データフローの検証ログ（一時的に表示）
        if st.session_state.get("debug_mode", False):
            st.write("**Debug Info:**")
            st.write(f"- metrics keys: {list(metrics.keys())}")
            st.write(f"- fd_visualization type: {type(fd_vis)}")
            if fd_vis is not None:
                st.write(f"- fd_visualization shape: {fd_vis.shape if isinstance(fd_vis, np.ndarray) else 'N/A'}")
            else:
                st.write("- fd_visualization: None")
        
        if fd_vis is not None and isinstance(fd_vis, np.ndarray):
            # 【BGR to RGB変換】FlowDeficitVisualizer が返す画像は BGR 形式（OpenCV標準）
            # Streamlit表示前に BGR -> RGB 変換を必須で実行
            try:
                if len(fd_vis.shape) == 3 and fd_vis.shape[2] == 3:
                    fd_vis_rgb = cv2.cvtColor(fd_vis, cv2.COLOR_BGR2RGB)
                else:
                    fd_vis_rgb = fd_vis
                
                # 【強制再描画】最新の解析画像を確実に表示
                fd_display = _resize_for_qc(fd_vis_rgb)
                st.image(
                    fd_display,
                    caption="Flow Deficit (FD) - 4.tif背景 + ROI転写 + 物理的拡張3層",
                    use_column_width=True,
                )
            except Exception as e:
                st.error(f"FD画像の表示エラー: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            # 【詳細なエラー情報】fd_visualizationがNoneの場合の原因を特定
            if fd_vis is None:
                # パイプライン内で生成に失敗した可能性
                error_msg = "FD visualization not available."
                st.warning(error_msg)
                
                # デバッグモード時は詳細情報を表示
                if st.session_state.get("debug_mode", False):
                    st.write("**Debug Details:**")
                    st.write(f"- flow_deficit_image_path in metrics: {'flow_deficit_image_path' in metrics}")
                    st.write(f"- roi_mask available: {res.get('roi_mask') is not None}")
                    if res.get('roi_mask') is not None:
                        roi_shape = res['roi_mask'].shape if isinstance(res['roi_mask'], np.ndarray) else 'N/A'
                        st.write(f"- roi_mask shape: {roi_shape}")
            else:
                st.error(
                    f"FD visualization has invalid type: {type(fd_vis)}. "
                    f"Expected np.ndarray, got {type(fd_vis).__name__}"
                )

    st.markdown("##### Key metrics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        area_val = metrics.get("mnv_area_mm2", metrics.get("area", 0))
        st.metric(
            "MNV Area",
            (
                f"{area_val:.3f} mm²"
                if isinstance(area_val, (int, float))
                else str(area_val)
            ),
        )
    with col2:
        vd = metrics.get("vessel_density", 0)
        vd_display = vd * 100 if isinstance(vd, (int, float)) else vd
        st.metric(
            "Vessel Density",
            f"{vd_display:.2f}%" if isinstance(vd_display, (int, float)) else str(vd),
        )
    with col3:
        st.metric("Subtype", metrics.get("mnv_subtype", "N/A"))
    with col4:
        st.metric("Status", "OK" if success else "Error")

    st.divider()
    st.caption("Accept and go to the next image, or reject to redraw ROI.")
    st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
    col_ok, col_ng = st.columns([1, 1])

    with col_ok:
        if st.button(
            "Accept & Continue",
            type="primary",
            use_container_width=True,
            key=f"mnv_qc_accept_{idx}_{filename}",
        ):
            st.session_state.qc_status[filename] = "ok"
            st.session_state.current_index += 1
            if st.session_state.current_index < len(files):
                st.session_state.mode = "mnv_roi"
            else:
                st.session_state.mode = "summary"
            st.rerun()
            return

    with col_ng:
        if st.button(
            "Reject → Redraw ROI",
            use_container_width=True,
            key=f"mnv_qc_reject_{idx}_{filename}",
        ):
            st.session_state.mode = "mnv_roi"
            st.rerun()
            return

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# VD QC画面
# ============================================================================
def show_vd_qc_screen():
    """VD QC画面（per-patient表示）"""
    vd_file_list = list(st.session_state.get("vd_file_list") or [])
    if not vd_file_list:
        vd_file_list = list((st.session_state.get("vd_results") or {}).get("superficial_files") or [])
        if vd_file_list:
            st.session_state.vd_file_list = vd_file_list
    vd_count = int(st.session_state.get("vd_file_count", 0)) or len(vd_file_list)
    idx = int(st.session_state.get("current_index", 0))

    if vd_count <= 0 or idx < 0 or idx >= vd_count:
        st.session_state.mode = "summary"
        st.rerun()
    if idx >= len(vd_file_list):
        st.session_state.mode = "summary"
        st.rerun()
    filename = vd_file_list[idx]

    res = st.session_state.per_file_results.get(filename)
    if res is None:
        st.session_state.mode = "summary"
        st.rerun()

    metrics = res.get("metrics", {}) if isinstance(res.get("metrics"), dict) else {}

    progress_pct = (idx + 1) / vd_count * 100 if vd_count else 0
    st.progress(min(progress_pct / 100, 1.0))
    st.markdown(
        f'<div class="compact-header">VD QC — {idx+1} / {vd_count}</div>',
        unsafe_allow_html=True,
    )

    if get_vd_metrics_for_file and get_vd_summary_value:
        data = get_vd_metrics_for_file(metrics, filename)
        if not data:
            st.warning("No VD results for this file. Check input or suffixes.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("FAZ Area (mm²)", f"{data['faz_area']:.3f}")
            with col2:
                st.metric("FAZ Circularity", f"{data['faz_circularity']:.3f}")
            with col3:
                st.metric("Superficial VD (whole %)", f"{data['superficial_whole']:.2f}%")
            with col4:
                st.metric("Deep VD (whole %)", f"{data['deep_whole']:.2f}%")

            sec_col1, sec_col2 = st.columns(2)
            with sec_col1:
                st.caption("Superficial")
                sup_series = pd.Series(
                    [
                        data["superficial_sectors"]["superior"],
                        data["superficial_sectors"]["temporal"],
                        data["superficial_sectors"]["nasal"],
                        data["superficial_sectors"]["inferior"],
                    ],
                    index=["Superior", "Temporal", "Nasal", "Inferior"],
                )
                st.bar_chart(sup_series)
            with sec_col2:
                st.caption("Deep")
                deep_series = pd.Series(
                    [
                        data["deep_sectors"]["superior"],
                        data["deep_sectors"]["temporal"],
                        data["deep_sectors"]["nasal"],
                        data["deep_sectors"]["inferior"],
                    ],
                    index=["Superior", "Temporal", "Nasal", "Inferior"],
                )
                st.bar_chart(deep_series)
    else:
        st.info("VD metrics unavailable.")

    vd_vis = (st.session_state.get("vd_visualizations", {}) or {}).get(filename, {})
    sup_bytes = vd_vis.get("superficial")
    deep_bytes = vd_vis.get("deep")
    if sup_bytes or deep_bytes:
        with st.expander("Overlay", expanded=True):
            v1, v2 = st.columns(2)
            with v1:
                if sup_bytes:
                    st.image(sup_bytes, caption="Superficial", use_column_width=True)
                else:
                    st.caption("—")
            with v2:
                if deep_bytes:
                    st.image(deep_bytes, caption="Deep", use_column_width=True)
                else:
                    st.caption("—")

    st.divider()
    st.caption("Accept または Skip で次へ")
    st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
    col_ok, col_ng = st.columns([1, 1])
    with col_ok:
        if st.button(
            "Accept & Continue",
            type="primary",
            use_container_width=True,
            key=f"vd_accept_{idx}_{filename}",
        ):
            st.session_state.qc_status[filename] = "ok"
            st.session_state.current_index += 1
            n_vd = int(st.session_state.get("vd_file_count", 0)) or len(st.session_state.get("vd_file_list") or [])
            if st.session_state.current_index < n_vd:
                st.session_state.mode = "vd_qc"
            else:
                st.session_state.mode = "summary"
            st.rerun()
    with col_ng:
        if st.button(
            "Skip (Reject)",
            use_container_width=True,
            key=f"vd_reject_{idx}_{filename}",
        ):
            st.session_state.qc_status[filename] = "skipped"
            st.session_state.current_index += 1
            n_vd = int(st.session_state.get("vd_file_count", 0)) or len(st.session_state.get("vd_file_list") or [])
            if st.session_state.current_index < n_vd:
                st.session_state.mode = "vd_qc"
            else:
                st.session_state.mode = "summary"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# アップロード画面
# ============================================================================
def show_upload_screen():
    """スクロールレスアップロード画面"""

    st.markdown(
        '<div class="compact-header">🔬 ARIAKE OCTA Analysis</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="compact-subheader">Scrollable Interface</div>',
        unsafe_allow_html=True,
    )

    analysis_type = st.session_state.get("analysis_type", "MNV")
    if analysis_type == "VD":
        st.markdown("#### VD")
        st.caption(
            "File Upload: 単一画像でFAZ+VD。Folder Batch: ペア（*1.tif / *2.tif）を配置。サフィックスはサイドバーで変更。"
        )
    else:
        st.markdown("#### MNV — File Upload")
        st.info("Upload your OCTA images to start MNV analysis (ROI will be drawn on the next step).")

    # VD解析: File Upload / Folder Batch の両方対応
    if analysis_type == "VD":
        current_mode = st.session_state.get("processing_mode", "File Upload")
        if current_mode not in {"File Upload", "Folder Batch"}:
            current_mode = "File Upload"
            st.session_state.processing_mode = current_mode
        st.caption(f"Current Mode: {current_mode}")
        if st.button(
            "Use File Upload",
            key="set_mode_file_upload_vd",
            use_container_width=True,
            type="primary" if current_mode == "File Upload" else "secondary",
        ):
            st.session_state.processing_mode = "File Upload"
            st.session_state.browsing_for = None
            st.rerun()
        if st.button(
            "Use Folder Batch",
            key="set_mode_folder_batch_vd",
            use_container_width=True,
            type="primary" if current_mode == "Folder Batch" else "secondary",
        ):
            st.session_state.processing_mode = "Folder Batch"
            st.rerun()
    else:
        # MNV解析時は File Upload / Folder Batch を選択可能
        current_mode = st.session_state.get("processing_mode", "File Upload")
        if current_mode not in {"File Upload", "Folder Batch"}:
            current_mode = "File Upload"
            st.session_state.processing_mode = current_mode

        st.caption(f"Current Mode: {current_mode}")
        if st.button(
            "Use File Upload",
            key="set_mode_file_upload",
            use_container_width=True,
            type="primary" if current_mode == "File Upload" else "secondary",
        ):
            st.session_state.processing_mode = "File Upload"
            st.session_state.browsing_for = None
            st.rerun()
        if st.button(
            "Use Folder Batch",
            key="set_mode_folder_batch",
            use_container_width=True,
            type="primary" if current_mode == "Folder Batch" else "secondary",
        ):
            st.session_state.processing_mode = "Folder Batch"
            st.rerun()

    processing_mode = st.session_state.get("processing_mode", "Folder Batch" if analysis_type == "VD" else "File Upload")

    input_folder = str(st.session_state.get("input_path", ""))
    output_folder = str(st.session_state.get("output_path", ""))
    source_mode = "file_upload"

    uploaded_files = []
    if processing_mode == "File Upload":
        upload_label = "Select or drag OCTA images"
        if analysis_type == "VD":
            upload_help = (
                "Upload one or more OCTA images. Each image is processed "
                "independently (FAZ detection + VD analysis). No pair required."
            )
        else:
            upload_help = "Upload one or more OCTA images for MNV analysis."
        uploaded_files = st.file_uploader(
            upload_label,
            type=["tif", "tiff", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help=upload_help,
        )
        if uploaded_files:
            with st.expander("Uploaded files", expanded=True):
                for i, f in enumerate(uploaded_files, 1):
                    st.caption(f"{i}. {f.name}")
                st.caption(
                    f"Total: {len(uploaded_files)} image(s). Draw ROI on each image in the next step."
                )
        output_folder = ""
    else:
        source_mode = "folder_batch"
        st.markdown("### 📁 Folder Settings")
        pending_input = st.session_state.pop("pending_input_folder_text", None)
        if pending_input is not None:
            st.session_state.input_path = str(pending_input)
            st.session_state.input_folder_text = str(pending_input)
        pending_output = st.session_state.pop("pending_output_folder_text", None)
        if pending_output is not None:
            st.session_state.output_path = str(pending_output)
            st.session_state.output_folder_text = str(pending_output)

        if "input_folder_text" not in st.session_state:
            st.session_state.input_folder_text = input_folder
        if "output_folder_text" not in st.session_state:
            st.session_state.output_folder_text = output_folder

        col1, col2 = st.columns([4, 1])
        with col1:
            input_folder = st.text_input(
                "Input Folder",
                placeholder="/Users/yourname/data/input",
                key="input_folder_text",
            ).strip()
        with col2:
            if st.button("📂 Browse", key="browse_input"):
                st.session_state.browsing_for = "input"
                st.session_state.current_browse_path = (
                    input_folder if input_folder else str(Path.home())
                )

        col3, col4 = st.columns([4, 1])
        with col3:
            output_folder = st.text_input(
                "Output Folder",
                placeholder="/Users/yourname/data/output",
                key="output_folder_text",
            ).strip()
        with col4:
            if st.button("📂 Browse", key="browse_output"):
                st.session_state.browsing_for = "output"
                st.session_state.current_browse_path = (
                    output_folder if output_folder else str(Path.home())
                )

        st.session_state.input_path = input_folder
        st.session_state.output_path = output_folder

        if st.session_state.get("browsing_for") is not None:
            browse_target = st.session_state.get("browsing_for")
            st.markdown(f"#### 📂 Select {'Input' if browse_target == 'input' else 'Output'} Folder")

            def _sync_browse_target_path(path_value: str) -> None:
                """現在参照中のtargetへパスを即時反映"""
                st.session_state.current_browse_path = path_value
                if browse_target == "input":
                    st.session_state.input_path = path_value
                    st.session_state.pending_input_folder_text = path_value
                else:
                    st.session_state.output_path = path_value
                    st.session_state.pending_output_folder_text = path_value

            quick_paths = {
                "🏠 Home": str(Path.home()),
                "🖥️ Desktop": str(Path.home() / "Desktop"),
                "📄 Documents": str(Path.home() / "Documents"),
                "📥 Downloads": str(Path.home() / "Downloads"),
            }
            quick_cols = st.columns(len(quick_paths))
            for idx, (label, qpath) in enumerate(quick_paths.items()):
                with quick_cols[idx]:
                    if st.button(label, key=f"quick_nav_{idx}", use_container_width=True):
                        _sync_browse_target_path(qpath)

            browse_path = Path(
                st.session_state.get("current_browse_path", str(Path.home()))
            ).expanduser()
            st.caption(f"Current Path: {browse_path}")
            if browse_path.parent != browse_path:
                if st.button("⬆️ Parent Folder", key="go_parent_folder"):
                    browse_path = browse_path.parent
                    _sync_browse_target_path(str(browse_path))

            try:
                subdirs = sorted(
                    [d for d in browse_path.iterdir() if d.is_dir()],
                    key=lambda x: x.name.lower(),
                )
                if subdirs:
                    max_items = 100
                    shown_subdirs = subdirs[:max_items]
                    st.caption("Subfolders (single click to open):")
                    for idx, subdir in enumerate(shown_subdirs):
                        if st.button(
                            f"📁 {subdir.name}",
                            key=f"open_subdir_single_{idx}_{subdir.name}",
                            use_container_width=True,
                        ):
                            _sync_browse_target_path(str(subdir))
                            browse_path = subdir
                            st.caption(f"Opened: {subdir}")
                else:
                    st.info("No subfolders found.")
            except PermissionError:
                st.error("Permission denied for this directory.")
            except Exception as e:
                st.error(f"Directory browse error: {e}")

            sel_col1, sel_col2 = st.columns(2)
            with sel_col1:
                if st.button("✅ Select This Folder", key="select_current_folder", use_container_width=True):
                    chosen_path = str(browse_path)
                    _sync_browse_target_path(chosen_path)
                    log_event(
                        "folder_selected",
                        {
                            "target": browse_target,
                            "path": chosen_path,
                            "exists": Path(chosen_path).exists(),
                        },
                        force_session=False,
                    )
                    st.session_state.browsing_for = None
                    if browse_target == "input":
                        input_folder = chosen_path
                    else:
                        output_folder = chosen_path
            with sel_col2:
                if st.button("❌ Cancel", key="cancel_folder_select", use_container_width=True):
                    st.session_state.browsing_for = None

        input_folder = str(st.session_state.get("input_path", "")).strip()
        output_folder = str(st.session_state.get("output_path", "")).strip()

        if input_folder:
            input_path_obj = Path(input_folder).expanduser()
            if input_path_obj.exists() and input_path_obj.is_dir():
                all_image_files = sorted(
                    [
                        p
                        for p in input_path_obj.iterdir()
                        if p.is_file()
                        and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
                    ],
                    key=lambda p: p.name.lower(),
                )
                # MNV解析の場合、ROI指定画面に表示するファイルをフィルタリング
                analysis_type = st.session_state.get("analysis_type", "MNV")
                uploaded_files = filter_mnv_files_for_roi_selection(
                    all_image_files, analysis_type=analysis_type
                )
                total_count = len(all_image_files)
                filtered_count = len(uploaded_files)
                if analysis_type == "MNV" and total_count != filtered_count:
                    st.info(
                        f"✅ Found {total_count} images in input folder. "
                        f"Filtered to {filtered_count} files for ROI selection "
                        f"(excluded: *1.tif, *2.tif, *4.tif)"
                    )
                else:
                    st.info(f"✅ Found {total_count} images in input folder")
                if uploaded_files:
                    with st.expander("📋 Files", expanded=False):
                        for i, file_path in enumerate(uploaded_files[:200], 1):
                            st.caption(f"{i}. {file_path.name}")
            else:
                st.error(f"Input folder not found: {input_folder}")
        else:
            st.warning("Specify an input folder to start Folder Batch mode.")

        if output_folder:
            output_path_obj = Path(output_folder).expanduser()
            if not output_path_obj.exists():
                st.warning(f"Output folder will be created: {output_path_obj}")
        else:
            st.warning("Specify an output folder (session subfolder will be created inside).")

    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} files ready")

        if st.button(
            "🚀 Start Analysis",
            type="primary",
            use_container_width=True,
        ):
            if processing_mode == "Folder Batch" and not output_folder:
                st.error("Output folder is required in Folder Batch mode.")
                return

            st.session_state.persistent_output_dir = None
            st.session_state.session_id = _generate_session_id()
            st.session_state.analysis_started_at = now_iso()
            st.session_state.analysis_ended_at = ""
            st.session_state.analysis_duration_sec = 0.0
            st.session_state.analysis_start_epoch = time.time()
            st.session_state.analysis_end_logged = False
            st.session_state.folder_exports_saved = False
            st.session_state.vd_visualizations = {}

            file_queue = []
            if processing_mode == "File Upload":
                for file in uploaded_files:
                    try:
                        data = file.getbuffer()
                    except Exception:
                        data = file.read()
                    file_queue.append({"name": file.name, "bytes": bytes(data)})
                st.session_state.output_path = ""
            else:
                for file_path in uploaded_files:
                    try:
                        file_queue.append(
                            {"name": file_path.name, "bytes": file_path.read_bytes()}
                        )
                    except Exception:
                        continue
                st.session_state.input_path = input_folder
                st.session_state.output_path = output_folder

            if not file_queue:
                st.error("No readable image files found for analysis.")
                return

            # file_queueをsession_stateに設定（ensure_persistent_output_dir()で使用するため）
            st.session_state.file_queue = file_queue
            
            if processing_mode == "Folder Batch":
                log_event(
                    "folder_selected",
                    {
                        "target": "input",
                        "path": input_folder,
                        "exists": bool(input_folder and Path(input_folder).expanduser().exists()),
                    },
                    force_session=True,
                )
                log_event(
                    "folder_selected",
                    {
                        "target": "output",
                        "path": output_folder,
                        "exists": bool(output_folder and Path(output_folder).expanduser().exists()),
                    },
                    force_session=True,
                )
            st.session_state.current_index = 0
            st.session_state.per_file_results = {}
            st.session_state.qc_status = {}
            st.session_state.pop("vd_file_list", None)
            st.session_state.pop("vd_file_count", None)
            st.session_state.pop("vd_results", None)
            analysis_type = st.session_state.get("analysis_type", "MNV")
            log_event(
                "analysis_start",
                {
                    "started_at": st.session_state.analysis_started_at,
                    "source_mode": source_mode,
                    "file_count": len(file_queue),
                    "scale_mm": st.session_state.get("scale_mm", 6.0),
                    "vd_side": st.session_state.get("vd_side", "right"),
                    "sup_suffix": st.session_state.get("sup_suffix", "1.tif"),
                    "deep_suffix": st.session_state.get("deep_suffix", "2.tif"),
                    "vd_use_intref": st.session_state.get("vd_use_intref", False),
                    "vd_intref_percentile": st.session_state.get(
                        "vd_intref_percentile", 40.0
                    ),
                    "vd_intref_center_ratio": st.session_state.get(
                        "vd_intref_center_ratio", 0.5
                    ),
                    "input_folder": input_folder if source_mode == "folder_batch" else "",
                    "output_folder": output_folder if source_mode == "folder_batch" else "",
                },
                force_session=True,
            )

            if analysis_type == "VD":
                with st.spinner("VD解析中..."):
                    ok = run_vd_batch(
                        file_queue,
                        scale_mm=st.session_state.get("scale_mm", 6.0),
                        vd_side=st.session_state.get("vd_side", "right"),
                        sup_suffix=st.session_state.get("sup_suffix", "1.tif"),
                        deep_suffix=st.session_state.get("deep_suffix", "2.tif"),
                        save_stages=False,
                        analyst_name=st.session_state.get(
                            "analyst_name", "Python Streamlit Analysis"
                        ),
                        vd_use_intref=st.session_state.get("vd_use_intref", False),
                        vd_intref_percentile=st.session_state.get(
                            "vd_intref_percentile", 40.0
                        ),
                        vd_intref_center_ratio=st.session_state.get(
                            "vd_intref_center_ratio", 0.5
                        ),
                        single_image_mode=(processing_mode == "File Upload"),
                    )
                if ok:
                    st.session_state.mode = "vd_qc"
                else:
                    st.error("VD解析に失敗しました。")
                    return
            else:
                st.session_state.mode = "mnv_roi"
            st.rerun()


# ============================================================================
# サマリー画面
# ============================================================================
def _summary_file_list() -> list[str]:
    """
    サマリー用のファイル名リストを返す。VD/MNV 混在・dict 混入対策済み。
    常に list[str] を返し、per_file_results.get(filename) が安全に使えるようにする。
    """
    vd_list = st.session_state.get("vd_file_list") or []
    if vd_list:
        out = [str(x) for x in vd_list if isinstance(x, str)]
        if out:
            return out
    fq = st.session_state.get("file_queue", [])
    out = []
    for f in fq:
        if isinstance(f, dict) and f.get("name"):
            out.append(str(f["name"]))
        elif isinstance(f, str):
            out.append(f)
    if out:
        return out
    per = st.session_state.get("per_file_results", {})
    return [str(k) for k in per.keys() if isinstance(k, str)]


def show_summary_screen():
    """スクロールレスサマリー画面"""

    st.markdown(
        '<div class="compact-header">📊 Analysis Complete</div>', unsafe_allow_html=True
    )

    # 表示用ファイルリスト（VDの場合はvd_file_list、MNVの場合はfile_queue）。TypeError 対策で正規化
    file_list = _summary_file_list()
    total = len(file_list)
    ok_count = sum(1 for k, v in st.session_state.qc_status.items() if v == "ok" and k in file_list)
    skipped_count = sum(1 for k, v in st.session_state.qc_status.items() if v == "skipped" and k in file_list)
    pending_count = max(total - ok_count - skipped_count, 0)
    success_rate = (ok_count / total * 100) if total > 0 else 0.0

    if (
        st.session_state.get("analysis_started_at")
        and not st.session_state.get("analysis_end_logged", False)
    ):
        ended_at = now_iso()
        start_epoch = float(st.session_state.get("analysis_start_epoch", 0.0) or 0.0)
        duration_sec = round(max(time.time() - start_epoch, 0.0), 3) if start_epoch else 0.0
        st.session_state.analysis_ended_at = ended_at
        st.session_state.analysis_duration_sec = duration_sec
        log_event(
            "analysis_end",
            {
                "started_at": st.session_state.get("analysis_started_at"),
                "ended_at": ended_at,
                "duration_sec": duration_sec,
                "total_count": total,
                "ok_count": ok_count,
                "skipped_count": skipped_count,
                "pending_count": pending_count,
                "success_rate_percent": round(success_rate, 2),
            },
            force_session=True,
        )
        st.session_state.analysis_end_logged = True

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", total)
    with col2:
        st.metric("Accepted", ok_count)
    with col3:
        st.metric("Skipped", skipped_count)
    with col4:
        st.metric("Acceptance Rate", f"{success_rate:.0f}%")

    if pending_count > 0:
        st.caption(f"Pending: {pending_count}")

    # 結果テーブル（MNV/VD混在対応）
    rows = []
    for fname in file_list:
        res = st.session_state.per_file_results.get(fname, {})
        status = st.session_state.qc_status.get(fname, "pending")
        file_type = res.get("type", "Unknown")
        mnv_area = "–"
        vd_value = "–"
        complexity = "–"

        if res:
            metrics = res.get("metrics", {}) or {}
            if file_type == "MNV":
                v = metrics.get("mnv_area_mm2")
                mnv_area = f"{v:.3f}" if isinstance(v, (int, float)) else "–"
                v = metrics.get("complexity_score")
                complexity = f"{v:.2f}" if isinstance(v, (int, float)) else "–"
            elif file_type == "VD" and get_vd_summary_value:
                try:
                    v = get_vd_summary_value(metrics, fname)
                    vd_value = f"{v:.2f}%" if v is not None else "–"
                except Exception:
                    vd_value = "–"

        rows.append(
            {
                "File": fname,
                "Type": file_type,
                "Status": status,
                "MNV Area": mnv_area,
                "VD %": vd_value,
                "Complexity": complexity,
            }
        )

    if rows:
        df = pd.DataFrame(rows)
        st.markdown("### 📋 Results")
        filter_col1, filter_col2 = st.columns([1, 1])
        with filter_col1:
            status_filter = st.selectbox(
                "Status filter",
                ["all", "ok", "skipped", "pending"],
                index=1,
                key="summary_status_filter",
            )
        with filter_col2:
            type_filter = st.selectbox(
                "Type filter",
                ["all", "MNV", "VD", "Unknown"],
                index=0,
                key="summary_type_filter",
            )

        filtered_df = df.copy()
        if status_filter != "all":
            filtered_df = filtered_df[filtered_df["Status"] == status_filter]
        if type_filter != "all":
            filtered_df = filtered_df[filtered_df["Type"] == type_filter]
        filtered_df = filtered_df.sort_values(by=["Status", "File"], kind="stable")

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    with st.expander("QC Status Log", expanded=False):
        for fname in file_list:
            status = st.session_state.qc_status.get(fname, "pending")
            icon = "✅" if status == "ok" else "⏭️" if status == "skipped" else "❓"
            st.caption(f"{icon} {fname}")

    has_mnv_result = any(
        (st.session_state.per_file_results.get(fname, {}) or {}).get("type") == "MNV"
        for fname in file_list
    )
    vd_csv_bytes, vd_csv_name = build_vd_results_csv()
    # VD解析は Folder Batch のみ対応のため、vd_csv_bytes の存在で判定可能（シンプル化）
    has_vd = bool(vd_csv_bytes and vd_csv_name)
    # MNV CSVは1回だけ取得（解析対象0件のときのみ None,""）
    mnv_csv_bytes, mnv_csv_name = None, ""
    if has_mnv_result:
        mnv_csv_bytes, mnv_csv_name = export_mnv_results_to_csv()
    has_mnv_csv = bool(mnv_csv_bytes and mnv_csv_name)
    # Stability CSV（MNV解析済みのときのみ、4指標: stab_cv, stab_mean_adjacent_change, stab_residual_cv, stab_range_percent）
    stability_csv_bytes, stability_csv_name = None, ""
    if has_mnv_result:
        stability_csv_bytes, stability_csv_name = build_stability_csv()
    has_stability_csv = bool(stability_csv_bytes and stability_csv_name)

    # Folder Batch: 保存は1回だけ。ensure で export_root 確定 → folder_exports_saved で二重実行防止
    is_folder_batch = st.session_state.get("processing_mode") == "Folder Batch"
    if is_folder_batch and (has_mnv_result or has_vd):
        if not st.session_state.get("folder_exports_saved", False):
            session_dir = ensure_persistent_output_dir()
            export_root = session_dir / "exports"
            export_root.mkdir(parents=True, exist_ok=True)
            saved_files = []
            if has_mnv_csv:
                (export_root / mnv_csv_name).write_bytes(mnv_csv_bytes)
                saved_files.append(str(export_root / mnv_csv_name))
            if has_stability_csv:
                (export_root / stability_csv_name).write_bytes(stability_csv_bytes)
                saved_files.append(str(export_root / stability_csv_name))
            if vd_csv_bytes and vd_csv_name:
                (export_root / vd_csv_name).write_bytes(vd_csv_bytes)
                saved_files.append(str(export_root / vd_csv_name))
            saved_files.extend(save_mnv_rgb_images(export_root, file_list))
            saved_files.extend(save_vd_visualization_images(export_root))
            saved_files.extend(export_log_variants(export_root))
            st.session_state.folder_exports_saved = True
            if saved_files:
                st.success("✅ CSV and result images were saved automatically to output folder.")
                log_event(
                    "folder_batch_auto_saved",
                    {"saved_files": saved_files},
                    force_session=True,
                )

    # アクション（メイン行: MNV結果が無い／CSV出力行0の場合はMNV列を出さない）
    st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
    n_main = (
        1
        + (1 if has_mnv_csv else 0)
        + (1 if has_stability_csv else 0)
        + (1 if (vd_csv_bytes and vd_csv_name) else 0)
    )
    main_cols = st.columns(max(n_main, 1))
    idx = 0
    with main_cols[idx]:
        if st.button(
            "🔄 New Analysis",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.mode = "idle"
            st.session_state.file_queue = []
            st.session_state.per_file_results = {}
            st.session_state.qc_status = {}
            st.session_state.persistent_output_dir = None
            st.session_state.session_id = ""
            st.session_state.analysis_started_at = ""
            st.session_state.analysis_ended_at = ""
            st.session_state.analysis_duration_sec = 0.0
            st.session_state.analysis_start_epoch = 0.0
            st.session_state.analysis_end_logged = False
            st.session_state.folder_exports_saved = False
            st.session_state.vd_visualizations = {}
            st.session_state.pop("vd_file_list", None)
            st.session_state.pop("vd_file_count", None)
            st.session_state.pop("vd_results", None)
            st.session_state.pop("summary_status_filter", None)
            st.session_state.pop("summary_type_filter", None)
            st.rerun()
        idx += 1
    if has_mnv_csv:
        with main_cols[idx]:
            st.download_button(
                "📥 MNV CSV",
                data=mnv_csv_bytes,
                file_name=mnv_csv_name,
                mime="text/csv",
                use_container_width=True,
            )
        idx += 1
    if has_stability_csv:
        with main_cols[idx]:
            st.download_button(
                "📥 Stability",
                data=stability_csv_bytes,
                file_name=stability_csv_name,
                mime="text/csv",
                use_container_width=True,
                key="dl_stability_csv",
            )
        idx += 1
    if vd_csv_bytes and vd_csv_name:
        with main_cols[idx]:
            st.download_button(
                "📥 VD CSV",
                data=vd_csv_bytes,
                file_name=vd_csv_name,
                mime="text/csv",
                use_container_width=True,
                key="dl_vd_csv",
            )

    # File Upload / Folder Batch 共通: VD解析・MNV解析のセクション構成を揃える
    is_file_upload = st.session_state.get("processing_mode") == "File Upload"
    if is_file_upload and (has_vd or has_mnv_result):
        log_jsonl, log_csv, _log_txt, log_base = get_log_download_bytes()
        sections: list[tuple[str, Optional[bytes], str, bool]] = []
        if has_vd:
            vd_zip, vd_zip_name = build_vd_visualization_zip_bytes()
            sections.append(("VD解析", vd_zip, vd_zip_name, True))
        if has_mnv_result:
            mnv_zip, mnv_zip_name = build_mnv_rgb_zip_bytes(file_list)
            sections.append(("MNV解析", mnv_zip, mnv_zip_name, not has_vd))
        if sections:
            cols = st.columns(len(sections))
            for i, (title, zip_bytes, zip_name, show_log) in enumerate(sections):
                with cols[i]:
                    st.markdown(f"**{title}**")
                    if zip_bytes and zip_name:
                        st.download_button(
                            "📥 VD visualization (zip)" if "VD" in title else "📥 MNV RGB (zip)",
                            data=zip_bytes,
                            file_name=zip_name,
                            mime="application/zip",
                            use_container_width=True,
                            key=f"dl_upload_{i}_zip",
                        )
                    if show_log and log_jsonl is not None:
                        st.download_button(
                            "📥 Log (JSONL)",
                            data=log_jsonl,
                            file_name=f"{log_base}.jsonl",
                            mime="application/jsonlines",
                            use_container_width=True,
                            key=f"dl_upload_{i}_jsonl",
                        )
                        if log_csv is not None:
                            st.download_button(
                                "📥 Log (CSV)",
                                data=log_csv,
                                file_name=f"{log_base}.csv",
                                mime="text/csv",
                                use_container_width=True,
                                key=f"dl_upload_{i}_csv",
                            )

    # Folder Batch: 仕様マトリクスに沿ったダウンロードセクション（VDのみ/MNVのみで空列を出さない）
    # has_vd は上で定義済み（vd_results と vd_visualizations も考慮）
    if is_folder_batch and (has_vd or has_mnv_result):
        persistent = st.session_state.get("persistent_output_dir")
        if not persistent:
            ensure_persistent_output_dir()
            persistent = st.session_state.get("persistent_output_dir")
        if persistent:
            export_root = Path(persistent) / "exports"
            log_jsonl, log_csv, _log_txt, log_base = get_log_download_bytes()
            # append 方式: 表示するセクションだけリストに追加（VDのみなら MNV 列なし）
            sections: list[tuple[str, Optional[bytes], str, bool]] = []
            if has_vd:
                vd_zip, vd_zip_name = build_zip_from_export_subdir(
                    export_root, "VD_visualization", "VD_visualization"
                )
                # Log は VD のみのときはここ、VD+MNV のときもここに1回だけ（重複キー防止）
                sections.append(("VD解析", vd_zip, vd_zip_name, True))
            if has_mnv_result:
                mnv_zip, mnv_zip_name = build_zip_from_export_subdir(
                    export_root, "MNV_RGB", "MNV_RGB"
                )
                # MNV のみのときだけ Log を表示（VD がある場合は上で表示済み）
                sections.append(("MNV解析", mnv_zip, mnv_zip_name, not has_vd))
            if sections:
                cols = st.columns(len(sections))
                for i, (title, zip_bytes, zip_name, show_log) in enumerate(sections):
                    with cols[i]:
                        st.markdown(f"**{title}**")
                        if zip_bytes and zip_name:
                            st.download_button(
                                "📥 VD visualization (zip)" if "VD" in title else "📥 MNV RGB (zip)",
                                data=zip_bytes,
                                file_name=zip_name,
                                mime="application/zip",
                                use_container_width=True,
                                key=f"dl_folder_{i}_zip",
                            )
                        if show_log and log_jsonl is not None:
                            st.download_button(
                                "📥 Log (JSONL)",
                                data=log_jsonl,
                                file_name=f"{log_base}.jsonl",
                                mime="application/jsonlines",
                                use_container_width=True,
                                key=f"dl_folder_{i}_jsonl",
                            )
                            if log_csv is not None:
                                st.download_button(
                                    "📥 Log (CSV)",
                                    data=log_csv,
                                    file_name=f"{log_base}.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    key=f"dl_folder_{i}_csv",
                                )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# メイン関数
# ============================================================================
def main():
    """メイン関数"""
    initialize_session_state()

    if is_auth_enabled() and not st.session_state.get("authenticated", False):
        st.title(f"🔐 {APP_NAME} Login")
        st.caption("Please enter your access key and analysis settings.")

        # サイドメニューで入力する内容をログイン画面に表示
        st.markdown("#### Analysis Setup")
        login_analysis_type = st.selectbox(
            "Analysis Type",
            ["MNV", "VD"],
            key="login_analysis_type",
            help="MNV: lesion ROI + metrics. VD: superficial/deep pairs (1.tif + 2.tif)",
        )
        login_scale_mm = st.number_input(
            "Scale (mm)",
            min_value=1.0,
            max_value=20.0,
            value=float(st.session_state.get("scale_mm", 6.0)),
            step=0.5,
            key="login_scale_mm",
        )
        if login_analysis_type == "VD":
            with st.expander("VD Settings", expanded=True):
                login_vd_side = st.selectbox("Eye Side", ["right", "left"], key="login_vd_side")
                login_sup_suffix = st.text_input(
                    "Superficial suffix",
                    st.session_state.get("sup_suffix", "1.tif"),
                    key="login_sup_suffix",
                    help="1つの場合: 1.tif。複数ペア(visit1/visit2など): 1.tif, 1.tiff のようにカンマ区切り",
                )
                login_deep_suffix = st.text_input(
                    "Deep suffix",
                    st.session_state.get("deep_suffix", "2.tif"),
                    key="login_deep_suffix",
                    help="1つの場合: 2.tif。複数ペア時: 2.tif, 2.tiff のようにSuperficialと対応付けて指定",
                )
                login_vd_use_intref = st.checkbox(
                    "Enable IntRef (optional tuning mode)",
                    value=st.session_state.get("vd_use_intref", False),
                    key="login_vd_use_intref",
                    help="OFF: baseline (recommended). ON: apply intensity refinement.",
                )
                login_vd_intref_percentile = st.slider(
                    "IntRef percentile",
                    min_value=10.0,
                    max_value=60.0,
                    value=float(st.session_state.get("vd_intref_percentile", 40.0)),
                    step=1.0,
                    disabled=not login_vd_use_intref,
                    key="login_vd_intref_percentile",
                )
                login_vd_intref_center_ratio = st.slider(
                    "IntRef center ROI ratio",
                    min_value=0.3,
                    max_value=0.7,
                    value=float(st.session_state.get("vd_intref_center_ratio", 0.5)),
                    step=0.05,
                    disabled=not login_vd_use_intref,
                    key="login_vd_intref_center_ratio",
                )

        st.markdown("#### Operator")
        login_analyst = st.text_input(
            "Operator / Analyst",
            key="login_analyst_name",
            placeholder="Your name",
        ).strip()
        if login_analyst:
            st.session_state.analyst_name = login_analyst
        pwd = st.text_input("Access Key", type="password", key="access_key_input")
        if st.button(
            "Login",
            type="primary",
            use_container_width=True,
        ):
            if not login_analyst:
                st.error("Operator / Analyst is required.")
                st.stop()
            is_success = hmac.compare_digest(pwd, get_access_key())
            log_event(
                "auth_attempt",
                {"success": is_success},
                force_session=False,
            )
            if is_success:
                st.session_state.authenticated = True
                st.session_state.analysis_type = login_analysis_type
                st.session_state.scale_mm = login_scale_mm
                if login_analysis_type == "VD":
                    st.session_state.vd_side = login_vd_side
                    st.session_state.sup_suffix = login_sup_suffix
                    st.session_state.deep_suffix = login_deep_suffix
                    st.session_state.vd_use_intref = login_vd_use_intref
                    st.session_state.vd_intref_percentile = login_vd_intref_percentile
                    st.session_state.vd_intref_center_ratio = login_vd_intref_center_ratio
                # サイドバー用の表示名を同期
                st.session_state.sidebar_analyst_name = login_analyst
                st.rerun()
            else:
                st.error("Invalid access key.")
        st.stop()

    # サイドバー（コンパクト）
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.caption("Configure analysis parameters and monitor session status.")
        st.markdown('<div class="sidebar-section-title">Analysis Setup</div>', unsafe_allow_html=True)

        _analysis_options = ["MNV", "VD"]
        _current_analysis = st.session_state.get("analysis_type", "MNV")
        _analysis_index = _analysis_options.index(_current_analysis) if _current_analysis in _analysis_options else 0
        analysis_type = st.selectbox(
            "Analysis Type",
            _analysis_options,
            index=_analysis_index,
            help="MNV: lesion ROI + metrics. VD: superficial/deep pairs (1.tif + 2.tif)",
        )
        st.session_state.analysis_type = analysis_type

        scale_mm = st.number_input(
            "Scale (mm)",
            min_value=1.0,
            max_value=20.0,
            value=float(st.session_state.get("scale_mm", 6.0)),
            step=0.5,
        )
        st.session_state.scale_mm = scale_mm

        if analysis_type == "VD":
            with st.expander("VD Settings", expanded=True):
                _side_options = ["right", "left"]
                _current_side = st.session_state.get("vd_side", "right")
                _side_index = _side_options.index(_current_side) if _current_side in _side_options else 0
                vd_side = st.selectbox("Eye Side", _side_options, index=_side_index)
                sup_suffix = st.text_input(
                    "Superficial suffix",
                    value=st.session_state.get("sup_suffix", "1.tif"),
                    help="1つの場合: 1.tif。複数ペア(visit1/visit2など): 1.tif, 1.tiff のようにカンマ区切り",
                )
                deep_suffix = st.text_input(
                    "Deep suffix",
                    value=st.session_state.get("deep_suffix", "2.tif"),
                    help="1つの場合: 2.tif。複数ペア時: 2.tif, 2.tiff のようにSuperficialと対応付けて指定",
                )
                vd_use_intref = st.checkbox(
                    "Enable IntRef (optional tuning mode)",
                    value=st.session_state.get("vd_use_intref", False),
                    help="OFF: baseline (recommended). ON: apply intensity refinement.",
                )
                vd_intref_percentile = st.slider(
                    "IntRef percentile",
                    min_value=10.0,
                    max_value=60.0,
                    value=float(st.session_state.get("vd_intref_percentile", 40.0)),
                    step=1.0,
                    disabled=not vd_use_intref,
                )
                vd_intref_center_ratio = st.slider(
                    "IntRef center ROI ratio",
                    min_value=0.3,
                    max_value=0.7,
                    value=float(st.session_state.get("vd_intref_center_ratio", 0.5)),
                    step=0.05,
                    disabled=not vd_use_intref,
                )
                st.session_state.vd_side = vd_side
                st.session_state.sup_suffix = sup_suffix
                st.session_state.deep_suffix = deep_suffix
                st.session_state.vd_use_intref = vd_use_intref
                st.session_state.vd_intref_percentile = vd_intref_percentile
                st.session_state.vd_intref_center_ratio = vd_intref_center_ratio

        st.markdown('<div class="sidebar-section-title">Operator</div>', unsafe_allow_html=True)
        if "sidebar_analyst_name" not in st.session_state:
            st.session_state.sidebar_analyst_name = st.session_state.get(
                "analyst_name", "Python Streamlit Analysis"
            )
        analyst_name = st.text_input(
            "Analyst (optional)",
            key="sidebar_analyst_name",
            placeholder="Your name",
        ).strip()
        st.session_state.analyst_name = analyst_name or "Python Streamlit Analysis"

        st.divider()

        # ステータス表示
        st.markdown("### 📊 Session Status")
        mode = st.session_state.get("mode", "idle")
        st.caption(f"Mode: {mode_label(mode)}")
        st.caption(f"Input: {st.session_state.get('processing_mode', 'File Upload')}")

        fq = st.session_state.get("file_queue", [])
        vfl = st.session_state.get("vd_file_list", [])
        total_files = len(vfl) if vfl else len(fq)
        completed = 0
        if total_files > 0:
            completed = sum(
                1
                for fname in (vfl if vfl else [f.get("name", "") for f in fq])
                if st.session_state.get("qc_status", {}).get(fname) in {"ok", "skipped"}
            )
        st.caption(f"Files: {total_files}")
        if total_files > 0:
            st.progress(min(completed / total_files, 1.0))
            st.caption(f"Progress: {completed}/{total_files}")

        started_at = st.session_state.get("analysis_started_at", "")
        ended_at = st.session_state.get("analysis_ended_at", "")
        if started_at:
            st.caption(f"Started: {started_at}")
        if ended_at:
            st.caption(f"Ended: {ended_at}")
            st.caption(
                f"Duration: {st.session_state.get('analysis_duration_sec', 0.0):.1f} sec"
            )

    # メインエリア - モード別表示
    if st.session_state.mode == "idle":
        show_upload_screen()
    elif st.session_state.mode == "mnv_roi":
        show_scrollfree_mnv_roi_screen()
    elif st.session_state.mode == "mnv_qc":
        show_scrollfree_qc_screen()
    elif st.session_state.mode == "vd_qc":
        show_vd_qc_screen()
    elif st.session_state.mode == "summary":
        show_summary_screen()


if __name__ == "__main__":
    main()
