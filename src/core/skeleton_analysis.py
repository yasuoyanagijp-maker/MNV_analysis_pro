"""
スケルトン解析モジュール
ImageJのAnalyze Skeletonプラグインの実装を統合
血管のスケルトン化、径測定、分岐点解析、トルトゥオシティ計算
"""

import warnings
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from skimage import morphology

warnings.filterwarnings("ignore")


@dataclass
class Point:
    """スケルトン上の点を表現"""

    x: int
    y: int
    z: int = 0

    def __hash__(self):
        return hash((self.x, self.y, self.z))

    def __eq__(self, other):
        return (self.x, self.y, self.z) == (other.x, other.y, other.z)


@dataclass
class Branch:
    """ブランチ（エッジ）を表現"""

    points: List[Point]
    v1: Optional["Vertex"] = None  # 始点
    v2: Optional["Vertex"] = None  # 終点
    length: float = 0.0
    euclidean_distance: float = 0.0

    def calculate_length(self, pixel_size=(1.0, 1.0, 1.0)):
        """ブランチの長さを計算"""
        if len(self.points) < 2:
            self.length = 0.0
            return

        total_length = 0.0
        for i in range(len(self.points) - 1):
            p1, p2 = self.points[i], self.points[i + 1]
            dx = (p2.x - p1.x) * pixel_size[0]
            dy = (p2.y - p1.y) * pixel_size[1]
            dz = (p2.z - p1.z) * pixel_size[2]
            total_length += np.sqrt(dx**2 + dy**2 + dz**2)

        self.length = total_length

        # ユークリッド距離を計算
        if len(self.points) >= 2:
            p1, p2 = self.points[0], self.points[-1]
            dx = (p2.x - p1.x) * pixel_size[0]
            dy = (p2.y - p1.y) * pixel_size[1]
            dz = (p2.z - p1.z) * pixel_size[2]
            self.euclidean_distance = np.sqrt(dx**2 + dy**2 + dz**2)


@dataclass
class Vertex:
    """頂点（分岐点または端点）を表現"""

    points: List[Point]
    branches: List[Branch]
    vertex_type: str  # 'endpoint', 'junction'


