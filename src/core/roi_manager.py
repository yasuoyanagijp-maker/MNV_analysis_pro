"""
ROI管理モジュール
半自動ROI検出とROI修正
"""

from typing import Dict, Optional, Tuple

import cv2
import numpy as np


class ROIDetector:
    """
    ROI検出クラス
    ROI_semiauto_improved に対応
    """

    def __init__(self):
        self.saved_roi = None
        self.roi_type = None

    def detect_roi_interactive(self, image: np.ndarray) -> Tuple[np.ndarray, str]:
        """
        対話的にROIを検出（GUI環境用）

        Parameters:
        -----------
        image : np.ndarray
            入力画像

        Returns:
        --------
        roi_mask : np.ndarray
            ROIマスク
        roi_type : str
            ROIタイプ（'polygon', 'freehand'）
        """
        # 実際のGUI実装ではここでユーザー入力を受け取る
        # この実装では自動検出のフォールバックを提供
        print("Interactive ROI detection not implemented in CLI mode.")
        print("Using automatic detection...")

        return self.detect_roi_automatic(image)

    def detect_roi_automatic(
        self, image: np.ndarray, method: str = "threshold"
    ) -> Tuple[np.ndarray, str]:
        """
        自動的にROIを検出

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        method : str
            検出方法（'threshold', 'edge', 'contour'）

        Returns:
        --------
        roi_mask : np.ndarray
            ROIマスク
        roi_type : str
            ROIタイプ
        """
        h, w = image.shape

        if method == "threshold":
            # 閾値ベースの検出
            _, binary = cv2.threshold(
                image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            # 最大の連結成分を取得
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                binary, connectivity=8
            )

            if num_labels > 1:
                # 最大の成分（背景を除く）
                largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
                roi_mask = (labels == largest_label).astype(np.uint8) * 255
            else:
                # フォールバック：中心の円形ROI
                roi_mask = self._create_circular_roi(h, w)

        elif method == "edge":
            # エッジベースの検出
            edges = cv2.Canny(image, 50, 150)

            # 輪郭検出
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if len(contours) > 0:
                # 最大の輪郭
                largest_contour = max(contours, key=cv2.contourArea)
                roi_mask = np.zeros((h, w), dtype=np.uint8)
                cv2.drawContours(roi_mask, [largest_contour], -1, 255, -1)
            else:
                roi_mask = self._create_circular_roi(h, w)

        else:  # 'contour'
            # ガウシアンブラー + 輪郭検出
            blurred = cv2.GaussianBlur(image, (5, 5), 0)
            _, binary = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if len(contours) > 0:
                largest_contour = max(contours, key=cv2.contourArea)
                roi_mask = np.zeros((h, w), dtype=np.uint8)
                cv2.drawContours(roi_mask, [largest_contour], -1, 255, -1)
            else:
                roi_mask = self._create_circular_roi(h, w)

        return roi_mask, "polygon"

    def _create_circular_roi(self, height: int, width: int) -> np.ndarray:
        """
        デフォルトの円形ROIを作成

        Parameters:
        -----------
        height : int
            画像の高さ
        width : int
            画像の幅

        Returns:
        --------
        roi_mask : np.ndarray
            円形ROIマスク
        """
        center_x = width // 2
        center_y = height // 2
        radius = min(width, height) // 3

        roi_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.circle(roi_mask, (center_x, center_y), radius, 255, -1)

        return roi_mask

    def save_roi(self, roi_mask: np.ndarray, roi_type: str):
        """
        ROIを保存（次回使用のため）

        Parameters:
        -----------
        roi_mask : np.ndarray
            ROIマスク
        roi_type : str
            ROIタイプ
        """
        self.saved_roi = roi_mask.copy()
        self.roi_type = roi_type

    def get_saved_roi(self) -> Optional[Tuple[np.ndarray, str]]:
        """
        保存されたROIを取得

        Returns:
        --------
        roi_mask : np.ndarray or None
        roi_type : str or None
        """
        if self.saved_roi is not None:
            return self.saved_roi.copy(), self.roi_type
        return None


