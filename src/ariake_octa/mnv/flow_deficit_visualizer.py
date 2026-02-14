"""
Flow Deficit Visualizer Module

Flow Deficit領域を3つの同心円リングで色分け表示。
Ring 1: 赤 (0-0.2mm)
Ring 2: 緑 (0.2-0.4mm)
Ring 3: 青 (0.4-0.6mm)

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

from typing import List, Tuple
import logging

import cv2
import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)


class FlowDeficitVisualizer:
    """
    Flow Deficit 3環可視化器

    FD領域を同心円リングごとに色分けして表示。
    ガウシアンブラーで滑らかな表示。
    """

    def __init__(
        self,
        pixel_size_mm: float = 0.003,
        ring_widths_mm: List[float] = None,
        blur_sigma: float = 4.0,
    ):
        """
        Parameters
        ----------
        pixel_size_mm : float
            ピクセルサイズ (mm)
        ring_widths_mm : list of float
            各リングの外側半径 (mm) [ring1, ring2, ring3]
        blur_sigma : float
            ガウシアンブラーのσ (ピクセル)
        """
        self.pixel_size_mm = pixel_size_mm

        if ring_widths_mm is None:
            ring_widths_mm = [0.2, 0.4, 0.6]
        self.ring_widths_mm = ring_widths_mm

        self.blur_sigma = blur_sigma

        # リング半径（ピクセル）
        self.ring_widths_pixels = [int(w / pixel_size_mm) for w in ring_widths_mm]

    def create_fd_visualization(
        self,
        fd_mask: np.ndarray,
        lesion_center: Tuple[float, float],
        background_image: np.ndarray = None,
        roi_mask: np.ndarray = None,
    ) -> np.ndarray:
        """
        Flow Deficit 3環可視化を作成

        【可視化と背景の仕様】
        1. 背景: 必ず4.tif（background_image）を背景画像として使用
        2. 染色: 4.tif内の暗い欠損部（fd_mask）と、物理的拡張で生成された3つの排他的なマスク
           （Mask 1, 2, 3）の論理積をとり、赤・緑・青の色をそれぞれ独立して乗せる
        3. 境界線: 各マスクの外縁を白い不正形な線（cv2.drawContours）で描画

        Parameters
        ----------
        fd_mask : np.ndarray
            Flow Deficitマスク (bool) - 4.tif内の暗い欠損領域
        lesion_center : tuple
            病変中心座標 (center_y, center_x) ピクセル単位（後方互換性のため保持、roi_mask使用時は未使用）
        background_image : np.ndarray, optional
            背景画像（4.tif、グレースケール）- 必ず4.tifを使用
        roi_mask : np.ndarray, optional
            base_roi_mask（3.tifから4.tifに転写されたROIマスク、bool または 0/1 の uint8）
            指定時はROI形状に追従した物理的拡張リングを使用

        Returns
        -------
        np.ndarray
            FD可視化画像 (H×W×3, uint8) - 4.tifを背景とし、不正形な3色の解析結果が乗った画像
        """
        h, w = fd_mask.shape
        center_y, center_x = lesion_center

        # ROIマスクが指定されている場合は形状追従型、そうでなければ正円型
        if roi_mask is not None:
            # ROI形状に追従した膨張リングを作成
            ring_masks, ring_contours = self._create_ring_masks_from_roi(
                roi_mask, self.ring_widths_mm
            )
        else:
            # 後方互換性: 正円リング（既存の動作）
            ring_masks = self._create_ring_masks(
                (h, w), center_y, center_x, self.ring_widths_pixels
            )
            ring_contours = None

        # RGB画像を初期化
        if background_image is not None:
            # 背景画像をRGBに変換
            if len(background_image.shape) == 2:
                fd_image = cv2.cvtColor(background_image, cv2.COLOR_GRAY2BGR)
            else:
                fd_image = background_image.copy()
        else:
            # 黒背景
            fd_image = np.zeros((h, w, 3), dtype=np.uint8)

        # 【可視化の再構築】fd_layer全体を一度(0,0,0)で初期化
        fd_layer = np.zeros((h, w, 3), dtype=np.uint8)

        # 各リングのFD領域を色分け（距離スライスベースの排他的マスクを使用）
        # Ring 1 (Red): dist <= 0.2mm
        mask1 = ring_masks[0]
        fd_in_ring1 = fd_mask & mask1
        if np.any(fd_in_ring1):
            fd_layer[fd_in_ring1] = [0, 0, 255]  # BGR: 赤
            logger.debug(f"Ring 1 (Red): {np.sum(fd_in_ring1)} FD pixels")

        # Ring 2 (Green): 0.2mm < dist <= 0.4mm
        mask2 = ring_masks[1]
        fd_in_ring2 = fd_mask & mask2
        if np.any(fd_in_ring2):
            fd_layer[fd_in_ring2] = [0, 255, 0]  # BGR: 緑
            logger.debug(f"Ring 2 (Green): {np.sum(fd_in_ring2)} FD pixels")

        # Ring 3 (Blue): 0.4mm < dist <= 0.6mm
        mask3 = ring_masks[2]
        fd_in_ring3 = fd_mask & mask3
        if np.any(fd_in_ring3):
            fd_layer[fd_in_ring3] = [255, 0, 0]  # BGR: 青
            logger.debug(f"Ring 3 (Blue): {np.sum(fd_in_ring3)} FD pixels")

        # 【色の混在検証】各チャンネルを個別に確認
        # 各色が独立していることを検証（重複がないことを確認）
        red_pixels = np.sum((fd_layer[:, :, 2] > 0) & (fd_layer[:, :, 0] > 0))  # 赤と青が重複
        green_red_pixels = np.sum((fd_layer[:, :, 1] > 0) & (fd_layer[:, :, 2] > 0))  # 緑と赤が重複
        green_blue_pixels = np.sum((fd_layer[:, :, 1] > 0) & (fd_layer[:, :, 0] > 0))  # 緑と青が重複
        
        logger.debug(
            f"Color overlap check: "
            f"Red-Blue overlap={red_pixels}, "
            f"Green-Red overlap={green_red_pixels}, "
            f"Green-Blue overlap={green_blue_pixels}"
        )
        
        if red_pixels > 0 or green_red_pixels > 0 or green_blue_pixels > 0:
            logger.warning(
                f"⚠ Color overlap detected! "
                f"This indicates a bug in ring mask generation."
            )

        # ガウシアンブラー適用
        if self.blur_sigma > 0:
            fd_layer = cv2.GaussianBlur(fd_layer, (0, 0), self.blur_sigma)

        # 半透明でオーバーレイ
        alpha = 0.6
        fd_image = np.where(
            fd_layer > 0,
            (alpha * fd_layer + (1 - alpha) * fd_image).astype(np.uint8),
            fd_image,
        )

        # リング境界を描画
        if ring_contours is not None:
            # ROI形状追従型: 不正形な境界線を描画
            fd_image = self._draw_ring_boundaries_from_roi(
                fd_image, ring_contours
            )
        else:
            # 後方互換性: 正円境界線
            fd_image = self._draw_ring_boundaries(
                fd_image, center_y, center_x, self.ring_widths_pixels
            )

        return fd_image

    def _create_ring_masks_from_roi(
        self,
        roi_mask: np.ndarray,
        ring_widths_mm: List[float],
    ) -> Tuple[List[np.ndarray], List[List[np.ndarray]]]:
        """
        ROI形状に追従した膨張リングマスクを作成（医学的妥当性を確保）

        【アルゴリズム: Exclusive Doughnut Rings】
        1. base_roi そのものは解析・染色対象から除外する
        2. 距離変換で base_roi からの距離 (px) を算出
        3. XOR的スライスで排他的なドーナツを作成:
           - Mask1 = (dist > 0) AND (dist <= 0.2mm相当px) → Base ROIを明示的に除外
           - Mask2 = (dist > 0.2mm相当px) AND (dist <= 0.4mm相当px)
           - Mask3 = (dist > 0.4mm相当px) AND (dist <= 0.6mm相当px)
        4. 3つのマスクは互いに排他（交差なし）。base_roi はどのマスクにも含まない。

        Parameters
        ----------
        roi_mask : np.ndarray
            base_roi_mask（3.tifから4.tifに転写されたROIマスク、bool または 0/1 の uint8）
        ring_widths_mm : list of float
            各リングの外側までの距離 (mm) [0.2, 0.4, 0.6]

        Returns
        -------
        tuple[list of np.ndarray, list of list of np.ndarray]
            (3つの排他的なリングマスク (bool), 各リングの輪郭リスト)
        """
        # 【ROI転写の確認】base_roi_maskをboolに正規化
        if roi_mask.dtype != bool:
            roi_base = (roi_mask > 0).astype(bool)
        else:
            roi_base = roi_mask.copy()

        # 【物理的拡張】ROI境界から外側への距離を計算
        # scipy.ndimage.distance_transform_edt を使用
        # ROIの補集合（背景）に対して距離変換を適用
        background_mask = (~roi_base).astype(bool)
        # ユークリッド距離変換（ピクセル単位）
        dist = ndimage.distance_transform_edt(background_mask)
        # dist[i,j] = 背景ピクセル(i,j)からROI境界までの距離（ピクセル）
        # ROI内部は dist == 0
        # ROI外側は dist > 0（ROI境界からの距離、ピクセル単位）

        # 【物理計算の再検算】ミリメートルをピクセルに換算
        threshold_02 = 0.2 / self.pixel_size_mm
        threshold_04 = 0.4 / self.pixel_size_mm
        threshold_06 = 0.6 / self.pixel_size_mm

        # デバッグログ: 計算されたピクセル閾値を出力
        logger.debug(
            f"FD Ring thresholds (pixels): "
            f"0.2mm={threshold_02:.2f}, "
            f"0.4mm={threshold_04:.2f}, "
            f"0.6mm={threshold_06:.2f}, "
            f"pixel_size_mm={self.pixel_size_mm:.6f}"
        )
        logger.debug(
            f"Distance transform stats: "
            f"min={np.min(dist):.2f}, max={np.max(dist):.2f}, "
            f"mean={np.mean(dist):.2f}, "
            f"ROI pixels (dist==0)={np.sum(dist == 0)}, "
            f"background pixels={np.sum(dist > 0)}"
        )

        # 【重要】排他的なドーナツ型マスクの生成 (dist > 0 を入れてROI内部を抜く)
        # Ring 1 (Red): ROIの縁から200μmまで（Base ROI本体を除外）
        mask1 = (dist > 0) & (dist <= threshold_02)
        # Ring 2 (Green): 0.2mm < dist <= 0.4mm
        mask2 = (dist > threshold_02) & (dist <= threshold_04)
        # Ring 3 (Blue): 0.4mm < dist <= 0.6mm
        mask3 = (dist > threshold_04) & (dist <= threshold_06)

        ring_masks = [mask1, mask2, mask3]

        # デバッグログ: 各リングのピクセル数を出力
        logger.debug(
            f"Ring mask pixel counts: "
            f"Ring1 (Red)={np.sum(mask1)}, "
            f"Ring2 (Green)={np.sum(mask2)}, "
            f"Ring3 (Blue)={np.sum(mask3)}, "
            f"Total={np.sum(mask1) + np.sum(mask2) + np.sum(mask3)}"
        )

        # 境界線描画用の輪郭: 各リングの外側境界を取得
        ring_contours_list = []
        for threshold in [threshold_02, threshold_04, threshold_06]:
            # 累積領域の輪郭を取得（境界線描画用）
            expanded_mask = roi_base | (dist <= threshold)
            outer_contours, _ = cv2.findContours(
                expanded_mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            ring_contours_list.append(outer_contours)

        return ring_masks, ring_contours_list

    def _create_ring_masks(
        self,
        shape: Tuple[int, int],
        center_y: float,
        center_x: float,
        ring_radii: List[int],
    ) -> List[np.ndarray]:
        """
        同心円リングマスクを作成（後方互換性のため保持）

        Parameters
        ----------
        shape : tuple
            画像サイズ (height, width)
        center_y, center_x : float
            中心座標
        ring_radii : list of int
            各リングの外側半径 (ピクセル)

        Returns
        -------
        list of np.ndarray
            3つのリングマスク (bool)
        """
        h, w = shape
        y_indices, x_indices = np.ogrid[:h, :w]

        distances = np.sqrt((y_indices - center_y) ** 2 + (x_indices - center_x) ** 2)

        # Ring 1: 0 ~ r1
        ring1 = distances <= ring_radii[0]

        # Ring 2: r1 ~ r2
        ring2 = (distances > ring_radii[0]) & (distances <= ring_radii[1])

        # Ring 3: r2 ~ r3
        ring3 = (distances > ring_radii[1]) & (distances <= ring_radii[2])

        return [ring1, ring2, ring3]

    def _draw_ring_boundaries_from_roi(
        self,
        image: np.ndarray,
        ring_contours_list: List[List[np.ndarray]],
        color: Tuple[int, int, int] = (255, 255, 255),  # 白
        thickness: int = 1,
    ) -> np.ndarray:
        """
        ROI形状に追従したリング境界線を描画（不正形な境界）

        Parameters
        ----------
        image : np.ndarray
            BGR画像
        ring_contours_list : list of list of np.ndarray
            各リングの輪郭リスト（各要素はcv2.findContoursの戻り値形式）
        color : tuple
            境界線の色 (B, G, R)
        thickness : int
            境界線の太さ

        Returns
        -------
        np.ndarray
            境界線を追加した画像
        """
        for ring_contours in ring_contours_list:
            if ring_contours:
                cv2.drawContours(
                    image, ring_contours, -1, color, thickness, cv2.LINE_AA
                )
        return image

    def _draw_ring_boundaries(
        self,
        image: np.ndarray,
        center_y: float,
        center_x: float,
        ring_radii: List[int],
        color: Tuple[int, int, int] = (255, 255, 255),  # 白
        thickness: int = 1,
    ) -> np.ndarray:
        """
        リング境界線を描画（後方互換性のため保持: 正円）

        Parameters
        ----------
        image : np.ndarray
            RGB画像
        center_y, center_x : float
            中心座標
        ring_radii : list of int
            リング半径
        color : tuple
            境界線の色 (B, G, R)
        thickness : int
            境界線の太さ

        Returns
        -------
        np.ndarray
            境界線を追加した画像
        """
        center = (int(center_x), int(center_y))

        for radius in ring_radii:
            cv2.circle(image, center, radius, color, thickness, cv2.LINE_AA)

        return image

    def create_with_legend(
        self, fd_visualization: np.ndarray, legend_position: str = "top-right"
    ) -> np.ndarray:
        """
        凡例を追加

        Parameters
        ----------
        fd_visualization : np.ndarray
            FD可視化画像
        legend_position : str
            凡例の位置

        Returns
        -------
        np.ndarray
            凡例付き画像
        """
        image = fd_visualization.copy()
        h, w = image.shape[:2]

        # 凡例テキスト
        legends = [
            ("Ring 1 (0-0.2mm)", (0, 0, 255)),  # 赤
            ("Ring 2 (0.2-0.4mm)", (0, 255, 0)),  # 緑
            ("Ring 3 (0.4-0.6mm)", (255, 0, 0)),  # 青
        ]

        # 位置計算
        margin = 10
        line_height = 25
        box_size = 15

        if legend_position == "top-right":
            start_x = w - 200
            start_y = margin + 20
        elif legend_position == "bottom-right":
            start_y = h - len(legends) * line_height - margin
            start_x = w - 200
        else:
            start_x = w - 200
            start_y = margin + 20

        # 背景矩形
        cv2.rectangle(
            image,
            (start_x - 5, start_y - 15),
            (w - margin, start_y + len(legends) * line_height + 5),
            (0, 0, 0),
            -1,
        )

        # 各凡例を描画
        for i, (text, color) in enumerate(legends):
            y = start_y + i * line_height

            # 色ボックス
            cv2.rectangle(
                image,
                (start_x, y - box_size // 2),
                (start_x + box_size, y + box_size // 2),
                color,
                -1,
            )

            # テキスト
            cv2.putText(
                image,
                text,
                (start_x + box_size + 10, y + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        return image


def create_visualizer(
    pixel_size_mm: float = 0.003, blur_sigma: float = 4.0
) -> FlowDeficitVisualizer:
    """
    デフォルトパラメータで可視化器を作成

    Parameters
    ----------
    pixel_size_mm : float
        ピクセルサイズ (mm)
    blur_sigma : float
        ガウシアンブラーのσ

    Returns
    -------
    FlowDeficitVisualizer
        Flow Deficit可視化器
    """
    return FlowDeficitVisualizer(
        pixel_size_mm=pixel_size_mm,
        ring_widths_mm=[0.2, 0.4, 0.6],
        blur_sigma=blur_sigma,
    )
