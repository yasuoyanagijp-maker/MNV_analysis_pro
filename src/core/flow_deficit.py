"""
Flow Deficit解析モジュール
performFlowDeficitAnalysisImproved に対応
"""

from typing import Dict, List

import cv2
import numpy as np

from .preprocessing import AdaptiveThresholder


class FlowDeficitAnalyzer:
    """
    Flow Deficit解析クラス
    """

    def __init__(
        self,
        mm_per_pixel: float,
        pixel_size_um: float,
        num_rings: int = 3,
        enlarge_step_mm: float = 0.2,
    ):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            ピクセルあたりのmm
        pixel_size_um : float
            ピクセルサイズ（μm）
        num_rings : int
            リング数
        enlarge_step_mm : float
            リングごとの拡大幅（mm）
        """
        self.mm_per_pixel = mm_per_pixel
        self.pixel_size_um = pixel_size_um
        self.num_rings = num_rings
        self.enlarge_step_mm = enlarge_step_mm

    def analyze(
        self,
        image: np.ndarray,
        base_roi_mask: np.ndarray,
        phansalkar_radius: int = 15,
    ) -> Dict[str, any]:
        """
        Flow Deficit解析を実行

        Parameters:
        -----------
        image : np.ndarray
            入力画像（Choriocapillaris層）
        base_roi_mask : np.ndarray
            基準ROIマスク
        phansalkar_radius : int
            Phansalkar二値化の半径

        Returns:
        --------
        results : dict
            Flow Deficit解析結果
        """
        # 二値化（黒がFlow Deficit）
        binary = AdaptiveThresholder.phansalkar(
            image, radius=phansalkar_radius, k=0, r=0
        )

        # 反転（黒=Flow Deficit → 白）
        binary_inverted = 255 - binary

        # リングROIを作成
        ring_masks = self._create_ring_rois(base_roi_mask)

        # 各リングでFlow Deficitを解析
        fd_results = []

        for ring_idx in range(self.num_rings):
            ring_mask = ring_masks[ring_idx]

            ring_result = self._analyze_ring(binary_inverted, ring_mask, ring_idx + 1)

            fd_results.append(ring_result)

        # 結果を統合
        results = {
            "FD_percent_R1": fd_results[0]["percent"],
            "FD_percent_R2": fd_results[1]["percent"],
            "FD_percent_R3": fd_results[2]["percent"],
            "FD_average_area_R1": fd_results[0]["average_area"],
            "FD_average_area_R2": fd_results[1]["average_area"],
            "FD_average_area_R3": fd_results[2]["average_area"],
            "FD_number_R1": fd_results[0]["number"],
            "FD_number_R2": fd_results[1]["number"],
            "FD_number_R3": fd_results[2]["number"],
            "FD_density_R1": fd_results[0]["density"],
            "FD_density_R2": fd_results[1]["density"],
            "FD_density_R3": fd_results[2]["density"],
            "binary_inverted": binary_inverted,
            "ring_masks": ring_masks,
        }

        return results

    def _create_ring_rois(self, base_roi_mask: np.ndarray) -> List[np.ndarray]:
        """
        同心円リングROIを作成

        Parameters:
        -----------
        base_roi_mask : np.ndarray
            基準ROIマスク

        Returns:
        --------
        ring_masks : list of np.ndarray
            リングマスクのリスト
        """
        enlarge_pixels = int(self.enlarge_step_mm / self.mm_per_pixel)

        # 基準ROIの輪郭を取得
        contours, _ = cv2.findContours(
            base_roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if len(contours) == 0:
            # フォールバック：全体をリングとして扱う
            h, w = base_roi_mask.shape
            ring_masks = [base_roi_mask.copy() for _ in range(self.num_rings)]
            return ring_masks

        ring_masks = []
        previous_mask = base_roi_mask.copy()

        for ring_idx in range(self.num_rings):
            # 拡大量
            enlarge_amount = (ring_idx + 1) * enlarge_pixels

            # 拡大されたマスクを作成
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * enlarge_amount + 1, 2 * enlarge_amount + 1),
            )

            enlarged_mask = cv2.dilate(base_roi_mask, kernel, iterations=1)

            # リングマスク = 拡大マスク - 前のマスク
            if ring_idx == 0:
                ring_mask = base_roi_mask.copy()
            else:
                ring_mask = cv2.subtract(enlarged_mask, previous_mask)

            ring_masks.append(ring_mask)
            previous_mask = enlarged_mask.copy()

        return ring_masks

    def _analyze_ring(
        self,
        binary_inverted: np.ndarray,
        ring_mask: np.ndarray,
        ring_number: int,
    ) -> Dict[str, float]:
        """
        1つのリングでFlow Deficitを解析

        Parameters:
        -----------
        binary_inverted : np.ndarray
            反転された二値画像（白=Flow Deficit）
        ring_mask : np.ndarray
            リングマスク
        ring_number : int
            リング番号

        Returns:
        --------
        result : dict
            解析結果
        """
        # リング領域のみを抽出
        ring_region = cv2.bitwise_and(binary_inverted, ring_mask)

        # リング面積を計算
        ring_area_pixels = np.sum(ring_mask > 0)
        ring_area_mm2 = ring_area_pixels * (self.mm_per_pixel**2)

        if ring_area_mm2 == 0:
            return {"percent": 0, "average_area": 0, "number": 0, "density": 0}

        # Flow Deficitの白ピクセル数
        fd_pixels = np.sum(ring_region > 0)
        fd_area_mm2 = fd_pixels * (self.mm_per_pixel**2)
        fd_area_um2 = fd_area_mm2 * 1e6

        # Flow Deficitのパーティクル解析
        if fd_pixels > 0:
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                ring_region, connectivity=8
            )

            # 背景を除く
            num_particles = num_labels - 1

            if num_particles > 0:
                # 各パーティクルの面積
                total_fd_area_um2 = 0
                for i in range(1, num_labels):
                    particle_area_pixels = stats[i, cv2.CC_STAT_AREA]
                    particle_area_mm2 = particle_area_pixels * (self.mm_per_pixel**2)
                    particle_area_um2 = particle_area_mm2 * 1e6
                    total_fd_area_um2 += particle_area_um2

                average_area_um2 = total_fd_area_um2 / num_particles
            else:
                num_particles = 1 if fd_pixels > 0 else 0
                total_fd_area_um2 = fd_area_um2
                average_area_um2 = total_fd_area_um2
        else:
            num_particles = 0
            total_fd_area_um2 = 0
            average_area_um2 = 0

        # Flow Deficit割合
        ring_area_um2 = ring_area_mm2 * 1e6
        if ring_area_um2 > 0:
            fd_percent = (total_fd_area_um2 / ring_area_um2) * 100
        else:
            fd_percent = 0

        # 密度
        if ring_area_mm2 > 0:
            fd_density = num_particles / ring_area_mm2
        else:
            fd_density = 0

        result = {
            "percent": fd_percent,
            "average_area": average_area_um2,
            "number": num_particles,
            "density": fd_density,
        }

        return result

    def create_visualization(
        self, binary_inverted: np.ndarray, ring_masks: List[np.ndarray]
    ) -> np.ndarray:
        """
        Flow Deficitの可視化画像を作成

        Parameters:
        -----------
        binary_inverted : np.ndarray
            反転された二値画像
        ring_masks : list of np.ndarray
            リングマスクのリスト

        Returns:
        --------
        visualization : np.ndarray
            可視化画像（RGB）
        """
        # RGB画像を作成
        h, w = binary_inverted.shape
        visualization = np.zeros((h, w, 3), dtype=np.uint8)

        # 元の二値画像を赤チャンネルに
        visualization[:, :, 2] = binary_inverted  # Red

        # 緑チャンネル（Ring 1-3を削除）
        green_channel = binary_inverted.copy()
        for ring_idx in range(min(3, len(ring_masks))):
            ring_mask = ring_masks[ring_idx]
            green_channel = cv2.bitwise_and(green_channel, cv2.bitwise_not(ring_mask))
        visualization[:, :, 1] = green_channel  # Green

        # 青チャンネル（元の二値画像）
        visualization[:, :, 0] = binary_inverted  # Blue

        return visualization
