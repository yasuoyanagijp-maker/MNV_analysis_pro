"""
Image Saver Module

可視化画像をJPEG形式で保存。
スケールバー、テキストオーバーレイを統合して保存。

Author: ARIAKE OCTA Analysis Team
Date: 2026-01-22
"""

from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np


class ImageSaver:
    """
    画像保存器

    可視化画像をJPEG形式で保存。
    品質、圧縮設定を管理。
    """

    def __init__(self, jpeg_quality: int = 95, create_subdirs: bool = True):
        """
        Parameters
        ----------
        jpeg_quality : int
            JPEG圧縮品質 (0-100)
        create_subdirs : bool
            サブディレクトリを自動作成するか
        """
        self.jpeg_quality = jpeg_quality
        self.create_subdirs = create_subdirs

    def save_image(
        self, image: np.ndarray, output_path: str, create_dir: bool = True
    ) -> bool:
        """
        画像を保存

        Parameters
        ----------
        image : np.ndarray
            保存する画像
        output_path : str
            保存先パス
        create_dir : bool
            ディレクトリを作成するか

        Returns
        -------
        bool
            保存成功したかどうか
        """
        try:
            # ディレクトリ作成
            if create_dir:
                output_dir = Path(output_path).parent
                output_dir.mkdir(parents=True, exist_ok=True)

            # JPEG保存
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            success = cv2.imwrite(str(output_path), image, encode_param)

            return success

        except Exception as e:
            print(f"Error saving image: {e}")
            return False

    def save_mnv_visualizations(
        self, visualizations: Dict[str, np.ndarray], output_dir: str, file_id: str
    ) -> Dict[str, str]:
        """
        MNV可視化画像セットを保存

        Parameters
        ----------
        visualizations : dict
            可視化画像の辞書
            - 'rgb': RGB合成画像
            - 'color_coded': 擬似カラー画像
            - 'flow_deficit': Flow Deficit可視化
        output_dir : str
            出力ディレクトリ
        file_id : str
            ファイルID

        Returns
        -------
        dict
            保存されたファイルパスの辞書
        """
        saved_paths = {}

        # 出力ディレクトリ作成
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # RGB合成画像
        if "rgb" in visualizations:
            rgb_path = output_path / f"{file_id}_MNV_RGB.jpg"
            if self.save_image(visualizations["rgb"], str(rgb_path), create_dir=False):
                saved_paths["rgb"] = str(rgb_path)

        # 擬似カラー画像
        if "color_coded" in visualizations:
            cc_path = output_path / f"{file_id}_Color_coded.jpg"
            if self.save_image(
                visualizations["color_coded"], str(cc_path), create_dir=False
            ):
                saved_paths["color_coded"] = str(cc_path)

        # Flow Deficit可視化
        if "flow_deficit" in visualizations:
            fd_path = output_path / f"{file_id}_FlowDeficit.jpg"
            if self.save_image(
                visualizations["flow_deficit"], str(fd_path), create_dir=False
            ):
                saved_paths["flow_deficit"] = str(fd_path)

        # 元画像（オプション）
        if "original" in visualizations:
            orig_path = output_path / f"{file_id}_Original.jpg"
            if self.save_image(
                visualizations["original"], str(orig_path), create_dir=False
            ):
                saved_paths["original"] = str(orig_path)

        # 二値画像（オプション）
        if "binary" in visualizations:
            binary_path = output_path / f"{file_id}_Binary.jpg"
            if self.save_image(
                visualizations["binary"], str(binary_path), create_dir=False
            ):
                saved_paths["binary"] = str(binary_path)

        return saved_paths

    def add_watermark(
        self,
        image: np.ndarray,
        text: str = "ARIAKE OCTA",
        position: str = "bottom-left",
        font_scale: float = 0.5,
        color: Tuple[int, int, int] = (200, 200, 200),
        thickness: int = 1,
    ) -> np.ndarray:
        """
        ウォーターマークを追加

        Parameters
        ----------
        image : np.ndarray
            画像
        text : str
            ウォーターマークテキスト
        position : str
            位置
        font_scale : float
            フォントスケール
        color : tuple
            テキスト色 (B, G, R)
        thickness : int
            テキスト太さ

        Returns
        -------
        np.ndarray
            ウォーターマーク付き画像
        """
        image_with_wm = image.copy()
        h, w = image.shape[:2]

        # テキストサイズ取得
        text_size = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )[0]

        # 位置計算
        margin = 10
        if position == "bottom-left":
            x = margin
            y = h - margin
        elif position == "bottom-right":
            x = w - text_size[0] - margin
            y = h - margin
        elif position == "top-left":
            x = margin
            y = text_size[1] + margin
        else:  # top-right
            x = w - text_size[0] - margin
            y = text_size[1] + margin

        # テキスト描画
        cv2.putText(
            image_with_wm,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

        return image_with_wm

    def create_thumbnail(
        self, image: np.ndarray, max_size: Tuple[int, int] = (256, 256)
    ) -> np.ndarray:
        """
        サムネイル画像を作成

        Parameters
        ----------
        image : np.ndarray
            元画像
        max_size : tuple
            最大サイズ (width, height)

        Returns
        -------
        np.ndarray
            サムネイル画像
        """
        h, w = image.shape[:2]
        max_w, max_h = max_size

        # アスペクト比を維持してリサイズ
        scale = min(max_w / w, max_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        thumbnail = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return thumbnail


def create_saver(jpeg_quality: int = 95) -> ImageSaver:
    """
    デフォルトパラメータで保存器を作成

    Parameters
    ----------
    jpeg_quality : int
        JPEG品質 (0-100)

    Returns
    -------
    ImageSaver
        画像保存器
    """
    return ImageSaver(jpeg_quality=jpeg_quality, create_subdirs=True)