class SkeletonAnalyzer:
    """
    ImageJのAnalyze Skeletonプラグインを模倣したスケルトン解析
    performSkeletonAnalysisImproved に対応
    """

    # ボクセルタイプの定数
    ENDPOINT = 30
    JUNCTION = 70
    SLAB = 127

    def __init__(self, mm_per_pixel: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            ピクセルあたりのmm
        """
        self.mm_per_pixel = mm_per_pixel
        self.pixel_size_um = mm_per_pixel * 1000

        # ImageJ Analyze Skeleton用
        self.input_image = None
        self.tagged_image = None
        self.width = 0
        self.height = 0
        self.depth = 0

    def skeletonize(self, binary: np.ndarray) -> np.ndarray:
        """
        スケルトン化

        Parameters:
        -----------
        binary : np.ndarray
            二値画像

        Returns:
        --------
        skeleton : np.ndarray
            スケルトン画像
        """
        skeleton_bool = morphology.skeletonize(binary > 0)
        skeleton = (skeleton_bool * 255).astype(np.uint8)
        return skeleton

    def setup_imagej_analyzer(self, skeleton: np.ndarray):
        """ImageJ Analyze Skeletonの初期化"""
        self.input_image = skeleton.astype(np.uint8)

        if skeleton.ndim == 2:
            self.height, self.width = skeleton.shape
            self.depth = 1
            self.input_image = skeleton[np.newaxis, :, :]
        elif skeleton.ndim == 3:
            self.depth, self.height, self.width = skeleton.shape
        else:
            raise ValueError("Input image must be 2D or 3D")

        self.tagged_image = np.zeros_like(self.input_image, dtype=np.uint8)

    def get_neighbors_26(self, x: int, y: int, z: int) -> List[Point]:
        """26連結近傍を取得（2Dの場合は8連結）"""
        neighbors = []
        for dz in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0 and dz == 0:
                        continue
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if (
                        0 <= nx < self.width
                        and 0 <= ny < self.height
                        and 0 <= nz < self.depth
                    ):
                        if self.input_image[nz, ny, nx] > 0:
                            neighbors.append(Point(nx, ny, nz))
        return neighbors

    def classify_voxel(self, x: int, y: int, z: int) -> int:
        """
        ボクセルを端点・分岐点・通常点に分類

        Returns:
            ENDPOINT (<2 neighbors), JUNCTION (>2 neighbors), SLAB (2 neighbors)
        """
        neighbors = self.get_neighbors_26(x, y, z)
        n_neighbors = len(neighbors)

        if n_neighbors < 2:
            return self.ENDPOINT
        elif n_neighbors > 2:
            return self.JUNCTION
        else:
            return self.SLAB

    def tag_skeleton(self):
        """スケルトン内の全ピクセルをタグ付け（2Dはベクトル化）"""
        if self.depth == 1:
            self._tag_skeleton_2d_vectorized()
        else:
            for z in range(self.depth):
                for y in range(self.height):
                    for x in range(self.width):
                        if self.input_image[z, y, x] > 0:
                            voxel_type = self.classify_voxel(x, y, z)
                            self.tagged_image[z, y, x] = voxel_type

    def _tag_skeleton_2d_vectorized(self):
        """2Dスケルトンのタグ付けをベクトル化（3x3カーネル）"""
        img = (self.input_image[0] > 0).astype(np.uint8)
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)
        filtered = cv2.filter2D(img, -1, kernel)
        # 1 neighbor -> endpoint; 3+ -> junction; 2 -> slab
        endpoint = (filtered == 11) & (img > 0)
        junction = (filtered >= 13) & (img > 0)
        slab = (img > 0) & ~endpoint & ~junction
        self.tagged_image[0] = np.where(
            endpoint, self.ENDPOINT, np.where(junction, self.JUNCTION, slab * self.SLAB)
        ).astype(np.uint8)

    def find_vertices(self) -> List[Vertex]:
        """全ての端点と分岐点を検出（2Dはnp.whereで高速化）"""
        if self.depth == 1:
            return self._find_vertices_2d()
        return self._find_vertices_3d()

    def _find_vertices_2d(self) -> List[Vertex]:
        """2D: np.whereで端点・分岐点座標を取得してから処理"""
        img = self.tagged_image[0]
        vertices = []

        y_ep, x_ep = np.where(img == self.ENDPOINT)
        for i in range(len(x_ep)):
            p = Point(int(x_ep[i]), int(y_ep[i]), 0)
            vertices.append(Vertex([p], [], "endpoint"))

        y_j, x_j = np.where(img == self.JUNCTION)
        junction_set = set(zip(x_j.tolist(), y_j.tolist()))
        visited_j = set()

        for i in range(len(x_j)):
            xy = (int(x_j[i]), int(y_j[i]))
            if xy in visited_j:
                continue
            vertex_points = []
            queue = deque([xy])
            visited_j.add(xy)
            while queue:
                x, y = queue.popleft()
                vertex_points.append(Point(x, y, 0))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            nxy = (nx, ny)
                            if nxy in junction_set and nxy not in visited_j:
                                visited_j.add(nxy)
                                queue.append(nxy)
            if vertex_points:
                vertices.append(Vertex(vertex_points, [], "junction"))

        return vertices

    def _find_vertices_3d(self) -> List[Vertex]:
        """3D: 従来の全画素スキャン"""
        vertices = []
        visited = set()
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    voxel_type = self.tagged_image[z, y, x]
                    if voxel_type in (self.ENDPOINT, self.JUNCTION):
                        point = Point(x, y, z)
                        if point not in visited:
                            vertex_points = [point]
                            visited.add(point)
                            if voxel_type == self.JUNCTION:
                                queue = deque([point])
                                while queue:
                                    p = queue.popleft()
                                    for n in self.get_neighbors_26(p.x, p.y, p.z):
                                        if (
                                            self.tagged_image[n.z, n.y, n.x]
                                            == self.JUNCTION
                                            and n not in visited
                                        ):
                                            vertex_points.append(n)
                                            visited.add(n)
                                            queue.append(n)
                            vertices.append(
                                Vertex(
                                    vertex_points, [],
                                    "junction" if voxel_type == self.JUNCTION else "endpoint"
                                )
                            )
        return vertices

    def trace_branch(self, start: Point, prev: Point, vertices_dict: Dict) -> Branch:
        """
        ブランチをトレース

        Parameters:
            start: 開始点
            prev: 前の点（逆方向を防ぐ）
            vertices_dict: 点から頂点へのマッピング
        """
        branch_points = [start]
        current = start
        previous = prev

        while True:
            neighbors = self.get_neighbors_26(current.x, current.y, current.z)
            next_points = [n for n in neighbors if n != previous]

            if not next_points:
                break

            # 頂点に到達したら停止
            if len(next_points) > 1 or next_points[0] in vertices_dict:
                if next_points[0] not in branch_points:
                    branch_points.append(next_points[0])
                break

            # ブランチに沿って続ける
            previous = current
            current = next_points[0]
            branch_points.append(current)

            # ループ検出
            if len(branch_points) > self.width * self.height * self.depth:
                break

        branch = Branch(branch_points)
        pixel_size = (self.mm_per_pixel, self.mm_per_pixel, self.mm_per_pixel)
        branch.calculate_length(pixel_size)
        return branch

    def find_branches(self, vertices: List[Vertex]) -> List[Branch]:
        """頂点を接続する全てのブランチを検出"""
        branches = []

        vertices_dict = {}
        for vertex in vertices:
            for point in vertex.points:
                vertices_dict[point] = vertex

        visited_pairs = set()

        for vertex in vertices:
            for start_point in vertex.points:
                neighbors = self.get_neighbors_26(
                    start_point.x, start_point.y, start_point.z
                )

                for neighbor in neighbors:
                    if neighbor in vertex.points:
                        continue

                    pair_id = (id(vertex), neighbor.x, neighbor.y, neighbor.z)
                    if pair_id in visited_pairs:
                        continue
                    visited_pairs.add(pair_id)

                    branch = self.trace_branch(neighbor, start_point, vertices_dict)

                    if len(branch.points) > 0:
                        branch.v1 = vertex

                        end_point = branch.points[-1]
                        if end_point in vertices_dict:
                            branch.v2 = vertices_dict[end_point]

                        branches.append(branch)
                        vertex.branches.append(branch)

        return branches

    def analyze_skeleton_structure(self, skeleton: np.ndarray) -> Dict[str, any]:
        """
        スケルトンの構造解析（ImageJ Analyze Skeleton互換）
        2D時はbboxでクロップして高速化し、座標は元画像系に変換して返す。
        """
        skel = skeleton if skeleton.ndim == 2 else skeleton[0]
        y_pts, x_pts = np.where(skel > 0)
        if len(x_pts) == 0:
            self.setup_imagej_analyzer(skeleton)
            return self._empty_skeleton_results()

        # Crop to bbox for faster iteration (skeleton is sparse)
        y_lo, y_hi = int(y_pts.min()), int(y_pts.max()) + 1
        x_lo, x_hi = int(x_pts.min()), int(x_pts.max()) + 1
        crop = skel[y_lo:y_hi, x_lo:x_hi]
        if skeleton.ndim == 3:
            crop = crop[np.newaxis, :, :]
        offset_x, offset_y = x_lo, y_lo

        self.setup_imagej_analyzer(crop)
        self.tag_skeleton()

        vertices = self.find_vertices()
        branches = self.find_branches(vertices)

        # Restore coordinates to original image space
        self._add_offset_to_points(vertices, branches, offset_x, offset_y)

        return self._build_skeleton_results(vertices, branches, skeleton)

    def _add_offset_to_points(
        self,
        vertices: List["Vertex"],
        branches: List["Branch"],
        offset_x: int,
        offset_y: int,
    ) -> None:
        """Add offset to all Point coordinates (for crop->original space)."""
        for v in vertices:
            v.points = [
                Point(p.x + offset_x, p.y + offset_y, p.z) for p in v.points
            ]
        for b in branches:
            b.points = [
                Point(p.x + offset_x, p.y + offset_y, p.z) for p in b.points
            ]

    def _empty_skeleton_results(self) -> Dict[str, any]:
        """Return empty results when skeleton has no pixels."""
        return {
            "num_branches": 0,
            "num_junctions": 0,
            "num_endpoints": 0,
            "num_triple_points": 0,
            "num_quadruple_points": 0,
            "num_skeletons": 0,
            "branch_lengths": [],
            "branch_euclidean_distances": [],
            "junction_positions": [],
            "endpoint_positions": [],
            "branches": [],
            "vertices": [],
        }

    def _build_skeleton_results(
        self,
        vertices: List["Vertex"],
        branches: List["Branch"],
        skeleton: np.ndarray,
    ) -> Dict[str, any]:
        """Build results dict from vertices and branches."""
        # 端点と分岐点のカウント
        num_endpoints = sum(1 for v in vertices if v.vertex_type == "endpoint")
        num_junctions = sum(1 for v in vertices if v.vertex_type == "junction")

        # トリプル・クアドラプルポイント
        num_triple = 0
        num_quadruple = 0
        for vertex in vertices:
            if vertex.vertex_type == "junction":
                n_branches = len(vertex.branches)
                if n_branches == 3:
                    num_triple += 1
                elif n_branches == 4:
                    num_quadruple += 1

        # ブランチ長の情報
        branch_lengths = [b.length for b in branches]
        branch_euclidean_distances = [b.euclidean_distance for b in branches]

        # 端点・分岐点の座標
        endpoint_positions = []
        junction_positions = []
        for vertex in vertices:
            if vertex.points:
                p = vertex.points[0]
                if vertex.vertex_type == "endpoint":
                    endpoint_positions.append((p.x, p.y))
                else:
                    junction_positions.append((p.x, p.y))

        # 連結成分数
        if skeleton.ndim == 2:
            num_labels = cv2.connectedComponents(skeleton, connectivity=8)[0]
        else:
            num_labels = cv2.connectedComponents(skeleton[0], connectivity=8)[0]

        results = {
            "num_branches": len(branches),
            "num_junctions": num_junctions,
            "num_endpoints": num_endpoints,
            "num_triple_points": num_triple,
            "num_quadruple_points": num_quadruple,
            "num_skeletons": num_labels - 1,
            "branch_lengths": branch_lengths,
            "branch_euclidean_distances": branch_euclidean_distances,
            "junction_positions": junction_positions,
            "endpoint_positions": endpoint_positions,
            "branches": branches,
            "vertices": vertices,
        }

        return results


class DiameterAnalyzer:
    """
    血管径解析クラス
    performVesselDiameterAnalysis に対応
    """

    def __init__(self, mm_per_pixel: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            ピクセルあたりのmm
        """
        self.mm_per_pixel = mm_per_pixel
        self.pixel_size_um = mm_per_pixel * 1000

    def create_distance_map(self, binary: np.ndarray) -> np.ndarray:
        """
        距離マップを作成

        Parameters:
        -----------
        binary : np.ndarray
            二値画像

        Returns:
        --------
        distance_map : np.ndarray
            距離マップ（各ピクセルから最近傍の背景までの距離）
        """
        distance_map = cv2.distanceTransform(binary, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)

        return distance_map

    def analyze_diameter_statistics(
        self, distance_map: np.ndarray, skeleton: np.ndarray
    ) -> Dict[str, float]:
        """
        径の統計量を計算
        ImageJ の performVesselDiameterAnalysis に対応

        Parameters:
        -----------
        distance_map : np.ndarray
            距離マップ
        skeleton : np.ndarray
            スケルトン画像

        Returns:
        --------
        stats : dict
            統計量（単位: μm）
        """
        # ImageJではdistance map画像全体の統計を取得している
        # changeValues(0, 0, NaN) でゼロをNaNに変換
        distance_map_copy = distance_map.copy()
        distance_map_copy[distance_map_copy == 0] = np.nan

        # NaN以外の値を取得（ImageJのgetStatisticsと同等）
        valid_distances = distance_map_copy[~np.isnan(distance_map_copy)]

        if len(valid_distances) == 0:
            return {
                "mean_diameter_um": 0,
                "std_diameter_um": 0,
                "max_diameter_um": 0,
                "max_mean_ratio": 0,
                "max_mean_sd": 0,
                "cv_diameter": 0,
            }

        # 統計計算（ImageJのgetStatisticsと同等）
        mean_dist = valid_distances.mean()
        std_dist = valid_distances.std()
        max_dist = valid_distances.max()

        # 径に変換（距離×2）
        mean_diameter_um = mean_dist * 2 * self.pixel_size_um
        std_diameter_um = std_dist * 2 * self.pixel_size_um
        max_diameter_um = max_dist * 2 * self.pixel_size_um

        # ImageJと同じ計算
        if std_dist > 0:
            max_mean_ratio = (max_dist - mean_dist) / std_dist
        else:
            max_mean_ratio = 0

        if max_dist > 0:
            max_mean_sd = 100 * std_dist / max_dist
        else:
            max_mean_sd = 0

        if mean_diameter_um > 0:
            cv_diameter = 100 * std_diameter_um / mean_diameter_um
        else:
            cv_diameter = 0

        stats = {
            "mean_diameter_um": mean_diameter_um,
            "std_diameter_um": std_diameter_um,
            "max_diameter_um": max_diameter_um,
            "max_mean_ratio": max_mean_ratio,
            "max_mean_sd": max_mean_sd,
            "cv_diameter": cv_diameter,
        }

        return stats


class BranchAnalyzer:
    """
    ブランチ情報解析クラス
    processBranchInformation に対応
    """

    def __init__(self, mm_per_pixel: float, skeleton_diameter_um: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            ピクセルあたりのmm
        skeleton_diameter_um : float
            平均血管径（μm）
        """
        self.mm_per_pixel = mm_per_pixel
        self.skeleton_diameter_um = skeleton_diameter_um

    def calculate_tortuosity(
        self, branch_lengths: List[float], euclidean_distances: List[float]
    ) -> Tuple[float, float]:
        """
        トルトゥオシティ（屈曲度）を計算

        Parameters:
        -----------
        branch_lengths : list of float
            ブランチ長のリスト（mm単位）
        euclidean_distances : list of float
            ユークリッド距離のリスト（mm単位）

        Returns:
        --------
        mean_tortuosity : float
            平均トルトゥオシティ
        total_length_mm : float
            総血管長（mm）
        """
        threshold_mm = self.skeleton_diameter_um / 1000.0

        sum_weighted_tortuosity = 0.0
        sum_filtered_length = 0.0
        total_length = 0.0

        for length, euc_dist in zip(branch_lengths, euclidean_distances):
            total_length += length

            # 両方ともmm単位で比較
            if euc_dist > threshold_mm and euc_dist > 0:
                tortuosity = length / euc_dist

                if 1.0 <= tortuosity < 10.0:
                    sum_weighted_tortuosity += length * tortuosity
                    sum_filtered_length += length

        if sum_filtered_length > 0:
            mean_tortuosity = sum_weighted_tortuosity / sum_filtered_length
        else:
            mean_tortuosity = 0.0

        if np.isnan(mean_tortuosity) or mean_tortuosity > 1000:
            mean_tortuosity = 0.0

        # total_lengthは既にmm単位（branch.lengthがmm単位で計算されているため）
        total_length_mm = total_length

        return mean_tortuosity, total_length_mm

    def calculate_corrected_values(
        self,
        vessel_length_mm: float,
        vessel_area_mm2: float,
        triple_points: int,
        quadruple_points: int,
    ) -> Tuple[float, float]:
        """
        補正された血管径と血管長を計算
        calculateCorrectedValues に対応

        Parameters:
        -----------
        vessel_length_mm : float
            血管長（mm）
        vessel_area_mm2 : float
            血管面積（mm²）
        triple_points : int
            3分岐点の数
        quadruple_points : int
            4分岐点の数

        Returns:
        --------
        corrected_diameter_um : float
            補正血管径（μm）
        corrected_length_mm : float
            補正血管長（mm）
        """
        if vessel_length_mm > 0 and (triple_points > 0 or quadruple_points > 0):
            discriminant = (
                vessel_length_mm**2
                - 4 * (triple_points / 2 + quadruple_points) * vessel_area_mm2
            )

            if discriminant >= 0:
                corrected_diameter_um = (
                    1000
                    * (vessel_length_mm - np.sqrt(discriminant))
                    / (2 * (triple_points / 2 + quadruple_points))
                )
            else:
                corrected_diameter_um = 1000 * (vessel_area_mm2 / vessel_length_mm)

            corrected_length_mm = (
                vessel_length_mm
                - triple_points * self.skeleton_diameter_um / 2000
                - quadruple_points * self.skeleton_diameter_um / 1000
            )
            corrected_length_mm = max(corrected_length_mm, 0)
        else:
            if vessel_length_mm > 0:
                corrected_diameter_um = 1000 * (vessel_area_mm2 / vessel_length_mm)
            else:
                corrected_diameter_um = 0
            corrected_length_mm = vessel_length_mm

        return corrected_diameter_um, corrected_length_mm

    def calculate_densities(
        self,
        vessel_length_mm: float,
        num_branches: int,
        num_junctions: int,
        num_endpoints: int,
        num_triple: int,
        num_quadruple: int,
    ) -> Dict[str, float]:
        """
        各種密度を計算

        Parameters:
        -----------
        vessel_length_mm : float
            血管長（mm）
        num_branches : int
            ブランチ数
        num_junctions : int
            分岐点数
        num_endpoints : int
            端点数
        num_triple : int
            3分岐点数
        num_quadruple : int
            4分岐点数

        Returns:
        --------
        densities : dict
            各種密度（単位: /mm）
        """
        if vessel_length_mm > 0:
            branch_density = num_branches / vessel_length_mm
            junction_density = num_junctions / vessel_length_mm
            endpoint_density = num_endpoints / vessel_length_mm
            multiple_density = (num_triple + num_quadruple) / vessel_length_mm
        else:
            branch_density = 0
            junction_density = 0
            endpoint_density = 0
            multiple_density = 0

        return {
            "branch_density": branch_density,
            "junction_density": junction_density,
            "endpoint_density": endpoint_density,
            "multiple_density": multiple_density,
        }


class TaggedSkeletonProcessor:
    """
    Tagged Skeletonの処理
    processTaggedSkeleton, createRefinedSkeleton に対応
    """

    @staticmethod
    def create_tagged_skeleton(skeleton: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Tagged Skeletonを作成

        Parameters:
        -----------
        skeleton : np.ndarray
            スケルトン画像

        Returns:
        --------
        tagged : dict
            'red': ブランチ（通常の骨格点）
            'blue': 分岐点
            'green': 端点
        """
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)

        filtered = cv2.filter2D(skeleton // 255, -1, kernel)

        junctions_mask = (filtered >= 13) & (skeleton > 0)
        endpoints_mask = (filtered == 11) & (skeleton > 0)
        branches_mask = (skeleton > 0) & ~junctions_mask & ~endpoints_mask

        tagged = {
            "red": (branches_mask * 255).astype(np.uint8),
            "blue": (junctions_mask * 255).astype(np.uint8),
            "green": (endpoints_mask * 255).astype(np.uint8),
        }

        return tagged

    @staticmethod
    def calculate_max_junction_area(blue_channel: np.ndarray) -> float:
        """
        Blueチャンネル（分岐点）の最大面積を計算

        ImageJマクロの処理:
        1. Blue channelを二値化
        2. Analyze Particles で全パーティクル検出
        3. 最大面積を返す

        Parameters:
        -----------
        blue_channel : np.ndarray
            Blueチャンネル（分岐点）

        Returns:
        --------
        max_area : float
            最大面積
        """
        # 二値化
        binary = (blue_channel > 0).astype(np.uint8) * 255

        # パーティクルが存在しない場合
        if np.sum(binary) == 0:
            return 0

        # Analyze Particles
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )

        # 最大面積を検索
        max_area = 0
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area > max_area:
                max_area = area

        return max_area

    @staticmethod
    def apply_diameter_length_filter(
        red_channel: np.ndarray,
        distance_map: np.ndarray,
        threshold: float = 0.7,
    ) -> np.ndarray:
        """
        径/長さ比によるフィルタリング（ImageJ完全互換、ベクトル化）
        """
        binary = (red_channel > 0).astype(np.uint8) * 255

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )

        if num_labels <= 1:
            return binary

        labels_flat = labels.ravel()
        dist_flat = np.asarray(distance_map, dtype=np.float64).ravel()
        idx = np.flatnonzero(labels_flat > 0)
        lab = labels_flat[idx]
        n_points = np.bincount(lab, minlength=num_labels + 1)[1:]
        sum_dist = np.bincount(lab, weights=dist_flat[idx], minlength=num_labels + 1)[
            1:
        ]
        n_points = np.maximum(n_points, 1)
        mean_diameter = sum_dist / n_points
        ratio = mean_diameter / n_points
        keep = ratio <= threshold
        keep_full = np.concatenate([[True], keep])
        result = np.where(keep_full[labels], binary, 0).astype(np.uint8)
        return result

    @staticmethod
    def remove_isolated_junctions(skeleton: np.ndarray, max_area: float) -> np.ndarray:
        """
        孤立した分岐点を除去（ImageJ完全互換）

        ImageJマクロの処理:
        1. Make Binary
        2. Analyze Particles で全パーティクル検出
        3. 面積 < maxarea のパーティクルを削除

        Parameters:
        -----------
        skeleton : np.ndarray
            スケルトン画像
        max_area : float
            最大面積（これより小さい成分を削除）

        Returns:
        --------
        cleaned : np.ndarray
            クリーニング後の画像
        """
        binary = (skeleton > 0).astype(np.uint8) * 255

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )

        if num_labels <= 1:
            return binary

        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = areas >= max_area
        keep_full = np.concatenate([[True], keep])
        result = np.where(keep_full[labels], binary, 0).astype(np.uint8)
        return result

    @staticmethod
    def create_refined_skeleton(
        tagged: Dict[str, np.ndarray],
        distance_map: np.ndarray,
        max_junction_area: float,
    ) -> np.ndarray:
        """
        Refined Skeletonを作成（ImageJ processTaggedSkeleton完全実装）

        ImageJマクロの処理フロー:
        1. Red - Blue（分岐点を除去）
        2. applyDiameterLengthFilter: 直径/長さ比 > 0.7 のパーティクルを削除
        3. Result + Blue（分岐点を再追加）
        4. removeIsolatedJunctionPoints: 面積 < maxarea の小パーティクルを削除

        Parameters:
        -----------
        tagged : dict
            Tagged skeleton（'red', 'blue'チャンネル）
        distance_map : np.ndarray
            距離マップ
        max_junction_area : float
            分岐点の最大面積

        Returns:
        --------
        refined : np.ndarray
            精製されたスケルトン
        """
        red = tagged["red"]
        blue = tagged["blue"]

        # 1. Red - Blue: 分岐点を除去
        subtracted = cv2.subtract(red, blue)

        # 2. applyDiameterLengthFilter: 短く太い枝を除去
        # 直径/長さ比 > 0.7 のパーティクルを削除
        filtered = TaggedSkeletonProcessor.apply_diameter_length_filter(
            subtracted, distance_map, threshold=0.7
        )

        # 3. Result + Blue: 分岐点を再追加
        combined = cv2.add(filtered, blue)

        # 4. removeIsolatedJunctionPoints: 小さい孤立点を除去
        # 面積 < maxarea のパーティクルを削除
        refined = TaggedSkeletonProcessor.remove_isolated_junctions(
            combined, max_junction_area
        )

        # 最終的な二値化
        refined = (refined > 0).astype(np.uint8) * 255

        return refined


