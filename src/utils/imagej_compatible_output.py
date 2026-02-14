"""
ImageJ-compatible output structure generator
ImageJマクロと同じフォルダー構造・ファイル名でデータを出力
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
import pandas as pd


class ImageJOutputManager:
    """
    ImageJマクロと互換性のある出力を管理するクラス

    フォルダー構造:
    - output_dir/
      - {MainFolder}_VD/
        - {patient_id}_original.jpg
        - {patient_id}_.jpg
        - Results-VD.csv
        - ARIAKE_Registration_Log.txt
      - {MainFolder}_MNV/
        - MNV_{patient_id}.jpg (Visualization_RGB)
        - FD_{patient_id}.jpg
        - {MainFolder}_MNV.csv
        - {MainFolder}_Parameter.csv
        - ARIAKE_Registration_Log.txt
    """

    def __init__(self, output_base_dir: str, main_folder_name: str):
        """
        Parameters:
        -----------
        output_base_dir : str
            出力ベースディレクトリ
        main_folder_name : str
            メインフォルダー名（通常は入力フォルダー名）
        """
        self.output_base_dir = Path(output_base_dir)
        self.main_folder_name = main_folder_name

        # VD出力ディレクトリ
        self.vd_output_dir = self.output_base_dir / f"{main_folder_name}_VD"

        # MNV出力ディレクトリ
        self.mnv_output_dir = self.output_base_dir / f"{main_folder_name}_MNV"

    def create_vd_structure(self):
        """VD解析用のディレクトリ構造を作成"""
        self.vd_output_dir.mkdir(parents=True, exist_ok=True)
        return self.vd_output_dir

    def create_mnv_structure(self):
        """MNV解析用のディレクトリ構造を作成"""
        self.mnv_output_dir.mkdir(parents=True, exist_ok=True)
        return self.mnv_output_dir

    # ================================================================
    # VD解析出力
    # ================================================================

    def save_vd_stage_image(
        self, image: np.ndarray, patient_id: str, stage_name: str = "original"
    ):
        """
        VD解析の段階画像を保存（ImageJ saveStageVD相当）

        Parameters:
        -----------
        image : np.ndarray
            保存する画像
        patient_id : str
            患者ID
        stage_name : str
            ステージ名 ("original", "processed"など)
        """
        if stage_name == "original":
            filename = f"{patient_id}_original.jpg"
        else:
            filename = f"{patient_id}_{stage_name}.jpg"

        filepath = self.vd_output_dir / filename

        # RGB変換
        if len(image.shape) == 2:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            image_rgb = image

        # 保存
        cv2.imwrite(str(filepath), image_rgb)
        return filepath

    def create_vd_table(self, results: Dict) -> Path:
        """
        VD解析結果テーブルを作成（ImageJ createVDTable相当）

        Parameters:
        -----------
        results : dict
            VD解析結果

        Returns:
        --------
        filepath : Path
            保存されたCSVファイルのパス
        """
        # Results-VD.csv を作成
        df = pd.DataFrame(
            {
                "Patient ID": results.get("patient_ids", []),
                "Superficial Image ID": results.get("superficial_files", []),
                "Deep Image ID": results.get("deep_files", []),
                "FAZ (mm^2)": results.get("faz_areas", []),
                "Circularity": results.get("faz_circularity", []),
                "Superficial": results.get("superficial_vessel_densities", []),
                "Superior Area (Superficial)": results.get("sup_superficial", []),
                "Temporal Area (Superficial)": results.get("temp_superficial", []),
                "Nasal Area (Superficial)": results.get("nasal_superficial", []),
                "Inferior Area (Superficial)": results.get("inf_superficial", []),
                "Deep": results.get("deep_vessel_densities", []),
                "Superior Area (Deep)": results.get("sup_deep", []),
                "Temporal Area (Deep)": results.get("temp_deep", []),
                "Nasal Area (Deep)": results.get("nasal_deep", []),
                "Inferior Area (Deep)": results.get("inf_deep", []),
                "Fractal Dimension (Superficial)": results.get(
                    "fractal_dimension_superficial", []
                ),
                "Fractal Dimension (Deep)": results.get(
                    "fractal_dimension_deep", []
                ),
                "Tortuosity (Superficial)": results.get(
                    "tortuosity_superficial", []
                ),
                "Tortuosity (Deep)": results.get("tortuosity_deep", []),
            }
        )

        filepath = self.vd_output_dir / "Results-VD.csv"
        df.to_csv(filepath, index=False)

        return filepath

    # ================================================================
    # MNV解析出力
    # ================================================================

    def save_mnv_visualization(
        self,
        image: np.ndarray,
        patient_id: str,
        area_mm2: float = None,
        image_type: str = "MNV",
    ) -> Path:
        """
        MNV可視化画像を保存（ImageJ saveStageImproved相当）

        Parameters:
        -----------
        image : np.ndarray
            保存する画像
        patient_id : str
            患者ID（ファイル名）
        area_mm2 : float, optional
            MNV面積（画像にテキストとして追加）
        image_type : str
            画像タイプ ("MNV", "FD")
        """
        # ファイル名: MNV_{patient_id}.jpg or FD_{patient_id}.jpg
        filename = f"{image_type}_{patient_id}.jpg"
        filepath = self.mnv_output_dir / filename

        # cv2.imwrite は BGR を期待するため、RGB→BGR 変換
        if len(image.shape) == 2:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        else:
            image_rgb = image.copy()

        # テキスト追加（面積情報）
        if area_mm2 is not None:
            h, w = image_rgb.shape[:2]
            text = f"Area: {area_mm2:.2f} mm²"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = h * 0.0005  # 画像サイズに応じたスケール
            thickness = max(1, int(h * 0.002))

            # テキストサイズを取得
            (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)

            # 中央下部に配置
            x = (w - text_w) // 2
            y = h - int(text_h * 2.1)

            # 白色でテキスト描画
            cv2.putText(
                image_rgb,
                text,
                (x, y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
            )

        # スケールバー追加（オプション）
        # ImageJの "Scale Bar..." コマンド相当
        # 実装は簡略化

        # 保存
        cv2.imwrite(str(filepath), image_rgb)
        return filepath

    def create_mnv_measurements_table(self, results: Dict) -> Path:
        """
        MNV測定結果テーブルを作成（ImageJ measurements table相当）

        Parameters:
        -----------
        results : dict
            MNV解析結果の辞書
        """
        # カラム名はImageJマクロと完全一致
        df = pd.DataFrame(
            {
                "ID": results.get("patient_ids", []),
                "File": results.get("filenames", []),
                "Subtype": results.get("mnv_subtype", []),
                "MNV Area (mm2)": results.get("mnv_area_mm2", []),
                "Vsl Area (mm2)": results.get("vessel_area_mm2", []),
                "Vsl Density (Vessel Area/MNV (%))": results.get("vessel_density", []),
                "Vessel density index adjusted by signal intensity (aVDI)": results.get(
                    "vessel_density_index", []
                ),
                "MNV Area adjusted by signal intensity (aMNV)": results.get(
                    "immature_vessel_area_index", []
                ),
                "Vsl Length (mm)": results.get("vessel_length_mm", []),
                "Dilated vessel (%)": results.get("high_skew_percentage", []),
                "Maturity Index": results.get("maturity_index", []),
                "Caliber Uniformity Score": results.get("stability_score", []),
                "Network Complexity Score": results.get("complexity_score", []),
                "Junction Density (n/mm)": results.get("junction_density", []),
                "End Pts Density (n/mm)": results.get("endpoint_density", []),
                "Multi-Branch Pts Density (n/mm)": results.get("multiple_density", []),
                "Branch Density (n/mm)": results.get("branch_density", []),
                # Flow Deficit
                "FD% (R1)": results.get("FD_percent_R1", []),
                "FD Avg Area µm² (R1)": results.get("FD_average_area_R1", []),
                "FD number (R1)": results.get("FD_number_R1", []),
                "FD density /mm² (R1)": results.get("FD_density_R1", []),
                "FD% (R2)": results.get("FD_percent_R2", []),
                "FD Avg Area µm² (R2)": results.get("FD_average_area_R2", []),
                "FD number (R2)": results.get("FD_number_R2", []),
                "FD density /mm² (R2)": results.get("FD_density_R2", []),
                "FD% (R3)": results.get("FD_percent_R3", []),
                "FD Avg Area µm² (R3)": results.get("FD_average_area_R3", []),
                "FD number (R3)": results.get("FD_number_R3", []),
                "FD density /mm² (R3)": results.get("FD_density_R3", []),
                # 空間分布
                "Center Branches": results.get("center_branch", []),
                "Center Total Length (mm)": results.get("vessel_length_center", []),
                "Center Tortuosity": results.get("tortuosity_center", []),
                "Center FD (Box-Counting)": results.get("FD_center", []),
                "Center Euler Number": results.get("euler_center", []),
                "Center Loop Number": results.get("loop_center", []),
                "Periphery Branches": results.get("periphery_branch", []),
                "Periphery Total Length (mm)": results.get(
                    "vessel_length_periphery", []
                ),
                "Periphery Tortuosity": results.get("tortuosity_periphery", []),
                "Periphery FD (Box-Counting)": results.get("FD_periphery", []),
                "Periphery Euler Number": results.get("euler_periphery", []),
                "Periphery Loop Number": results.get("loop_periphery", []),
                # その他
                "MNV mean gray intensity (AU)": results.get("mean_intensity", []),
                "Fractal Dim": results.get("fractal_dimension", []),
                "Tortuosity": results.get("tortuosity", []),
                "MNV intensity Variation (CV)": results.get("standard_deviation", []),
                "NV Diameter (CV)": results.get("cv_diameter", []),
                "(Skel) Vsl Diameter": results.get("mean_diameter_um", []),
                "End Pts": results.get("num_endpoints", []),
                "Vsl Branches": results.get("num_branches", []),
                "Vsl Junctions": results.get("num_junctions", []),
                "Triple Pts": results.get("triple_points", []),
                "Quadruple Pts": results.get("quadruple_points", []),
                "Raw Vsl Length": results.get("raw_vessel_length", []),
                "Raw Vsl Diameter": results.get("raw_vessel_diameter", []),
                "Quality of analysis": results.get("quality_control", []),
            }
        )

        # ファイル名: {MainFolder}_MNV.csv
        filepath = self.mnv_output_dir / f"{self.main_folder_name}_MNV.csv"
        df.to_csv(filepath, index=False)

        return filepath

    def create_mnv_parameter_file(
        self,
        scale_mm: float,
        tubeness_sigma: float = 1.0,
        log_sigma: float = 1.0,
        num_files: int = 0,
    ) -> Path:
        """
        MNV解析パラメータファイルを作成

        Parameters:
        -----------
        scale_mm : float
            画像スケール（mm）
        tubeness_sigma : float
            Tubenessフィルタのsigma
        log_sigma : float
            LoG(Mexican Hat)フィルタのsigma
        num_files : int
            処理ファイル数
        """
        now = datetime.now()

        # パラメータファイル内容
        content = []
        content.append("Parameter,Value")
        content.append(f"Date, {now.strftime('%a %d-%b-%Y')}")
        content.append(f"Time, {now.strftime('%H:%M:%S')}")
        content.append(f"Width (mm),{scale_mm}")
        content.append(f"Tubeness Filter Sigma,{tubeness_sigma}")
        content.append(f"Laplacian of Gaussian Filter Sigma,{log_sigma}")
        content.append(f"Processed Files,{num_files}")

        # ファイル名: {MainFolder}_Parameter.csv
        filepath = self.mnv_output_dir / f"{self.main_folder_name}_Parameter.csv"

        with open(filepath, "w") as f:
            f.write("\n".join(content))

        return filepath

    # ================================================================
    # ログ出力
    # ================================================================

    def save_log_file(
        self,
        log_content: str,
        analyst_name: str = "Python Analysis",
        analysis_type: str = "VD",
    ) -> Path:
        """
        作業者ログを保存（ImageJ saveLogToFile相当）

        Parameters:
        -----------
        log_content : str
            ログ内容
        analyst_name : str
            解析者名
        analysis_type : str
            解析タイプ ("VD" or "MNV")
        """
        # 出力ディレクトリを選択
        if analysis_type == "VD":
            output_dir = self.vd_output_dir
        else:
            output_dir = self.mnv_output_dir

        # ログヘッダー
        now = datetime.now()
        header = [
            "=================================================",
            "ARIAKE OCTA v2.1 (Python Implementation)",
            f"Log File Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Analyzed by: {analyst_name}",
            "=================================================",
            "",
        ]

        # 完全なログ
        full_log = "\n".join(header) + "\n" + log_content

        # ファイル名
        filepath = output_dir / "ARIAKE_Registration_Log.txt"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_log)

        return filepath

    # ================================================================
    # ZIPアーカイブ作成
    # ================================================================

    def create_download_package(self, analysis_type: str = "Both") -> Optional[Path]:
        """
        ダウンロード用ZIPパッケージを作成

        Parameters:
        -----------
        analysis_type : str
            "VD", "MNV", or "Both"
        """
        import zipfile

        zip_filename = f"{self.main_folder_name}_Analysis.zip"
        zip_path = self.output_base_dir / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # VDファイルを追加
            if analysis_type in ["VD", "Both"]:
                if self.vd_output_dir.exists():
                    for file in self.vd_output_dir.rglob("*"):
                        if file.is_file():
                            arcname = file.relative_to(self.output_base_dir)
                            zipf.write(file, arcname)

            # MNVファイルを追加
            if analysis_type in ["MNV", "Both"]:
                if self.mnv_output_dir.exists():
                    for file in self.mnv_output_dir.rglob("*"):
                        if file.is_file():
                            arcname = file.relative_to(self.output_base_dir)
                            zipf.write(file, arcname)

        return zip_path
