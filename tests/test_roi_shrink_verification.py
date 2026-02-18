"""
形状維持の縮小（ROI shape-preserving shrink）の検証テスト。

create_adaptive_masks が「元のROIの形を変えずに内側へ縮小」していることを
最小限のアサーションで確認する。指定マスク画像で実行可能。
処理したマスク（ROI / center / periphery）は OUTPUT_DIR に PNG で保存する。

実行方法（仮想環境を有効化した上で）:
  cd /Users/yy/retinal-analysis-pro
  PYTHONPATH=src pytest tests/test_roi_shrink_verification.py -v -s
  または
  PYTHONPATH=src python tests/test_roi_shrink_verification.py
"""

import sys
from pathlib import Path

import numpy as np

# プロジェクトルートの src を path に追加
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import pytest
except ImportError:
    pytest = None

# 検証用マスク画像（存在しない場合はスキップ）
MASK_IMAGE_PATH = Path("/Users/yy/Desktop/93413404_IVF_before_OS.jpg_ColorMask.png")
# 処理したマスクの保存先
OUTPUT_DIR = Path("/Users/yy/Desktop/名称未設定フォルダ")


def _load_roi_mask(path: Path) -> np.ndarray:
    """PNGマスクを読み込み、二値 (H,W) bool で返す。"""
    import cv2

    raw = cv2.imread(str(path))
    if raw is None:
        raise FileNotFoundError(f"Cannot load image: {path}")
    if raw.ndim == 3:
        # いずれかのチャンネルが非ゼロなら ROI
        roi = np.any(raw > 0, axis=2)
    else:
        roi = raw > 0
    return roi.astype(bool)


def _roi_centroid_and_radius(roi: np.ndarray) -> tuple:
    """ROI の重心 (cy, cx) と面積から推定した半径（ピクセル）を返す。"""
    ys, xs = np.where(roi)
    if len(ys) == 0:
        return 0.0, 0.0, 0.0
    cy, cx = float(ys.mean()), float(xs.mean())
    area = int(np.sum(roi))
    radius = np.sqrt(area / np.pi) if area > 0 else 0.0
    return cy, cx, radius


def _save_masks(
    out_dir: Path,
    roi_mask: np.ndarray,
    center_mask: np.ndarray,
    periphery_mask: np.ndarray,
    prefix: str = "",
) -> None:
    """処理したマスクを PNG で保存する。center=赤・periphery=緑のオーバーレイも保存。"""
    import cv2

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _to_uint8(m: np.ndarray) -> np.ndarray:
        return (np.asarray(m, dtype=bool).astype(np.uint8)) * 255

    cv2.imwrite(
        str(out_dir / f"{prefix}roi_mask.png"),
        _to_uint8(roi_mask),
    )
    cv2.imwrite(
        str(out_dir / f"{prefix}center_mask.png"),
        _to_uint8(center_mask),
    )
    cv2.imwrite(
        str(out_dir / f"{prefix}periphery_mask.png"),
        _to_uint8(periphery_mask),
    )
    # オーバーレイ: center=赤, periphery=緑 (BGR)
    h, w = roi_mask.shape
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[_to_uint8(center_mask) > 0] = [0, 0, 255]  # BGR red
    overlay[_to_uint8(periphery_mask) > 0] = [0, 255, 0]  # BGR green
    cv2.imwrite(str(out_dir / f"{prefix}overlay_center_periphery.png"), overlay)


