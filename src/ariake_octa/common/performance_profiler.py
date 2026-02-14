"""
Performance Profiler for ARIAKE OCTA Analysis System

処理時間計測、メモリ使用量監視、ボトルネック検出を提供します。

Author: GitHub Copilot
Version: 2.0.0-phase4
Date: 2026-01-22
"""

import json
import time

try:
    import psutil

    _HAS_PSUTIL = True
except Exception:  # pragma: no cover - best-effort fallback
    psutil = None
    _HAS_PSUTIL = False
    import warnings

    warnings.warn(
        "psutil is not installed; PerformanceProfiler will use limited fallback behavior (reduced accuracy)."
    )
import numpy as np
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Dict, List

import numpy as np
import psutil


@dataclass
class PerformanceMetrics:
    """パフォーマンスメトリクスデータクラス"""

    operation_name: str
    start_time: float
    end_time: float
    duration_seconds: float
    memory_before_mb: float
    memory_after_mb: float
    memory_delta_mb: float
    cpu_percent: float
    peak_memory_mb: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """辞書に変換"""
        return {
            "operation_name": self.operation_name,
            "duration_seconds": round(self.duration_seconds, 4),
            "duration_ms": round(self.duration_seconds * 1000, 2),
            "memory_before_mb": round(self.memory_before_mb, 2),
            "memory_after_mb": round(self.memory_after_mb, 2),
            "memory_delta_mb": round(self.memory_delta_mb, 2),
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "cpu_percent": round(self.cpu_percent, 1),
            "metadata": self.metadata,
        }


