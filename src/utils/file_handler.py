"""ファイル操作のユーティリティ"""

import os
from typing import List, Tuple

import pandas as pd


class FileHandler:
    """ファイル操作クラス"""

    @staticmethod
    def create_output_directory(base_path: str, folder_name: str) -> str:
        """出力ディレクトリを作成"""
        output_path = os.path.join(base_path, folder_name)
        os.makedirs(output_path, exist_ok=True)
        return output_path

    @staticmethod
    def find_files_by_suffix(directory: str, suffix: str) -> List[str]:
        """特定のサフィックスを持つファイルを検索"""
        files = []
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                if filename.lower().endswith(suffix.lower()):
                    files.append(os.path.join(root, filename))
        return sorted(files)

    @staticmethod
    def match_file_pairs(
        files: List[str], suffix1: str, suffix2: str
    ) -> List[Tuple[str, str]]:
        """ペアになるファイルをマッチング"""
        pairs = []
        files1 = [f for f in files if f.endswith(suffix1)]
        files2 = [f for f in files if f.endswith(suffix2)]

        for f1 in files1:
            base = f1.replace(suffix1, "")
            f2 = base + suffix2
            if f2 in files2:
                pairs.append((f1, f2))

        return pairs

    @staticmethod
    def save_results_csv(data: dict, output_path: str, filename: str):
        """結果をCSVで保存"""
        df = pd.DataFrame(data)
        full_path = os.path.join(output_path, filename)
        df.to_csv(full_path, index=False)
        return full_path