if pytest is not None:

    @pytest.fixture(scope="module")
    def roi_mask():
        """検証用マスク画像を読み込み、二値 ROI を返す。ファイルが無い場合はスキップ。"""
        if not MASK_IMAGE_PATH.exists():
            pytest.skip(f"Mask image not found: {MASK_IMAGE_PATH}")
        return _load_roi_mask(MASK_IMAGE_PATH)

    @pytest.fixture(scope="module")
    def analyzer():
        """RegionalAnalyzer のインスタンス（create_adaptive_masks 用）。"""
        from ariake_octa.mnv.regional_analyzer import RegionalAnalyzer

        return RegionalAnalyzer(center_radius_mm=0.5, pixel_size_mm=0.003)

    def test_create_adaptive_masks_shape_preserving_shrink(roi_mask, analyzer):
        """
        形状維持の縮小が正しく機能しているか検証する。

        - center は ROI の部分集合
        - periphery は ROI の部分集合
        - center ∩ periphery = ∅
        - center ∪ periphery = ROI（完全な分割）
        - shrink_pixels > 0 のとき center の面積 < ROI の面積（縮小されている）
        - center が空でない（十分な ROI と適度な shrink の場合）
        """
        h, w = roi_mask.shape
        cy, cx, estimated_radius = _roi_centroid_and_radius(roi_mask)
        assert estimated_radius > 0, "ROI has no area"

        # 既存呼び出しと同様: effective_center_radius を「境界からの距離」として使用
        if estimated_radius < 20:
            effective_center_radius = estimated_radius * 0.4
        else:
            effective_center_radius = estimated_radius / 3.0
        effective_center_radius = max(1.0, effective_center_radius)  # 少なくとも1px縮小

        center_mask, periphery_mask = analyzer.create_adaptive_masks(
            (h, w), roi_mask, (cy, cx), effective_center_radius
        )

        roi_binary = roi_mask.astype(bool)
        center_bool = np.asarray(center_mask, dtype=bool)
        periphery_bool = np.asarray(periphery_mask, dtype=bool)

        # center は ROI の部分集合
        assert np.all(np.logical_or(~center_bool, roi_binary)), (
            "center must be contained in ROI"
        )

        # periphery は ROI の部分集合
        assert np.all(np.logical_or(~periphery_bool, roi_binary)), (
            "periphery must be contained in ROI"
        )

        # center と periphery は disjoint
        assert not np.any(center_bool & periphery_bool), (
            "center and periphery must be disjoint"
        )

        # center ∪ periphery = ROI
        union = center_bool | periphery_bool
        assert np.all(union == roi_binary), (
            "center ∪ periphery must equal ROI"
        )

        # 縮小されている: center の面積 < ROI の面積
        roi_area = np.sum(roi_binary)
        center_area = np.sum(center_bool)
        periphery_area = np.sum(periphery_bool)
        assert center_area < roi_area, (
            f"center must be smaller than ROI (center={center_area}, roi={roi_area})"
        )
        assert center_area + periphery_area == roi_area, (
            "center + periphery pixel counts must sum to ROI"
        )

        # フォールバックにより細長いROIでも center は空にならない
        assert center_area > 0, (
            "center should be non-empty (shape-preserving shrink with fallback)"
        )

        # 処理したマスクを保存
        _save_masks(
            OUTPUT_DIR,
            roi_mask,
            center_bool,
            periphery_bool,
            prefix="test_shape_preserving_",
        )

    def test_shrink_zero_returns_full_roi_as_center(roi_mask, analyzer):
        """effective_center_radius=0 のとき center=ROI, periphery=空 となることを確認。"""
        h, w = roi_mask.shape
        cy, cx, _ = _roi_centroid_and_radius(roi_mask)

        center_mask, periphery_mask = analyzer.create_adaptive_masks(
            (h, w), roi_mask, (cy, cx), 0.0
        )

        assert np.all(center_mask.astype(bool) == roi_mask.astype(bool)), (
            "shrink=0: center should equal ROI"
        )
        assert np.sum(periphery_mask) == 0, "shrink=0: periphery should be empty"

        # shrink=0 の結果も保存
        _save_masks(
            OUTPUT_DIR,
            roi_mask,
            center_mask.astype(bool),
            periphery_mask.astype(bool),
            prefix="test_shrink_zero_",
        )


def _run_verification_standalone():
    """pytest なしで同じ検証を実行（__main__ 用）。"""
    if not MASK_IMAGE_PATH.exists():
        print(f"Skip: mask image not found: {MASK_IMAGE_PATH}")
        return 1
    # ariake_octa パッケージ経由だと tifffile 等が必須になるため、モジュールを直接読み込む
    _mnv_dir = SRC / "ariake_octa" / "mnv"
    if str(_mnv_dir) not in sys.path:
        sys.path.insert(0, str(_mnv_dir))
    from regional_analyzer import RegionalAnalyzer

    roi_mask = _load_roi_mask(MASK_IMAGE_PATH)
    h, w = roi_mask.shape
    cy, cx, estimated_radius = _roi_centroid_and_radius(roi_mask)
    print(f"ROI: shape={roi_mask.shape}, area={np.sum(roi_mask)}, "
          f"estimated_radius={estimated_radius:.1f} px, centroid=({cy:.1f},{cx:.1f})")

    if estimated_radius <= 0:
        print("FAIL: ROI has no area")
        return 1

    if estimated_radius < 20:
        effective_center_radius = estimated_radius * 0.4
    else:
        effective_center_radius = estimated_radius / 3.0
    effective_center_radius = max(1.0, effective_center_radius)
    print(f"effective_center_radius (shrink px): {effective_center_radius:.1f}")

    analyzer = RegionalAnalyzer(center_radius_mm=0.5, pixel_size_mm=0.003)
    center_mask, periphery_mask = analyzer.create_adaptive_masks(
        (h, w), roi_mask, (cy, cx), effective_center_radius
    )
    center_bool = np.asarray(center_mask, dtype=bool)
    periphery_bool = np.asarray(periphery_mask, dtype=bool)
    roi_binary = roi_mask.astype(bool)

    errors = []
    if not np.all(np.logical_or(~center_bool, roi_binary)):
        errors.append("center must be contained in ROI")
    if not np.all(np.logical_or(~periphery_bool, roi_binary)):
        errors.append("periphery must be contained in ROI")
    if np.any(center_bool & periphery_bool):
        errors.append("center and periphery must be disjoint")
    if not np.all((center_bool | periphery_bool) == roi_binary):
        errors.append("center ∪ periphery must equal ROI")
    roi_area = int(np.sum(roi_binary))
    center_area = int(np.sum(center_bool))
    periphery_area = int(np.sum(periphery_bool))
    if center_area >= roi_area:
        errors.append(f"center must be smaller than ROI (center={center_area}, roi={roi_area})")
    if center_area + periphery_area != roi_area:
        errors.append("center + periphery pixel counts must sum to ROI")
    if center_area == 0:
        errors.append("center must be non-empty (shape-preserving shrink with fallback)")

    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print("OK: shape-preserving shrink verified.")
    print(f"  center={center_area} px, periphery={periphery_area} px, roi={roi_area} px")
    _save_masks(
        OUTPUT_DIR,
        roi_mask,
        center_bool,
        periphery_bool,
        prefix="standalone_",
    )
    print(f"  Saved masks to: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    if pytest is not None:
        sys.exit(pytest.main([__file__, "-v", "-s"]))
    sys.exit(_run_verification_standalone())