class FractalAnalyzer:
    """
    フラクタル次元解析
    calculateFractalDimensionBoxCounting に対応
    """

    @staticmethod
    def box_counting(
        binary: np.ndarray,
        min_box_size: int = 2,
        max_box_size: Optional[int] = None,
    ) -> Tuple[List[int], List[int]]:
        """
        Box-counting法によるフラクタル次元計算の準備

        Parameters:
        -----------
        binary : np.ndarray
            二値画像
        min_box_size : int
            最小ボックスサイズ
        max_box_size : int, optional
            最大ボックスサイズ

        Returns:
        --------
        box_sizes : list of int
            ボックスサイズのリスト
        box_counts : list of int
            各サイズでのボックス数
        """
        skel = (binary > 0).astype(np.uint8)
        # Crop to non-zero bbox to reduce work on sparse skeletons
        y_pts, x_pts = np.where(skel > 0)
        if len(x_pts) == 0:
            return [], []
        y_lo, y_hi = int(y_pts.min()), int(y_pts.max()) + 1
        x_lo, x_hi = int(x_pts.min()), int(x_pts.max()) + 1
        crop = skel[y_lo:y_hi, x_lo:x_hi]
        h, w = crop.shape
        max_dim = max(h, w)

        if max_box_size is None:
            max_box_size = 2 ** int(np.log2(max_dim / 4))

        box_sizes = []
        box_counts = []

        box_size = min_box_size
        while box_size <= max_box_size:
            count = FractalAnalyzer._count_boxes(crop, box_size)

            if count > 0:
                box_sizes.append(box_size)
                box_counts.append(count)

            box_size *= 2

        # Diagnostic log for debugging FD issues
        try:
            print(
                f"[FractalAnalyzer] box_counting -> box_sizes={box_sizes}, box_counts={box_counts}"
            )
        except Exception:
            pass

        return box_sizes, box_counts

    @staticmethod
    def _count_boxes(binary: np.ndarray, box_size: int) -> int:
        """
        指定サイズのボックスでスケルトンを含むボックスをカウント（ベクトル化）
        block_reduce で各ブロックの max を取り、>0 のブロック数をカウント
        """
        from skimage.measure import block_reduce

        reduced = block_reduce(
            (binary > 0).astype(np.uint8), (box_size, box_size), np.max
        )
        return int(np.sum(reduced > 0))

    @staticmethod
    def calculate_fractal_dimension(
        box_sizes: List[int], box_counts: List[int]
    ) -> Tuple[float, float]:
        """
        フラクタル次元を計算

        Parameters:
        -----------
        box_sizes : list of int
            ボックスサイズ
        box_counts : list of int
            ボックス数

        Returns:
        --------
        fractal_dimension : float
            フラクタル次元
        r_squared : float
            決定係数
        """
        if len(box_sizes) < 3:
            print(
                f"[FractalAnalyzer] Insufficient box sizes for FD calculation: box_sizes={box_sizes}"
            )
            return 0.0, 0.0

        log_sizes = np.log(1.0 / np.array(box_sizes))
        log_counts = np.log(np.array(box_counts))

        # Diagnostic values
        try:
            print(
                f"[FractalAnalyzer] calc -> log_sizes={log_sizes.tolist()}, log_counts={log_counts.tolist()}"
            )
        except Exception:
            pass

        n = len(log_sizes)
        sum_x = np.sum(log_sizes)
        sum_y = np.sum(log_counts)
        sum_xy = np.sum(log_sizes * log_counts)
        sum_x2 = np.sum(log_sizes**2)

        denom = n * sum_x2 - sum_x**2
        if denom == 0:
            print("[FractalAnalyzer] Warning: denominator zero in slope calculation")
            return 0.0, 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom

        mean_y = sum_y / n
        ss_total = np.sum((log_counts - mean_y) ** 2)

        intercept = (sum_y - slope * sum_x) / n
        predicted = slope * log_sizes + intercept
        ss_residual = np.sum((log_counts - predicted) ** 2)

        r_squared = 1 - (ss_residual / ss_total) if ss_total > 0 else 0

        # Diagnostic summary
        print(
            f"[FractalAnalyzer] calc -> n={n}, slope={slope:.6f}, r2={r_squared:.6f}, ss_total={ss_total:.6f}, ss_residual={ss_residual:.6f}"
        )

        if slope < 0.5 or slope > 2.5:
            print(
                f"[FractalAnalyzer] FD out of expected range -> slope={slope:.6f}; returning 0.0"
            )
            return 0.0, r_squared

        return slope, r_squared


