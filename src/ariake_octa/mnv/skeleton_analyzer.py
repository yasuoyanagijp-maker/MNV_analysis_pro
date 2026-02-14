"""
Skeleton Analyzer

血管スケルトンの解析を行うモジュール。
分岐点、端点、ループ、トルトゥオシティ、フラクタル次元を計算。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

import logging
import time
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)
from scipy import ndimage
from skimage import measure, morphology


class SkeletonAnalyzer:
    """
    血管スケルトン解析器

    二値化画像からスケルトンを抽出し、
    血管構造の幾何学的特徴を計算する。
    """

    def __init__(self, pixel_size_mm: float = 0.003):
        """
        Parameters
        ----------
        pixel_size_mm : float
            1ピクセルのサイズ (mm)
        """
        self.pixel_size_mm = pixel_size_mm

    def analyze(
        self,
        binary_image: np.ndarray,
        roi_mask: Optional[np.ndarray] = None,
        compute_loops: bool = True,
    ) -> Dict:
        """
        スケルトン解析を実行

        Parameters
        ----------
        binary_image : np.ndarray
            二値化画像 (0 or 255)
        roi_mask : np.ndarray, optional
            関心領域マスク (bool)
        compute_loops : bool, optional
            True でループ数(num_loops)を計算。VD等で不要な場合は False で約13秒/枚短縮。

        Returns
        -------
        dict
            解析結果
            - skeleton: スケルトン画像 (bool)
            - num_branches: 分岐数
            - num_junctions: 分岐点数
            - num_endpoints: 端点数
            - num_loops: ループ数 (compute_loops=False のときは 0)
            - total_length_mm: 総血管長 (mm)
            - average_branch_length_mm: 平均分岐長 (mm)
            - tortuosity_mean: 平均トルトゥオシティ
            - tortuosity_std: トルトゥオシティ標準偏差
            - fractal_dimension: フラクタル次元
        """
        # 二値化
        binary = (binary_image > 127).astype(np.uint8)

        # ROIマスク適用
        if roi_mask is not None:
            binary = binary * roi_mask.astype(np.uint8)

        # スケルトン化
        t0 = time.perf_counter()
        skeleton = morphology.skeletonize(binary > 0)
        logger.info(
            "[VD timing]       skel_analyze_skeletonize: %.3f s",
            time.perf_counter() - t0,
        )

        if not np.any(skeleton):
            return self._empty_result()

        # 各種特徴の検出
        t0 = time.perf_counter()
        junctions, endpoints = self._detect_features(skeleton)
        logger.info(
            "[VD timing]       skel_analyze_detect_features: %.3f s",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()
        branches = self._extract_branches(skeleton, junctions, endpoints)
        logger.info(
            "[VD timing]       skel_analyze_extract_branches: %.3f s",
            time.perf_counter() - t0,
        )

        if compute_loops:
            t0 = time.perf_counter()
            loops = self._count_loops(skeleton)
            logger.info(
                "[VD timing]       skel_analyze_count_loops: %.3f s",
                time.perf_counter() - t0,
            )
        else:
            loops = 0

        # メトリクス計算
        total_length_pixels = np.sum(skeleton)
        total_length_mm = total_length_pixels * self.pixel_size_mm

        # 分岐長統計
        if branches:
            branch_lengths = [b["length_mm"] for b in branches]
            average_branch_length = np.mean(branch_lengths)
        else:
            average_branch_length = 0.0

        # トルトゥオシティ
        t0 = time.perf_counter()
        tortuosities = self._compute_tortuosity(branches)
        if tortuosities:
            tortuosity_mean = np.mean(tortuosities)
            tortuosity_std = np.std(tortuosities)
        else:
            tortuosity_mean = 1.0
            tortuosity_std = 0.0
        logger.info(
            "[VD timing]       skel_analyze_tortuosity: %.3f s",
            time.perf_counter() - t0,
        )

        # フラクタル次元
        t0 = time.perf_counter()
        fractal_dim = self._compute_fractal_dimension(skeleton)
        logger.info(
            "[VD timing]       skel_analyze_fractal_dimension: %.3f s",
            time.perf_counter() - t0,
        )

        return {
            "skeleton": skeleton,
            "num_branches": len(branches),
            "num_junctions": len(junctions),
            "num_endpoints": len(endpoints),
            "num_loops": loops,
            "total_length_mm": total_length_mm,
            "total_length_pixels": int(total_length_pixels),
            "average_branch_length_mm": average_branch_length,
            "tortuosity_mean": tortuosity_mean,
            "tortuosity_std": tortuosity_std,
            "fractal_dimension": fractal_dim,
            "branches": branches,
            "junctions": junctions,
            "endpoints": endpoints,
        }

    def _detect_features(
        self, skeleton: np.ndarray
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """
        分岐点と端点を検出

        Parameters
        ----------
        skeleton : np.ndarray
            スケルトン画像 (bool)

        Returns
        -------
        tuple
            (junctions, endpoints)
            各要素は (y, x) のリスト
        """
        # 8近傍の隣接ピクセル数をカウント
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)

        neighbor_count = ndimage.convolve(
            skeleton.astype(np.uint8), kernel, mode="constant", cval=0
        )

        # スケルトンピクセルのみ考慮
        neighbor_count = neighbor_count * skeleton.astype(np.uint8)

        # 端点: 隣接が1つ
        endpoints = np.argwhere(neighbor_count == 1)
        endpoints = [(int(y), int(x)) for y, x in endpoints]

        # 分岐点: 隣接が3つ以上
        junctions = np.argwhere(neighbor_count >= 3)
        junctions = [(int(y), int(x)) for y, x in junctions]

        return junctions, endpoints

    def _extract_branches(
        self,
        skeleton: np.ndarray,
        junctions: List[Tuple[int, int]],
        endpoints: List[Tuple[int, int]],
    ) -> List[Dict]:
        """
        スケルトンから分岐を抽出

        Parameters
        ----------
        skeleton : np.ndarray
            スケルトン画像
        junctions : list
            分岐点リスト
        endpoints : list
            端点リスト

        Returns
        -------
        list of dict
            分岐情報のリスト
            各要素: {'points': [...], 'length_mm': float}
        """
        # 分岐点を除去したスケルトン
        skeleton_copy = skeleton.copy()
        for y, x in junctions:
            skeleton_copy[y, x] = False

        # 連結成分ラベリング
        labeled = measure.label(skeleton_copy, connectivity=2)

        branches = []
        for region in measure.regionprops(labeled):
            coords = region.coords  # (y, x) のリスト

            if len(coords) < 2:
                continue

            # パス長計算（ピクセル間距離の合計）
            length_pixels = self._compute_path_length(coords)
            length_mm = length_pixels * self.pixel_size_mm

            branches.append(
                {
                    "points": coords,
                    "length_pixels": length_pixels,
                    "length_mm": length_mm,
                }
            )

        return branches

    def _compute_path_length(self, coords: np.ndarray) -> float:
        """
        座標列のパス長を計算

        Parameters
        ----------
        coords : np.ndarray
            座標配列 (N, 2)

        Returns
        -------
        float
            パス長（ピクセル単位）
        """
        if len(coords) < 2:
            return 0.0

        # 座標を順序づけ（最も近い点を繋ぐ）
        ordered = self._order_points(coords)

        # 連続点間の距離を合計
        diffs = np.diff(ordered, axis=0)
        distances = np.sqrt(np.sum(diffs**2, axis=1))

        return np.sum(distances)

    def _order_points(self, coords: np.ndarray) -> np.ndarray:
        """
        座標を順序づける（最近傍法）

        Parameters
        ----------
        coords : np.ndarray
            座標配列 (N, 2)

        Returns
        -------
        np.ndarray
            順序づけられた座標
        """
        if len(coords) < 2:
            return coords

        # 簡易実装: 開始点から最近傍を順次選択
        ordered = [coords[0]]
        remaining = list(coords[1:])

        while remaining:
            last_point = ordered[-1]
            distances = [np.linalg.norm(p - last_point) for p in remaining]
            min_idx = np.argmin(distances)
            ordered.append(remaining.pop(min_idx))

        return np.array(ordered)

    def _compute_tortuosity(self, branches: List[Dict]) -> List[float]:
        """
        トルトゥオシティを計算

        Parameters
        ----------
        branches : list
            分岐情報のリスト

        Returns
        -------
        list
            各分岐のトルトゥオシティ
            tortuosity = actual_length / straight_distance
        """
        tortuosities = []

        for branch in branches:
            coords = branch["points"]

            if len(coords) < 2:
                continue

            # 実際のパス長
            actual_length = branch["length_pixels"]

            # 直線距離
            start = coords[0]
            end = coords[-1]
            straight_distance = np.linalg.norm(end - start)

            if straight_distance > 0:
                tortuosity = actual_length / straight_distance
                tortuosities.append(tortuosity)

        return tortuosities

    def _count_loops(self, skeleton: np.ndarray) -> int:
        """
        ループ数を計算（オイラー数を使用）

        Parameters
        ----------
        skeleton : np.ndarray
            スケルトン画像

        Returns
        -------
        int
            ループ数
        """
        # オイラー数 = 端点数 - 分岐点数 - ループ数
        # ループ数 = 端点数 - 分岐点数 - オイラー数

        # 連結成分のオイラー数を計算
        labeled = measure.label(skeleton, connectivity=2)
        num_components = labeled.max()

        # 各連結成分のオイラー数
        euler_numbers = []
        for i in range(1, num_components + 1):
            component = labeled == i

            # skimage の euler_number は 2D で定義
            # euler = vertices - edges + faces
            # スケルトンでは faces=0 なので
            # euler ≈ endpoints - junctions

            try:
                euler = measure.euler_number(component, connectivity=2)
                euler_numbers.append(euler)
            except Exception:
                euler_numbers.append(0)

        # ループ数 = 1 - オイラー数（単一連結成分の場合）
        total_loops = sum([max(1 - e, 0) for e in euler_numbers])

        return int(total_loops)

    def _compute_fractal_dimension(self, skeleton: np.ndarray) -> float:
        """
        Box-counting法でフラクタル次元を計算

        Parameters
        ----------
        skeleton : np.ndarray
            スケルトン画像

        Returns
        -------
        float
            フラクタル次元
        """
        # Box sizes (powers of 2)
        sizes = np.array([2, 4, 8, 16, 32, 64])
        sizes = sizes[sizes < min(skeleton.shape) / 4]

        if len(sizes) < 2:
            return 1.0

        counts = []

        for size in sizes:
            # グリッドに分割してカウント
            n_boxes_y = int(np.ceil(skeleton.shape[0] / size))
            n_boxes_x = int(np.ceil(skeleton.shape[1] / size))

            count = 0
            for i in range(n_boxes_y):
                for j in range(n_boxes_x):
                    y_start = i * size
                    y_end = min((i + 1) * size, skeleton.shape[0])
                    x_start = j * size
                    x_end = min((j + 1) * size, skeleton.shape[1])

                    box = skeleton[y_start:y_end, x_start:x_end]

                    if np.any(box):
                        count += 1

            counts.append(count)

        # 線形回帰で傾きを求める
        # log(N) = -D * log(size) + const
        # D = fractal dimension

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            log_sizes = np.log(sizes)
            log_counts = np.log(counts)

            # 最小二乗法
            coeffs = np.polyfit(log_sizes, log_counts, 1)
            fractal_dim = -coeffs[0]

        # 妥当な範囲にクリップ (1.0 ~ 2.0)
        fractal_dim = np.clip(fractal_dim, 1.0, 2.0)

        return float(fractal_dim)

    def _empty_result(self) -> Dict:
        """
        空の結果を返す

        Returns
        -------
        dict
            デフォルト値の結果
        """
        return {
            "skeleton": np.array([]),
            "num_branches": 0,
            "num_junctions": 0,
            "num_endpoints": 0,
            "num_loops": 0,
            "total_length_mm": 0.0,
            "total_length_pixels": 0,
            "average_branch_length_mm": 0.0,
            "tortuosity_mean": 1.0,
            "tortuosity_std": 0.0,
            "fractal_dimension": 1.0,
            "branches": [],
            "junctions": [],
            "endpoints": [],
        }


def create_analyzer(pixel_size_mm: float = 0.003) -> SkeletonAnalyzer:
    """
    デフォルトパラメータで解析器を作成

    Parameters
    ----------
    pixel_size_mm : float
        ピクセルサイズ (mm)

    Returns
    -------
    SkeletonAnalyzer
        スケルトン解析器
    """
    return SkeletonAnalyzer(pixel_size_mm=pixel_size_mm)
