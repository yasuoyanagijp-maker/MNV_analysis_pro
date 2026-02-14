"""
CSV export utilities for analysis results
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class CSVExporter:
    """
    解析結果をCSV形式で保存
    """

    @staticmethod
    def export_metrics(
        metrics: Dict, output_path: str, include_timestamp: bool = True
    ) -> None:
        """
        メトリクスをCSVファイルに保存

        Args:
            metrics: メトリクス辞書
            output_path: 出力ファイルパス
            include_timestamp: タイムスタンプを含めるか
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # タイムスタンプ追加
        if include_timestamp:
            metrics["timestamp"] = datetime.now().isoformat()

        # CSV書き込み
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # ヘッダー
            writer.writerow(["Metric", "Value"])

            # データ
            for key, value in metrics.items():
                writer.writerow([key, value])

    @staticmethod
    def export_batch(
        metrics_list: List[Dict], output_path: str, file_ids: List[str] = None
    ) -> None:
        """
        複数の解析結果を1つのCSVファイルに保存

        Args:
            metrics_list: メトリクス辞書のリスト
            output_path: 出力ファイルパス
            file_ids: ファイル識別子のリスト（オプション）
        """
        if not metrics_list:
            return

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 全メトリクスのキーを収集
        all_keys = set()
        for metrics in metrics_list:
            all_keys.update(metrics.keys())

        all_keys = sorted(all_keys)

        # CSV書き込み
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # ヘッダー
            header = ["File_ID"] if file_ids else []
            header.extend(all_keys)
            writer.writerow(header)

            # データ
            for i, metrics in enumerate(metrics_list):
                row = []
                if file_ids:
                    row.append(file_ids[i] if i < len(file_ids) else f"file_{i}")
                row.extend([metrics.get(key, "") for key in all_keys])
                writer.writerow(row)