# 使用例
if __name__ == "__main__":
    # サンプル画像の作成
    skeleton = np.zeros((100, 100), dtype=np.uint8)

    # Y字型のスケルトンを描画
    skeleton[20:50, 50] = 255  # 垂直線
    skeleton[50, 30:51] = 255  # 左枝
    skeleton[50, 50:71] = 255  # 右枝

    # 解析の実行
    mm_per_pixel = 0.01
    analyzer = SkeletonAnalyzer(mm_per_pixel)

    # ImageJ Analyze Skeleton互換の解析
    result = analyzer.analyze_skeleton_structure(skeleton)

    print("=== スケルトン解析結果 ===")
    print(f"ブランチ数: {result['num_branches']}")
    print(f"端点数: {result['num_endpoints']}")
    print(f"分岐点数: {result['num_junctions']}")
    print(f"トリプルポイント: {result['num_triple_points']}")
    print(f"クアドラプルポイント: {result['num_quadruple_points']}")

    if result["branch_lengths"]:
        print("\nブランチ長:")
        print(f"  平均: {np.mean(result['branch_lengths']):.2f} mm")
        print(f"  最大: {np.max(result['branch_lengths']):.2f} mm")


class EulerAnalyzer:
    """
    Euler number and loop count calculation.
    Corresponds to calculateEulerNumber.
    """

    @staticmethod
    def calculate_euler_number(skeleton: np.ndarray) -> Tuple[int, int]:
        """
        Euler number and loop count calculation.

        Euler = V - E + F = 2 (for planar graphs).
        num_loops = E - V + C

        Parameters:
        -----------
        skeleton : np.ndarray
            Skeleton image.

        Returns:
        --------
        euler_number : int
            Euler number.
        num_loops : int
            Loop count.
        """
        # Number of connected components
        num_components = cv2.connectedComponents(skeleton, connectivity=8)[0] - 1

        if num_components == 0:
            return 0, 0

        # Detect endpoints and junctions
        endpoints = EulerAnalyzer._detect_endpoints(skeleton)
        junctions = EulerAnalyzer._detect_junctions(skeleton)

        # Estimate branch count (simplified version of Analyze Skeleton)
        num_branches = EulerAnalyzer._count_branches(skeleton)

        # Vertex count = endpoint count + junction count
        num_vertices = (
            endpoints if isinstance(endpoints, (int, np.integer)) else len(endpoints)
        ) + (junctions if isinstance(junctions, (int, np.integer)) else len(junctions))

        # Edge count = branch count
        num_edges = num_branches

        # Loop count = E - V + C
        num_loops = num_edges - num_vertices + num_components

        # ループ数は負になることがあり得る（そのまま返す）
        # Euler数 = C - ループ数
        euler_number = num_components - num_loops

        return euler_number, num_loops

    @staticmethod
    def _detect_endpoints(skeleton: np.ndarray) -> int:
        """Count endpoints."""
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)

        filtered = cv2.filter2D(skeleton // 255, -1, kernel)
        endpoints_mask = (filtered == 11) & (skeleton > 0)
        return np.sum(endpoints_mask)

    @staticmethod
    def _detect_junctions(skeleton: np.ndarray) -> int:
        """Count actual junctions (ImageJ style).

        The AnalyzeSkeleton plugin reports the number of junctions as connected
        components of junction voxels (neighboring junction voxels belong to the
        same junction). To match ImageJ behavior we count connected components in
        the junction mask rather than summing voxels.
        """
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)

        filtered = cv2.filter2D(skeleton // 255, -1, kernel)
        junctions_mask = (filtered >= 13) & (skeleton > 0)

        # Convert boolean mask to uint8 and count connected components
        junctions_uint8 = (junctions_mask > 0).astype(np.uint8)
        n_regions = cv2.connectedComponents(junctions_uint8, connectivity=8)[0] - 1
        return int(max(0, n_regions))

    @staticmethod
    def _count_branches(skeleton: np.ndarray) -> int:
        """Count branches (simplified version)."""
        # Approximated by connected component count
        num_components = cv2.connectedComponents(skeleton, connectivity=8)[0] - 1

        # Re-count after removing junctions
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)

        filtered = cv2.filter2D(skeleton // 255, -1, kernel)
        junctions_mask = (filtered >= 13) & (skeleton > 0)

        skeleton_no_junctions = skeleton.copy()
        skeleton_no_junctions[junctions_mask] = 0

        num_branches = (
            cv2.connectedComponents(skeleton_no_junctions, connectivity=8)[0] - 1
        )

        return max(num_branches, num_components)


class HighSkewnessAnalyzer:
    """
    Detect high skewness segments (arteriolarization).
    Corresponds to performHighSkewnessAnalysis, analyzeArteriolarizationSegments.
    """

    def __init__(self, mm_per_pixel: float, pixel_size_um: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            mm per pixel.
        pixel_size_um : float
            Pixel size (um).
        """
        self.mm_per_pixel = mm_per_pixel
        self.pixel_size_um = pixel_size_um

    def detect_high_skewness_segments(
        self, distance_map: np.ndarray, skeleton: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, Dict]:
        """
        Detect high skewness segments.

        Parameters:
        -----------
        distance_map : np.ndarray
            Distance map.
        skeleton : np.ndarray
            Skeleton image.

        Returns:
        --------
        high_skew_skeleton : np.ndarray
            Skeleton of high skewness segments.
        stats : dict
            Statistics.
        """
        # Collect distance values on skeleton
        skeleton_mask = skeleton > 0
        skeleton_distances = distance_map[skeleton_mask]

        # Remove NaN
        skeleton_distances = skeleton_distances[~np.isnan(skeleton_distances)]

        if len(skeleton_distances) < 10:
            zeros = np.zeros_like(skeleton)
            stats = {"threshold": 0, "count": 0}
            dilated_zeros = zeros.astype(np.float32)
            return zeros, dilated_zeros, stats

        # Statistics computation
        mean_dist = skeleton_distances.mean()
        std_dist = skeleton_distances.std()
        max_dist = skeleton_distances.max()
        min_dist = skeleton_distances.min()

        # Threshold determination
        threshold = self._calculate_threshold(
            skeleton_distances, mean_dist, std_dist, max_dist
        )

        # High skew map (ImageJ: distance-threshold, AND skeleton)
        high_skew_map = self._create_high_skew_map(distance_map, skeleton, threshold)

        # ImageJ compatible: Dilated for visualization FIRST (thick bands)
        dilated_for_vis = self._dilate_high_skew_for_visualization(
            high_skew_map, distance_map
        )
        dilated_highSkew_for_visualization = cv2.GaussianBlur(
            dilated_for_vis.astype(np.float32), (0, 0), sigmaX=4
        ).astype(np.float32)

        # Skeleton for segment analysis: AND(dilated, skeleton) per ImageJ
        high_skew_skeleton = self._skeletonize_high_skew(
            high_skew_map, distance_map, skeleton
        )

        stats = {
            "threshold": threshold,
            "mean": mean_dist,
            "std": std_dist,
            "max": max_dist,
            "min": min_dist,
        }

        return high_skew_skeleton, dilated_highSkew_for_visualization, stats

    def _calculate_threshold(
        self, distances: np.ndarray, mean: float, std: float, max_val: float
    ) -> float:
        """
        Calculate threshold.

        Parameters:
        -----------
        distances : np.ndarray
            Array of distance values.
        mean : float
            Mean.
        std : float
            Standard deviation.
        max_val : float
            Maximum value.

        Returns:
        --------
        threshold : float
            Threshold.
        """
        MIN_ABSOLUTE_STD_PIXEL = 0.5
        MIN_RELATIVE_RANGE = 0.50

        range_val = max_val - distances.min()
        relative_range = range_val / mean if mean > 0 else 0

        # When variance is nearly zero
        if std == 0.0:
            return 0

        # When variance is insufficient: mode+1
        elif (std > 0 and std < MIN_ABSOLUTE_STD_PIXEL) or (
            relative_range > 0 and relative_range < MIN_RELATIVE_RANGE
        ):
            # Calculate mode from histogram
            hist, bin_edges = np.histogram(distances, bins=int(max_val) + 1)
            mode_idx = np.argmax(hist)
            mode = bin_edges[mode_idx]
            threshold = mode + 1

        # When variance is sufficient
        else:
            threshold = mean + 2.0 * std

        return threshold

    def _create_high_skew_map(
        self, distance_map: np.ndarray, skeleton: np.ndarray, threshold: float
    ) -> np.ndarray:
        """
        Create high skewness map.

        Parameters:
        -----------
        distance_map : np.ndarray
            Distance map.
        skeleton : np.ndarray
            Skeleton.
        threshold : float
            Threshold.

        Returns:
        --------
        high_skew_map : np.ndarray
            High skewness map.
        """
        # distance - threshold
        high_skew = distance_map - threshold
        high_skew = np.maximum(high_skew, 0)

        # Binarize
        high_skew_binary = (high_skew > 0).astype(np.uint8) * 255

        # AND with skeleton mask
        skeleton_mask = (skeleton > 0).astype(np.uint8) * 255
        high_skew_masked = cv2.bitwise_and(high_skew_binary, skeleton_mask)

        return high_skew_masked

    def _dilate_high_skew_for_visualization(
        self, high_skew_map: np.ndarray, distance_map: np.ndarray
    ) -> np.ndarray:
        """
        ImageJ compatible: Dilate high skew by drawing circles (radius=distance).
        Returns THICK dilated mask for visualization (no skeleton AND).
        """
        h, w = high_skew_map.shape
        dilated = np.zeros_like(high_skew_map)
        y_coords, x_coords = np.where(high_skew_map > 0)
        for x, y in zip(x_coords, y_coords):
            radius = int(distance_map[y, x])
            if radius < 1:
                radius = 1
            cv2.circle(dilated, (x, y), radius, 255, -1)
        return dilated

    def _skeletonize_high_skew(
        self,
        high_skew_map: np.ndarray,
        distance_map: np.ndarray,
        skeleton: np.ndarray,
    ) -> np.ndarray:
        """
        Skeletonize high skewness region.

        Parameters:
        -----------
        high_skew_map : np.ndarray
            High skewness map.
        distance_map : np.ndarray
            Distance map.
        skeleton : np.ndarray
            Original skeleton.

        Returns:
        --------
        skeletonized : np.ndarray
            Skeletonized high skewness segments.
        """
        h, w = high_skew_map.shape

        # Dilation (based on distance map values)
        dilated = np.zeros_like(high_skew_map)

        y_coords, x_coords = np.where(high_skew_map > 0)

        for x, y in zip(x_coords, y_coords):
            radius = int(distance_map[y, x])
            if radius < 1:
                radius = 1

            # Draw circles
            cv2.circle(dilated, (x, y), radius, 255, -1)

        # AND with skeleton mask
        skeleton_mask = (skeleton > 0).astype(np.uint8) * 255
        result = cv2.bitwise_and(dilated, skeleton_mask)

        return result

    def analyze_segments(
        self,
        high_skew_skeleton: np.ndarray,
        mnv_area_mm2: float,
        vessel_length_mm: float = 0,
    ) -> Dict[str, float]:
        """
        ImageJ analyzeArteriolarizationSegments compatible implementation.

        Processing matches ImageJ (imageJ.ijm 3564-3958):
        - Analyze Particles size>=2 on skeletonized high skew
        - Per-particle: branches, avg_branch_length, max_branch_length
        - total_length_mm = sum(particle_pixels) * pixel_size_um / 1000
        - segment_count = total_branches across particles
        - high_skew_percentage = total_length_mm / vessel_length_mm
        - localized_diameter_variation = CV of per-particle avg branch length (um)
        """
        if np.sum(high_skew_skeleton > 0) == 0:
            return {
                "segment_count": 0,
                "total_length_mm": 0,
                "max_segment_length_mm": 0,
                "density": 0,
                "connectivity_index": 0,
                "high_skew_percentage": 0,
                "localized_diameter_variation": 0.0,
            }

        # Analyze Particles (size >= 2)
        num_labels, labels = cv2.connectedComponents(high_skew_skeleton, connectivity=8)
        valid_particles = [i for i in range(1, num_labels) if np.sum(labels == i) >= 2]

        if not valid_particles:
            return {
                "segment_count": 0,
                "total_length_mm": 0,
                "max_segment_length_mm": 0,
                "density": 0,
                "connectivity_index": 0,
                "high_skew_percentage": 0,
                "localized_diameter_variation": 0.0,
            }

        # Analyze Skeleton (ImageJ: 各 particle ごとに Analyze Skeleton)
        total_branches = 0
        total_length_pixels = 0
        max_length_pixels = 0
        avg_branch_lengths_um = []  # Local Diameter Variation 用

        for particle_id in valid_particles:
            particle_mask = (labels == particle_id).astype(np.uint8)
            result = self._analyze_skeleton_particle(particle_mask)

            total_branches += result["branches"]
            total_length_pixels += result["branches"] * result["avg_branch_length"]
            max_length_pixels = max(max_length_pixels, result["max_branch_length"])
            # ImageJ: avgLengths[i] = getResult("Average Branch Length", i) * pixel_size_um
            avg_branch_lengths_um.append(
                float(result["avg_branch_length"]) * self.pixel_size_um
            )

        # Convert to mm
        segment_count = total_branches
        total_length_mm = (total_length_pixels * self.pixel_size_um) / 1000.0
        max_segment_length_mm = (max_length_pixels * self.pixel_size_um) / 1000.0

        density = segment_count / mnv_area_mm2 if mnv_area_mm2 > 0 else 0
        connectivity_index = total_length_mm / segment_count if segment_count > 0 else 0
        high_skew_percentage = (
            total_length_mm / vessel_length_mm if vessel_length_mm > 0 else 0
        )

        # Local Diameter Variation (max CV%): ImageJ 3918-3932 行
        # 各セグメントの平均ブランチ長(μm)の CV = 100 * std / mean
        if len(avg_branch_lengths_um) > 1:
            mean_l = float(np.mean(avg_branch_lengths_um))
            std_l = float(np.std(avg_branch_lengths_um))
            localized_diameter_variation = (
                100 * std_l / mean_l if mean_l > 0 else 0.0
            )
        else:
            localized_diameter_variation = 0.0

        # Python ネイティブ型で返す（CSV 出力時 numpy.int64 が isinstance(int) で False になる問題を回避）
        return {
            "segment_count": int(segment_count),
            "total_length_mm": float(total_length_mm),
            "max_segment_length_mm": float(max_segment_length_mm),
            "density": float(density),
            "connectivity_index": float(connectivity_index),
            "high_skew_percentage": float(high_skew_percentage),
            "localized_diameter_variation": float(localized_diameter_variation),
        }

    def _analyze_skeleton_particle(self, particle_mask: np.ndarray) -> Dict[str, float]:
        """ImageJ Analyze Skeleton implementation"""
        skeleton = (particle_mask > 0).astype(np.uint8)
        kernel = np.ones((3, 3), dtype=np.uint8)
        neighbor_count = (
            cv2.filter2D(skeleton.astype(np.float32), -1, kernel) * skeleton
        )

        junctions = np.sum(neighbor_count >= 3)
        endpoints = np.sum(neighbor_count == 2)
        total_pixels = np.sum(skeleton > 0)

        if total_pixels == 0:
            return {
                "branches": 0,
                "junctions": 0,
                "avg_branch_length": 0,
                "max_branch_length": 0,
            }

        branches = 1 if junctions == 0 else max(1, endpoints + junctions - 1)
        avg_branch_length = total_pixels / max(branches, 1)

        return {
            "branches": branches,
            "junctions": junctions,
            "avg_branch_length": avg_branch_length,
            "max_branch_length": total_pixels,
        }

    def calculate_localized_variation(self, high_skew_skeleton: np.ndarray) -> float:
        """
        Calculate localized diameter variation.

        Parameters:
        -----------
        high_skew_skeleton : np.ndarray
            Skeleton of high skewness segments.

        Returns:
        --------
        cv : float
            Coefficient of variation (%).
        """
        # Get average length of each segment
        num_labels, labels = cv2.connectedComponents(high_skew_skeleton, connectivity=8)

        if num_labels <= 2:  # Background only or 1 segment
            return 0.0

        segment_lengths = []

        for i in range(1, num_labels):
            segment_mask = labels == i
            length = np.sum(segment_mask) * self.pixel_size_um
            segment_lengths.append(length)

        if len(segment_lengths) > 1:
            mean_length = np.mean(segment_lengths)
            std_length = np.std(segment_lengths)

            if mean_length > 0:
                cv = 100 * std_length / mean_length
            else:
                cv = 0
        else:
            cv = 0

        return cv


class RegionalBranchAnalyzer:
    """
    Region-wise branch analysis.
    Corresponds to aggregateBranchInfoByRegion.
    """

    def __init__(self, mm_per_pixel: float, skeleton_diameter_um: float):
        """
        Parameters:
        -----------
        mm_per_pixel : float
            mm per pixel.
        skeleton_diameter_um : float
            Average vessel diameter (um).
        """
        self.mm_per_pixel = mm_per_pixel
        self.skeleton_diameter_um = skeleton_diameter_um
        self.fractal_analyzer = FractalAnalyzer()
        self.euler_analyzer = EulerAnalyzer()

    def analyze_by_region(
        self,
        skeleton: np.ndarray,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
    ) -> Dict[str, any]:
        """
        Aggregate branch information for center and periphery.

        Parameters:
        -----------
        skeleton : np.ndarray
            Skeleton image.
        center_mask : np.ndarray
            Center mask (255=center).
        periphery_mask : np.ndarray
            Periphery mask (255=periphery).

        Returns:
        --------
        results : dict
            'center': Center analysis results.
            'periphery': Periphery analysis results.
        """
        # Get branch information
        branch_info = self._get_branch_information(skeleton)

        # Classify branches by region
        center_branches, periphery_branches = self._classify_branches(
            branch_info, center_mask, periphery_mask
        )
        # Diagnostic: masks and branch counts
        try:
            print(
                f"[RegionalBranchAnalyzer] center_mask_pixels={int(np.sum(center_mask>0))}, periphery_mask_pixels={int(np.sum(periphery_mask>0))}"
            )
            print(
                f"[RegionalBranchAnalyzer] center_branches={len(center_branches)}, periphery_branches={len(periphery_branches)}"
            )
        except Exception:
            pass

        # Center analysis
        center_results = self._analyze_region(
            skeleton, center_mask, center_branches, region_name="center"
        )

        # Periphery analysis
        periphery_results = self._analyze_region(
            skeleton,
            periphery_mask,
            periphery_branches,
            region_name="periphery",
        )

        results = {"center": center_results, "periphery": periphery_results}

        return results

    def _get_branch_information(self, skeleton: np.ndarray) -> Dict:
        """
        Get branch information.

        Parameters:
        -----------
        skeleton : np.ndarray
            Skeleton image.

        Returns:
        --------
        branch_info : dict
            Branch information.
        """
        # Connected component analysis
        num_labels, labels = cv2.connectedComponents(skeleton, connectivity=8)

        branches = []

        for i in range(1, num_labels):
            component_mask = labels == i
            y_coords, x_coords = np.where(component_mask)

            if len(x_coords) < 2:
                continue

            # Start and end points (tentatively first and last)
            v1_x, v1_y = x_coords[0], y_coords[0]
            v2_x, v2_y = x_coords[-1], y_coords[-1]

            # Midpoint
            mid_x = int((v1_x + v2_x) / 2)
            mid_y = int((v1_y + v2_y) / 2)

            # Branch length
            branch_length = len(x_coords)

            # Euclidean distance
            euclidean_dist = np.sqrt((v2_x - v1_x) ** 2 + (v2_y - v1_y) ** 2)

            branches.append(
                {
                    "v1": (v1_x, v1_y),
                    "v2": (v2_x, v2_y),
                    "mid": (mid_x, mid_y),
                    "length": branch_length,
                    "euclidean_dist": euclidean_dist,
                }
            )

        return {"branches": branches}

    def _classify_branches(
        self,
        branch_info: Dict,
        center_mask: np.ndarray,
        periphery_mask: np.ndarray,
    ) -> Tuple[List, List]:
        """
        Classify branches into center/periphery (exclude boundary).

        Parameters:
        -----------
        branch_info : dict
            Branch information.
        center_mask : np.ndarray
            Center mask.
        periphery_mask : np.ndarray
            Periphery mask.

        Returns:
        --------
        center_branches : list
            Center branches.
        periphery_branches : list
            Periphery branches.
        """
        center_branches = []
        periphery_branches = []

        for branch in branch_info["branches"]:
            mid_x, mid_y = branch["mid"]

            # Boundary check
            in_center = center_mask[mid_y, mid_x] > 128
            in_periphery = periphery_mask[mid_y, mid_x] > 128

            if in_center and in_periphery:
                # Boundary branch - exclude
                continue
            elif in_center:
                center_branches.append(branch)
            elif in_periphery:
                periphery_branches.append(branch)

        return center_branches, periphery_branches

    def _analyze_region(
        self,
        skeleton: np.ndarray,
        region_mask: np.ndarray,
        branches: List,
        region_name: str = "",
    ) -> Dict:
        """
        Region analysis.

        Parameters:
        -----------
        skeleton : np.ndarray
            Skeleton image.
        region_mask : np.ndarray
            Region mask.
        branches : list
            Branch list.

        Returns:
        --------
        results : dict
            Analysis results.
        """
        # Extract skeleton within region
        region_skeleton = cv2.bitwise_and(skeleton, region_mask)
        # Diagnostic: report region stats
        try:
            region_pixels = int(np.sum(region_skeleton > 0))
            print(
                f"[FractalAnalyzer][{region_name}] region_pixels={region_pixels}, branch_count={len(branches)}"
            )
        except Exception:
            pass

        # Branch count
        branch_count = len(branches)

        # Length and tortuosity
        total_length = 0.0
        sum_weighted_tortuosity = 0.0
        threshold = self.skeleton_diameter_um / 1000.0  # um -> mm
        threshold_pixels = threshold / self.mm_per_pixel

        for branch in branches:
            length = branch["length"]
            euc_dist = branch["euclidean_dist"]

            total_length += length

            if euc_dist > threshold_pixels and euc_dist > 0:
                tortuosity = length / euc_dist
                if 1.0 <= tortuosity < 10.0:
                    sum_weighted_tortuosity += length * tortuosity

        # Convert to mm units
        total_length_mm = total_length * self.mm_per_pixel

        # Average tortuosity
        if total_length > 0:
            avg_tortuosity = sum_weighted_tortuosity / total_length
        else:
            avg_tortuosity = 0.0

        # Fractal dimension
        if np.sum(region_skeleton > 0) >= 50:
            box_sizes, box_counts = self.fractal_analyzer.box_counting(region_skeleton)
            fractal_dim, r_squared = self.fractal_analyzer.calculate_fractal_dimension(
                box_sizes, box_counts
            )
        else:
            fractal_dim = 0.0
            r_squared = 0.0

        # Euler number and loop count
        euler_number, num_loops = self.euler_analyzer.calculate_euler_number(
            region_skeleton
        )

        results = {
            "branch_count": branch_count,
            "total_length_mm": total_length_mm,
            "tortuosity": avg_tortuosity,
            "fractal_dimension": fractal_dim,
            "fractal_r_squared": r_squared,
            "euler_number": euler_number,
            "num_loops": num_loops,
        }

        return results