class PerformanceProfiler:
    """
    パフォーマンス測定・解析クラス

    Features:
    - 処理時間の自動計測
    - メモリ使用量の監視
    - ボトルネック検出
    - 統計レポート生成
    """

    def __init__(self, enable_profiling: bool = True):
        """
        初期化

        Parameters:
        -----------
        enable_profiling : bool
            プロファイリングの有効化（False時はオーバーヘッドなし）
        """
        self.enable_profiling = enable_profiling
        self.metrics_history: List[PerformanceMetrics] = []
        # psutil is optional; if not available we use conservative fallbacks
        self.process = psutil.Process() if _HAS_PSUTIL else None

    def _get_memory_mb(self) -> float:
        """Return current process memory usage in MB with fallbacks."""
        if self.process:
            try:
                return self.process.memory_info().rss / 1024 / 1024
            except Exception:
                return 0.0
        # Fallback using resource (best-effort, platform-dependent)
        try:
            import resource

            ru = resource.getrusage(resource.RUSAGE_SELF)
            val = float(ru.ru_maxrss)
            # Heuristic: on some platforms ru_maxrss is in bytes, on others kilobytes
            if val > 1e6:
                return val / (1024.0 * 1024.0)
            return val / 1024.0
        except Exception:
            return 0.0

    def _get_cpu_percent(self) -> float:
        """Return CPU percent used by process or 0.0 if unavailable."""
        if self.process:
            try:
                return self.process.cpu_percent()
            except Exception:
                return 0.0
        return 0.0

    def profile(self, operation_name: str = None, metadata: Dict = None):
        """
        関数デコレーター：自動プロファイリング

        Usage:
        ------
        @profiler.profile("VD Analysis")
        def analyze_vd(image):
            # 処理
            pass
        """

        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.enable_profiling:
                    return func(*args, **kwargs)

                # 操作名の決定
                op_name = operation_name or func.__name__

                # 計測開始
                with self.measure(op_name, metadata):
                    result = func(*args, **kwargs)

                return result

            return wrapper

        return decorator

    def measure(self, operation_name: str, metadata: Dict = None):
        """
        コンテキストマネージャー：計測範囲の指定

        Usage:
        ------
        with profiler.measure("Preprocessing"):
            # 計測したい処理
            pass
        """
        return _ProfilerContext(self, operation_name, metadata or {})

    def _record_metrics(self, metrics: PerformanceMetrics):
        """メトリクスを記録"""
        self.metrics_history.append(metrics)

    def get_summary(self) -> Dict:
        """
        統計サマリーを取得

        Returns:
        --------
        summary : dict
            各操作の統計情報
        """
        if not self.metrics_history:
            return {"error": "No metrics recorded"}

        # 操作名でグループ化
        operations = {}
        for metric in self.metrics_history:
            name = metric.operation_name
            if name not in operations:
                operations[name] = []
            operations[name].append(metric)

        # 各操作の統計計算
        summary = {}
        for name, metrics_list in operations.items():
            durations = [m.duration_seconds for m in metrics_list]
            memory_deltas = [m.memory_delta_mb for m in metrics_list]

            summary[name] = {
                "count": len(metrics_list),
                "total_time_seconds": round(sum(durations), 4),
                "mean_time_seconds": round(np.mean(durations), 4),
                "std_time_seconds": round(np.std(durations), 4),
                "min_time_seconds": round(min(durations), 4),
                "max_time_seconds": round(max(durations), 4),
                "mean_memory_delta_mb": round(np.mean(memory_deltas), 2),
                "max_memory_delta_mb": round(max(memory_deltas), 2),
            }

        return summary

    def get_bottlenecks(self, threshold_seconds: float = 1.0) -> List[Dict]:
        """
        ボトルネック検出

        Parameters:
        -----------
        threshold_seconds : float
            ボトルネックとみなす閾値（秒）

        Returns:
        --------
        bottlenecks : list
            遅い操作のリスト
        """
        bottlenecks = []

        for metric in self.metrics_history:
            if metric.duration_seconds >= threshold_seconds:
                bottlenecks.append(
                    {
                        "operation": metric.operation_name,
                        "duration_seconds": round(metric.duration_seconds, 4),
                        "memory_delta_mb": round(metric.memory_delta_mb, 2),
                        "metadata": metric.metadata,
                    }
                )

        # 処理時間でソート
        bottlenecks.sort(key=lambda x: x["duration_seconds"], reverse=True)

        return bottlenecks

    def get_memory_intensive_operations(
        self, threshold_mb: float = 100.0
    ) -> List[Dict]:
        """
        メモリ消費の多い操作を検出

        Parameters:
        -----------
        threshold_mb : float
            メモリ消費の閾値（MB）

        Returns:
        --------
        operations : list
            メモリ消費が大きい操作のリスト
        """
        operations = []

        for metric in self.metrics_history:
            if abs(metric.memory_delta_mb) >= threshold_mb:
                operations.append(
                    {
                        "operation": metric.operation_name,
                        "memory_delta_mb": round(metric.memory_delta_mb, 2),
                        "duration_seconds": round(metric.duration_seconds, 4),
                        "metadata": metric.metadata,
                    }
                )

        # メモリ消費量でソート
        operations.sort(key=lambda x: abs(x["memory_delta_mb"]), reverse=True)

        return operations

    def print_report(self, show_bottlenecks: bool = True):
        """
        パフォーマンスレポートを表示

        Parameters:
        -----------
        show_bottlenecks : bool
            ボトルネック情報を表示するか
        """
        print("\n" + "=" * 70)
        print("📊 Performance Report")
        print("=" * 70)

        # サマリー表示
        summary = self.get_summary()
        if "error" in summary:
            print(f"⚠️  {summary['error']}")
            return

        print("\n【Operation Summary】")
        print(
            f"{'Operation':<30} {'Count':<8} {'Total(s)':<10} {'Mean(s)':<10} {'Max(s)':<10}"
        )
        print("-" * 70)

        for name, stats in summary.items():
            print(
                f"{name:<30} {stats['count']:<8} "
                f"{stats['total_time_seconds']:<10.4f} "
                f"{stats['mean_time_seconds']:<10.4f} "
                f"{stats['max_time_seconds']:<10.4f}"
            )

        # ボトルネック表示
        if show_bottlenecks:
            bottlenecks = self.get_bottlenecks(threshold_seconds=0.5)
            if bottlenecks:
                print("\n【⚠️  Bottlenecks (>0.5s)】")
                for i, item in enumerate(bottlenecks[:5], 1):
                    print(
                        f"  {i}. {item['operation']}: {item['duration_seconds']:.4f}s "
                        f"(Memory: {item['memory_delta_mb']:+.2f}MB)"
                    )

        # メモリ消費表示
        memory_ops = self.get_memory_intensive_operations(threshold_mb=50.0)
        if memory_ops:
            print("\n【💾 Memory Intensive Operations (>50MB)】")
            for i, item in enumerate(memory_ops[:5], 1):
                print(
                    f"  {i}. {item['operation']}: {item['memory_delta_mb']:+.2f}MB "
                    f"(Duration: {item['duration_seconds']:.4f}s)"
                )

        print("\n" + "=" * 70)

    def save_report(self, filepath: str):
        """
        レポートをJSON形式で保存

        Parameters:
        -----------
        filepath : str
            保存先ファイルパス
        """
        report = {
            "summary": self.get_summary(),
            "bottlenecks": self.get_bottlenecks(),
            "memory_intensive": self.get_memory_intensive_operations(),
            "all_metrics": [m.to_dict() for m in self.metrics_history],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def reset(self):
        """メトリクス履歴をリセット"""
        self.metrics_history.clear()

    def get_total_time(self) -> float:
        """総処理時間を取得（秒）"""
        return sum(m.duration_seconds for m in self.metrics_history)

    def get_peak_memory(self) -> float:
        """ピークメモリ使用量を取得（MB）"""
        if not self.metrics_history:
            return 0.0
        return max(m.peak_memory_mb for m in self.metrics_history)


class _ProfilerContext:
    """プロファイラーコンテキストマネージャー（内部クラス）"""

    def __init__(
        self, profiler: PerformanceProfiler, operation_name: str, metadata: Dict
    ):
        self.profiler = profiler
        self.operation_name = operation_name
        self.metadata = metadata
        self.start_time = None
        self.memory_before = None

    def __enter__(self):
        if not self.profiler.enable_profiling:
            return self

        # 計測開始
        self.start_time = time.time()
        self.memory_before = self.profiler._get_memory_mb()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.profiler.enable_profiling:
            return

        # 計測終了
        end_time = time.time()
        memory_after = self.profiler._get_memory_mb()

        # メトリクス作成
        metrics = PerformanceMetrics(
            operation_name=self.operation_name,
            start_time=self.start_time,
            end_time=end_time,
            duration_seconds=end_time - self.start_time,
            memory_before_mb=self.memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=memory_after - self.memory_before,
            cpu_percent=self.profiler._get_cpu_percent(),
            peak_memory_mb=memory_after,
            metadata=self.metadata,
        )

        # 記録
        self.profiler._record_metrics(metrics)


# グローバルインスタンス（オプション）
_global_profiler = PerformanceProfiler(enable_profiling=False)


def get_global_profiler() -> PerformanceProfiler:
    """グローバルプロファイラーを取得"""
    return _global_profiler


def enable_global_profiling():
    """グローバルプロファイリングを有効化"""
    _global_profiler.enable_profiling = True


def disable_global_profiling():
    """グローバルプロファイリングを無効化"""
    _global_profiler.enable_profiling = False
