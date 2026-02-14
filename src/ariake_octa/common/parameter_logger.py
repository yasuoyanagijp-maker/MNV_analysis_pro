"""
Parameter logging utilities
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict


class ParameterLogger:
    """
    処理パラメータをログファイルに記録
    """

    @staticmethod
    def log(params: Dict, output_path: str) -> None:
        """
        パラメータをJSONファイルに保存

        Args:
            params: パラメータ辞書
            output_path: 出力ファイルパス
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # タイムスタンプ追加
        log_data = {"timestamp": datetime.now().isoformat(), "parameters": params}

        # JSON書き込み
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def append(params: Dict, output_path: str) -> None:
        """
        既存のログファイルに追記

        Args:
            params: パラメータ辞書
            output_path: 出力ファイルパス
        """
        path = Path(output_path)

        # 既存データを読み込み
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                log_data = json.load(f)

            if "history" not in log_data:
                log_data["history"] = []
        else:
            log_data = {"history": []}

        # 新しいエントリを追加
        entry = {"timestamp": datetime.now().isoformat(), "parameters": params}
        log_data["history"].append(entry)

        # 書き込み
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