class ROIModifier:
    """
    ROI修正クラス
    ROI_modify に対応
    """

    def __init__(
        self,
        iterations: int = 2,
        search_radius: int = 2,
        angle_threshold: float = 0.8,
        fast_mode: bool = True,
    ):
        """
        Parameters:
        -----------
        iterations : int
            反復回数（デフォルト: 2、高速化）
        search_radius : int
            探索半径（デフォルト: 2、高速化）
        angle_threshold : float
            角度閾値（ラジアン）
        fast_mode : bool
            高速モードを使用（デフォルト: True）
        """
        self.iterations = iterations
        self.search_radius = search_radius
        self.angle_threshold = angle_threshold
        self.fast_mode = fast_mode

    def modify_roi(self, image: np.ndarray, roi_mask: np.ndarray) -> np.ndarray:
        """
        ROIを修正

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        roi_mask : np.ndarray
            元のROIマスク

        Returns:
        --------
        modified_mask : np.ndarray
            修正されたROIマスク
        """
        # 輪郭を取得
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )

        if len(contours) == 0:
            return roi_mask

        # 最大の輪郭を取得
        contour = max(contours, key=cv2.contourArea)

        # 座標を抽出
        points = contour.squeeze()

        if len(points.shape) == 1:
            points = points.reshape(-1, 2)

        # 重心を計算
        centroid_x = points[:, 0].mean()
        centroid_y = points[:, 1].mean()

        # 角度でソート
        angles = np.arctan2(points[:, 1] - centroid_y, points[:, 0] - centroid_x)
        sorted_indices = np.argsort(angles)
        sorted_points = points[sorted_indices]

        # ROI修正の反復
        if self.fast_mode:
            # 高速モード: 簡易的な修正のみ
            modified_points = self._fast_modification(
                image, sorted_points, centroid_x, centroid_y
            )
        else:
            # 通常モード: 詳細な修正
            modified_points = self._iterative_modification(
                image, sorted_points, centroid_x, centroid_y
            )

        # 平滑化
        smoothed_points = self._smooth_points(modified_points)

        # 重複点を除去
        unique_points = self._remove_duplicate_points(smoothed_points)

        # 新しいマスクを作成
        modified_mask = np.zeros_like(roi_mask)
        cv2.fillPoly(modified_mask, [unique_points.astype(np.int32)], 255)

        return modified_mask

    def modify_roi_get_contour(
        self,
        image: np.ndarray,
        contour: np.ndarray,
        iterations: int = 2,
        search_radius: int = 2,
        angle_threshold: float = 0.8,
    ) -> np.ndarray:
        """
        ROI輪郭を修正して修正後の輪郭を返す

        Parameters:
        -----------
        image : np.ndarray
            入力画像 (グレースケール)
        contour : np.ndarray
            入力輪郭 (OpenCV形式)
        iterations : int
            反復回数
        search_radius : int
            探索半径
        angle_threshold : float
            角度閾値

        Returns:
        --------
        modified_contour : np.ndarray
            修正された輪郭 (OpenCV形式)
        """
        # Override instance params with caller's values
        self.iterations = iterations
        self.search_radius = search_radius
        self.angle_threshold = angle_threshold

        # Build a mask from the contour
        h, w = image.shape[:2]
        roi_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(roi_mask, [contour], -1, 255, -1)

        # Ensure image is grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Run the existing modify_roi pipeline
        modified_mask = self.modify_roi(gray, roi_mask)

        # Extract contour from modified mask
        contours, _ = cv2.findContours(
            modified_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if len(contours) == 0:
            return contour  # fallback to original

        return max(contours, key=cv2.contourArea)

    def _iterative_modification(
        self,
        image: np.ndarray,
        points: np.ndarray,
        centroid_x: float,
        centroid_y: float,
    ) -> np.ndarray:
        """
        反復的な点の修正

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        points : np.ndarray
            点の配列 (N, 2)
        centroid_x, centroid_y : float
            重心座標

        Returns:
        --------
        modified_points : np.ndarray
            修正された点
        """
        h, w = image.shape
        modified_points = points.copy()

        for iteration in range(self.iterations):
            for i in range(len(modified_points)):
                x, y = modified_points[i]

                # 前の点（角度制約用）
                if i > 0:
                    prev_x, prev_y = modified_points[i - 1]
                else:
                    prev_x, prev_y = x, y

                # 最小輝度を探索
                min_intensity = (
                    image[int(y), int(x)] if 0 <= y < h and 0 <= x < w else 255
                )
                new_x, new_y = x, y
                min_distance = float("inf")
                min_centroid_distance = float("inf")
                min_prev_distance = float("inf")

                # 方向ベクトル（重心から現在の点へ）
                dir_x = x - centroid_x
                dir_y = y - centroid_y
                norm = np.sqrt(dir_x**2 + dir_y**2)
                if norm > 0:
                    dir_x /= norm
                    dir_y /= norm

                # 探索範囲
                for dx in range(-self.search_radius, self.search_radius + 1):
                    for dy in range(-self.search_radius, self.search_radius + 1):
                        nx = int(x + dx)
                        ny = int(y + dy)

                        # 範囲チェック
                        if not (0 <= nx < w and 0 <= ny < h):
                            continue

                        # 探索点へのベクトル
                        vec_x = nx - centroid_x
                        vec_y = ny - centroid_y
                        vec_norm = np.sqrt(vec_x**2 + vec_y**2)

                        if vec_norm > 0:
                            vec_x /= vec_norm
                            vec_y /= vec_norm

                        # 角度チェック
                        dot_product = dir_x * vec_x + dir_y * vec_y
                        angle = np.arccos(np.clip(dot_product, -1, 1))

                        if abs(angle) > self.angle_threshold:
                            continue

                        # 輝度と距離を評価
                        intensity = image[ny, nx]
                        distance = np.sqrt(dx**2 + dy**2)
                        centroid_distance = np.sqrt(
                            (nx - centroid_x) ** 2 + (ny - centroid_y) ** 2
                        )
                        prev_distance = np.sqrt((nx - prev_x) ** 2 + (ny - prev_y) ** 2)

                        # 条件判定（優先順位付き）
                        if (
                            intensity < min_intensity
                            or (intensity == min_intensity and distance < min_distance)
                            or (
                                intensity == min_intensity
                                and distance == min_distance
                                and centroid_distance < min_centroid_distance
                            )
                            or (
                                intensity == min_intensity
                                and distance == min_distance
                                and centroid_distance == min_centroid_distance
                                and prev_distance < min_prev_distance
                            )
                        ):

                            min_intensity = intensity
                            new_x, new_y = nx, ny
                            min_distance = distance
                            min_centroid_distance = centroid_distance
                            min_prev_distance = prev_distance

                # 点を更新
                modified_points[i] = [new_x, new_y]

        return modified_points

    def _fast_modification(
        self,
        image: np.ndarray,
        points: np.ndarray,
        centroid_x: float,
        centroid_y: float,
    ) -> np.ndarray:
        """
        高速な点の修正（簡易版）

        Parameters:
        -----------
        image : np.ndarray
            入力画像
        points : np.ndarray
            点の配列 (N, 2)
        centroid_x, centroid_y : float
            重心座標

        Returns:
        --------
        modified_points : np.ndarray
            修正された点
        """
        h, w = image.shape
        modified_points = points.copy()

        # 1回の反復のみで高速化
        for i in range(0, len(modified_points), 5):  # 5点ごとにサンプリング
            x, y = modified_points[i]

            # 方向ベクトル（重心から現在の点へ）
            dir_x = x - centroid_x
            dir_y = y - centroid_y
            norm = np.sqrt(dir_x**2 + dir_y**2)
            if norm == 0:
                continue

            dir_x /= norm
            dir_y /= norm

            # 半径方向に簡易探索
            min_intensity = 255
            new_x, new_y = x, y

            for r in range(-self.search_radius, self.search_radius + 1):
                nx = int(x + dir_x * r)
                ny = int(y + dir_y * r)

                if 0 <= nx < w and 0 <= ny < h:
                    intensity = image[ny, nx]
                    if intensity < min_intensity:
                        min_intensity = intensity
                        new_x, new_y = nx, ny

            modified_points[i] = [new_x, new_y]

        return modified_points

    def _smooth_points(self, points: np.ndarray) -> np.ndarray:
        """
        3点移動平均で点を平滑化

        Parameters:
        -----------
        points : np.ndarray
            点の配列 (N, 2)

        Returns:
        --------
        smoothed : np.ndarray
            平滑化された点
        """
        n = len(points)
        smoothed = np.zeros_like(points, dtype=float)

        for i in range(n):
            prev_i = (i - 1) % n
            next_i = (i + 1) % n

            smoothed[i, 0] = (points[prev_i, 0] + points[i, 0] + points[next_i, 0]) / 3
            smoothed[i, 1] = (points[prev_i, 1] + points[i, 1] + points[next_i, 1]) / 3

        # 最初と最後を同じにする（閉じた輪郭）
        smoothed[-1] = smoothed[0]

        return smoothed

    def _remove_duplicate_points(self, points: np.ndarray) -> np.ndarray:
        """
        重複点を除去

        Parameters:
        -----------
        points : np.ndarray
            点の配列 (N, 2)

        Returns:
        --------
        unique_points : np.ndarray
            重複のない点
        """
        unique_list = []
        prev_point = None

        for point in points:
            current = tuple(point.astype(int))
            if prev_point is None or current != prev_point:
                unique_list.append(point)
                prev_point = current

        # 最初と最後が同じ場合は最後を削除
        if len(unique_list) > 1:
            if np.array_equal(unique_list[0], unique_list[-1]):
                unique_list = unique_list[:-1]

        return np.array(unique_list)

    def get_roi_coordinates(
        self, roi_mask: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        ROIマスクから座標を取得

        Parameters:
        -----------
        roi_mask : np.ndarray
            ROIマスク

        Returns:
        --------
        x_coords : np.ndarray
            X座標配列
        y_coords : np.ndarray
            Y座標配列
        """
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )

        if len(contours) == 0:
            return np.array([]), np.array([])

        contour = max(contours, key=cv2.contourArea)
        points = contour.squeeze()

        if len(points.shape) == 1:
            points = points.reshape(-1, 2)

        x_coords = points[:, 0]
        y_coords = points[:, 1]

        return x_coords, y_coords


class FAZDetector:
    """
    FAZ（Foveal Avascular Zone）検出クラス
    VD解析のFAZ検出に対応
    """

    @staticmethod
    def detect_faz(
        skeleton: np.ndarray,
        search_center: bool = True,
        remove_small_particles: bool = True,
        max_particle_size: int = 1000,
    ) -> np.ndarray:
        """
        FAZを検出

        Parameters:
        -----------
        skeleton : np.ndarray
            スケルトン画像
        search_center : bool
            中心から検索するか
        remove_small_particles : bool
            小粒子を除去するか（ImageJ互換）
        max_particle_size : int
            除去する粒子の最大サイズ（ピクセル）

        Returns:
        --------
        faz_mask : np.ndarray
            FAZマスク（255=FAZ領域）
        """
        h, w = skeleton.shape
        center_x = w // 2
        center_y = h // 2

        # 中心ピクセルをチェック
        center_value = skeleton[center_y, center_x]

        if center_value == 0:
            # 中心が黒（FAZ）の場合
            seed_x, seed_y = center_x, center_y
        else:
            # 中心が白の場合、周囲を探索
            found = False
            for dx in range(-15, 16):
                for dy in range(-15, 16):
                    check_x = center_x + dx
                    check_y = center_y + dy

                    if 0 <= check_x < w and 0 <= check_y < h:
                        if skeleton[check_y, check_x] == 0:
                            seed_x, seed_y = check_x, check_y
                            found = True
                            break
                if found:
                    break

            if not found:
                # 見つからない場合は小さい円形FAZを作成
                faz_mask = np.zeros((h, w), dtype=np.uint8)
                cv2.circle(faz_mask, (center_x, center_y), 20, 255, -1)
                return faz_mask

        # Flood fillでFAZ領域を取得
        faz_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        flood_mask = skeleton.copy()

        cv2.floodFill(flood_mask, faz_mask, (seed_x, seed_y), 255)

        # マスクを元のサイズに戻す
        faz_mask = faz_mask[1:-1, 1:-1]
        faz_mask = (flood_mask == 255).astype(np.uint8) * 255

        # ImageJ互換: FAZ領域内の小粒子を除去
        # ImageJ: "Analyze Particles...", "size=0-1000 circularity=0.0-1.0 show=[Nothing] exclude clear add"
        if remove_small_particles:
            faz_mask = FAZDetector._remove_small_particles(faz_mask, max_particle_size)

        return faz_mask

    @staticmethod
    def _remove_small_particles(
        faz_mask: np.ndarray, max_particle_size: int = 1000
    ) -> np.ndarray:
        """
        FAZ領域内の小粒子を除去（ImageJ互換）

        Parameters:
        -----------
        faz_mask : np.ndarray
            FAZマスク（255=FAZ領域）
        max_particle_size : int
            除去する粒子の最大サイズ（ピクセル）

        Returns:
        --------
        cleaned_mask : np.ndarray
            小粒子除去後のFAZマスク
        """
        from skimage import measure

        # FAZ領域（255）をTrueに変換
        faz_bool = faz_mask == 255

        # FAZ領域の反転：FAZ内部の穴（白い部分 = 血管断片）を検出
        inverted_inside = ~faz_bool

        # Connected components解析でFAZ内部の穴を検出
        labeled_holes = measure.label(inverted_inside, connectivity=2, background=False)
        regions = measure.regionprops(labeled_holes)

        # 小さい穴（0-max_particle_sizeピクセル）を塗りつぶす（FAZに統合）
        cleaned_bool = faz_bool.copy()
        for region in regions:
            if 0 < region.area <= max_particle_size:
                # この領域をFAZに含める（Trueにする）
                coords = region.coords
                for coord in coords:
                    cleaned_bool[coord[0], coord[1]] = True

        # uint8 255形式に戻す
        cleaned_mask = (cleaned_bool.astype(np.uint8)) * 255
        return cleaned_mask

    @staticmethod
    def expand_roi(roi_mask: np.ndarray, iterations: int = 1) -> np.ndarray:
        """
        ROIを拡張
        expandROI に対応

        Parameters:
        -----------
        roi_mask : np.ndarray
            ROIマスク
        iterations : int
            拡張回数

        Returns:
        --------
        expanded : np.ndarray
            拡張されたROI
        """
        # 輪郭を取得
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if len(contours) == 0:
            return roi_mask

        contour = max(contours, key=cv2.contourArea)
        points = contour.squeeze()

        if len(points.shape) == 1:
            points = points.reshape(-1, 2)

        # 3点移動平均で平滑化と拡張
        n = len(points)
        expanded_points = np.zeros_like(points, dtype=float)

        for i in range(n):
            prev_i = (i - 1) % n
            next_i = (i + 1) % n

            # 平均
            avg_x = (points[prev_i, 0] + points[i, 0] + points[next_i, 0]) / 3
            avg_y = (points[prev_i, 1] + points[i, 1] + points[next_i, 1]) / 3

            # ランダムな微小変動を追加
            noise_x = np.random.random() - 0.5
            noise_y = np.random.random() - 0.5

            expanded_points[i, 0] = avg_x + noise_x
            expanded_points[i, 1] = avg_y + noise_y

        # 新しいマスクを作成
        expanded_mask = np.zeros_like(roi_mask)
        cv2.fillPoly(expanded_mask, [expanded_points.astype(np.int32)], 255)

        return expanded_mask

    @staticmethod
    def create_concentric_rois(
        faz_mask: np.ndarray, image_width: int, image_height: int
    ) -> Dict[str, np.ndarray]:
        """
        同心円ROIを作成（全体、上、下、左、右）

        Parameters:
        -----------
        faz_mask : np.ndarray
            FAZマスク
        image_width : int
            画像幅
        image_height : int
            画像高さ

        Returns:
        --------
        rois : dict
            各領域のROIマスク
        """
        # FAZの中心を取得
        contours, _ = cv2.findContours(
            faz_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if len(contours) > 0:
            M = cv2.moments(contours[0])
            if M["m00"] != 0:
                center_x = int(M["m10"] / M["m00"])
                center_y = int(M["m01"] / M["m00"])
            else:
                center_x = image_width // 2
                center_y = image_height // 2
        else:
            center_x = image_width // 2
            center_y = image_height // 2

        # 半径
        radius = image_width // 2
        inner_radius = radius // 2

        # 全体のリング
        outer_circle = np.zeros((image_height, image_width), dtype=np.uint8)
        cv2.circle(outer_circle, (center_x, center_y), radius, 255, -1)

        inner_circle = np.zeros((image_height, image_width), dtype=np.uint8)
        cv2.circle(inner_circle, (center_x, center_y), inner_radius, 255, -1)

        ring = cv2.subtract(outer_circle, inner_circle)

        # 4象限を作成（45度回転した矩形 - ImageJと同じ方法）
        # ImageJのmakeRotatedRectangle(x1, y1, x2, y2, width)は
        # (x1,y1)から(x2,y2)への直線を中心線とし、幅widthの回転矩形を作成
        diag = int(image_width / 2 * np.sqrt(2))

        # bearing（中心からの偏移）
        xbearing = center_x - image_width // 2
        ybearing = center_y - image_height // 2

        # 上（Superior）- 左上から右上への45度矩形
        # makeRotatedRectangle(imageWidth/4+xbearing, -imageWidth/4+ybearing,
        #                      imageWidth*3/4+xbearing, imageWidth/4+ybearing, diag)
        superior = FAZDetector._create_rotated_rectangle_45deg(
            image_width,
            image_height,
            image_width // 4 + xbearing,
            -image_width // 4 + ybearing,
            image_width * 3 // 4 + xbearing,
            image_width // 4 + ybearing,
            diag,
        )
        superior = cv2.bitwise_and(ring, superior)

        # 下（Inferior）- 左下から右下への45度矩形
        # makeRotatedRectangle(imageWidth/4+xbearing, imageWidth*3/4+ybearing,
        #                      imageWidth*3/4+xbearing, imageWidth*5/4+ybearing, diag)
        inferior = FAZDetector._create_rotated_rectangle_45deg(
            image_width,
            image_height,
            image_width // 4 + xbearing,
            image_width * 3 // 4 + ybearing,
            image_width * 3 // 4 + xbearing,
            image_width * 5 // 4 + ybearing,
            diag,
        )
        inferior = cv2.bitwise_and(ring, inferior)

        # 左（Temporal）- 左上から左下への45度矩形
        # makeRotatedRectangle(-imageWidth/4+xbearing, imageWidth/4+ybearing,
        #                      imageWidth/4+xbearing, imageWidth*3/4+ybearing, diag)
        temporal = FAZDetector._create_rotated_rectangle_45deg(
            image_width,
            image_height,
            -image_width // 4 + xbearing,
            image_width // 4 + ybearing,
            image_width // 4 + xbearing,
            image_width * 3 // 4 + ybearing,
            diag,
        )
        temporal = cv2.bitwise_and(ring, temporal)

        # 右（Nasal）- 右上から右下への45度矩形
        # makeRotatedRectangle(imageWidth*3/4+xbearing, imageWidth/4+ybearing,
        #                      imageWidth*5/4+xbearing, imageWidth*3/4+ybearing, diag)
        nasal = FAZDetector._create_rotated_rectangle_45deg(
            image_width,
            image_height,
            image_width * 3 // 4 + xbearing,
            image_width // 4 + ybearing,
            image_width * 5 // 4 + xbearing,
            image_width * 3 // 4 + ybearing,
            diag,
        )
        nasal = cv2.bitwise_and(ring, nasal)

        return {
            "whole": outer_circle,
            "ring": ring,
            "superior": superior,
            "inferior": inferior,
            "temporal": temporal,
            "nasal": nasal,
        }

    @staticmethod
    def _create_rotated_rectangle_45deg(
        width: int,
        height: int,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        rect_width: int,
    ) -> np.ndarray:
        """
        ImageJのmakeRotatedRectangleに相当する45度回転矩形を作成

        Parameters:
        -----------
        width, height : int
            画像サイズ
        x1, y1 : int
            矩形の中心線の始点
        x2, y2 : int
            矩形の中心線の終点
        rect_width : int
            矩形の幅

        Returns:
        --------
        mask : np.ndarray
            回転矩形マスク
        """
        mask = np.zeros((height, width), dtype=np.uint8)

        # 中心線のベクトル
        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx**2 + dy**2)

        if length == 0:
            return mask

        # 正規化された方向ベクトル
        ux = dx / length
        uy = dy / length

        # 垂直ベクトル（90度回転）
        vx = -uy
        vy = ux

        # 矩形の4つの頂点
        half_width = rect_width / 2

        pts = np.array(
            [
                [x1 + vx * half_width, y1 + vy * half_width],
                [x2 + vx * half_width, y2 + vy * half_width],
                [x2 - vx * half_width, y2 - vy * half_width],
                [x1 - vx * half_width, y1 - vy * half_width],
            ],
            np.int32,
        )

        cv2.fillPoly(mask, [pts], 255)

        return mask


class ROIEnclosure:
    """
    ROIの包絡領域（Enclosure）を生成するクラス。
    疎な血管網（枯れ枝型）でも病変全体の広がりを定義するため、凸包とスプライン平滑化を用いる。
    """
    
    @staticmethod
    def generate_enclosed_mask(roi_mask: np.ndarray, smoothing_factor: float = 1.0) -> np.ndarray:
        """
        ROIマスクから滑らかな包絡領域マスクを生成する。
        
        Parameters:
        -----------
        roi_mask : np.ndarray
            元のROIマスク（0/255 または bool）
        smoothing_factor : float
            スプライン平滑化の強さ (0.0=平滑化なし)
            
        Returns:
        --------
        enclosed_mask : np.ndarray
            生成された包絡領域マスク (0/255)
        """
        import cv2
        import numpy as np
        from scipy.interpolate import splprep, splev

        if roi_mask is None or not np.any(roi_mask):
            return np.zeros_like(roi_mask, dtype=np.uint8) if roi_mask is not None else None

        binary = (roi_mask > 0).astype(np.uint8) * 255
        
        # 1. 輪郭抽出
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return binary
            
        # 全ての輪郭の点を集める（分散した血管網をひとまとめにするため）
        all_points = np.vstack(contours)
        
        if len(all_points) < 3:
            return binary
            
        # 2. 全体に対する凸包（Convex Hull）の計算
        hull = cv2.convexHull(all_points)
        
        # 3. スプライン曲線による平滑化 (点が十分ある場合)
        if len(hull) >= 4 and smoothing_factor > 0:
            x = hull[:, 0, 0]
            y = hull[:, 0, 1]
            
            try:
                # 距離が近い点（重複点や密接点）を間引く
                unique_pts = []
                for i in range(len(x)):
                    if i == 0 or (x[i]-unique_pts[-1][0])**2 + (y[i]-unique_pts[-1][1])**2 > 4.0:
                        unique_pts.append((x[i], y[i]))
                if unique_pts[0] != unique_pts[-1]:
                    unique_pts.append(unique_pts[0])
                    
                pts_arr = np.array(unique_pts)
                x_u = pts_arr[:, 0]
                y_u = pts_arr[:, 1]

                if len(x_u) >= 4:
                    # sパラメータは平滑化の度合い
                    tck, u = splprep([x_u, y_u], s=smoothing_factor * len(x_u), per=True)
                    unew = np.linspace(0, 1, len(x_u) * 5)
                    out = splev(unew, tck)
                    smooth_hull = np.stack(out, axis=1).astype(np.int32).reshape((-1, 1, 2))
                else:
                    smooth_hull = hull
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Spline smoothing failed: {e}")
                smooth_hull = hull
        else:
            smooth_hull = hull
            
        # 4. マスクの生成
        enclosed_mask = np.zeros_like(binary)
        cv2.fillPoly(enclosed_mask, [smooth_hull], 255)
        
        # 元のROI領域を確実に含める（スプラインが内側に入り込むのを防ぐ）
        enclosed_mask = cv2.bitwise_or(enclosed_mask, binary)
        
        return enclosed_mask
