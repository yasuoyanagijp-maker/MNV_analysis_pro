"""
Result Cache System for ARIAKE OCTA Analysis System

中間結果のキャッシュによる高速化とメモリ効率化を実現します。

Author: GitHub Copilot
Version: 2.0.0-phase4
Date: 2026-01-22
"""

import hashlib
import json
import pickle
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np


class ResultCache:
    """
    結果キャッシュクラス

    Features:
    - メモリキャッシュ（高速）
    - ディスクキャッシュ（永続化）
    - 自動有効期限管理
    - キャッシュヒット率統計
    """

    def __init__(
        self,
        cache_dir: str = ".cache",
        max_memory_items: int = 100,
        default_ttl_seconds: int = 3600,
        enable_disk_cache: bool = True,
    ):
        """
        初期化

        Parameters:
        -----------
        cache_dir : str
            ディスクキャッシュディレクトリ
        max_memory_items : int
            メモリキャッシュの最大アイテム数
        default_ttl_seconds : int
            デフォルトキャッシュ有効期限（秒）
        enable_disk_cache : bool
            ディスクキャッシュを有効化
        """
        self.cache_dir = Path(cache_dir)
        self.max_memory_items = max_memory_items
        self.default_ttl_seconds = default_ttl_seconds
        self.enable_disk_cache = enable_disk_cache

        # メモリキャッシュ
        self._memory_cache: Dict[str, Dict] = {}

        # 統計
        self.stats = {
            "hits": 0,
            "misses": 0,
            "memory_hits": 0,
            "disk_hits": 0,
            "saves": 0,
        }

        # ディスクキャッシュディレクトリ作成
        if self.enable_disk_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, *args, **kwargs) -> str:
        """
        引数からキャッシュキーを生成

        Parameters:
        -----------
        *args, **kwargs : any
            キャッシュキー生成用の引数

        Returns:
        --------
        key : str
            キャッシュキー（ハッシュ値）
        """

        # NumPy配列は内容のハッシュを使用
        def serialize_value(val):
            if isinstance(val, np.ndarray):
                return ("ndarray", val.tobytes(), val.shape, val.dtype.str)
            elif isinstance(val, (list, tuple)):
                return (
                    type(val).__name__,
                    tuple(serialize_value(v) for v in val),
                )
            elif isinstance(val, dict):
                return (
                    "dict",
                    tuple((k, serialize_value(v)) for k, v in sorted(val.items())),
                )
            else:
                return val

        serialized_args = serialize_value(args)
        serialized_kwargs = serialize_value(kwargs)

        key_data = json.dumps([serialized_args, serialized_kwargs], sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        キャッシュから取得

        Parameters:
        -----------
        key : str
            キャッシュキー

        Returns:
        --------
        value : any or None
            キャッシュされた値（存在しない or 期限切れの場合はNone）
        """
        # メモリキャッシュから取得
        if key in self._memory_cache:
            cache_entry = self._memory_cache[key]

            # 有効期限チェック
            if time.time() < cache_entry["expires_at"]:
                self.stats["hits"] += 1
                self.stats["memory_hits"] += 1
                return cache_entry["value"]
            else:
                # 期限切れ削除
                del self._memory_cache[key]

        # ディスクキャッシュから取得
        if self.enable_disk_cache:
            cache_file = self.cache_dir / f"{key}.pkl"
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        cache_entry = pickle.load(f)

                    # 有効期限チェック
                    if time.time() < cache_entry["expires_at"]:
                        # メモリキャッシュに昇格
                        self._put_memory(
                            key, cache_entry["value"], cache_entry["expires_at"]
                        )

                        self.stats["hits"] += 1
                        self.stats["disk_hits"] += 1
                        return cache_entry["value"]
                    else:
                        # 期限切れ削除
                        cache_file.unlink()
                except Exception:
                    pass

        # キャッシュミス
        self.stats["misses"] += 1
        return None

    def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        キャッシュに保存

        Parameters:
        -----------
        key : str
            キャッシュキー
        value : any
            保存する値
        ttl_seconds : int, optional
            有効期限（秒）
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = time.time() + ttl

        # メモリキャッシュに保存
        self._put_memory(key, value, expires_at)

        # ディスクキャッシュに保存
        if self.enable_disk_cache:
            self._put_disk(key, value, expires_at)

        self.stats["saves"] += 1

    def _put_memory(self, key: str, value: Any, expires_at: float):
        """メモリキャッシュに保存"""
        # 容量制限チェック
        if len(self._memory_cache) >= self.max_memory_items:
            # 最も古いエントリを削除（FIFO）
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]

        self._memory_cache[key] = {"value": value, "expires_at": expires_at}

    def _put_disk(self, key: str, value: Any, expires_at: float):
        """ディスクキャッシュに保存"""
        cache_file = self.cache_dir / f"{key}.pkl"

        try:
            cache_entry = {"value": value, "expires_at": expires_at}

            with open(cache_file, "wb") as f:
                pickle.dump(cache_entry, f)
        except Exception:
            # 保存失敗は無視
            pass

    def cached(self, ttl_seconds: Optional[int] = None):
        """
        関数デコレーター：自動キャッシュ

        Parameters:
        -----------
        ttl_seconds : int, optional
            有効期限（秒）

        Usage:
        ------
        @cache.cached(ttl_seconds=600)
        def expensive_function(x, y):
            # 重い処理
            return result
        """

        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # キャッシュキー生成
                cache_key = self._generate_key(func.__name__, *args, **kwargs)

                # キャッシュから取得
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # 関数実行
                result = func(*args, **kwargs)

                # キャッシュに保存
                self.put(cache_key, result, ttl_seconds)

                return result

            return wrapper

        return decorator

    def clear_memory(self):
        """メモリキャッシュをクリア"""
        self._memory_cache.clear()

    def clear_disk(self):
        """ディスクキャッシュをクリア"""
        if self.enable_disk_cache and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.pkl"):
                cache_file.unlink()

    def clear_all(self):
        """全キャッシュをクリア"""
        self.clear_memory()
        self.clear_disk()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "memory_hits": 0,
            "disk_hits": 0,
            "saves": 0,
        }

    def get_stats(self) -> Dict:
        """
        キャッシュ統計を取得

        Returns:
        --------
        stats : dict
            統計情報
        """
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0
        )

        return {
            "total_requests": total_requests,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "memory_hits": self.stats["memory_hits"],
            "disk_hits": self.stats["disk_hits"],
            "saves": self.stats["saves"],
            "memory_cache_size": len(self._memory_cache),
        }

    def print_stats(self):
        """統計情報を表示"""
        stats = self.get_stats()

        print("\n" + "=" * 50)
        print("💾 Cache Statistics")
        print("=" * 50)
        print(f"  Total requests: {stats['total_requests']}")
        print(f"  Hits: {stats['hits']} ({stats['hit_rate_percent']:.2f}%)")
        print(f"  Misses: {stats['misses']}")
        print(f"  Memory hits: {stats['memory_hits']}")
        print(f"  Disk hits: {stats['disk_hits']}")
        print(f"  Saves: {stats['saves']}")
        print(f"  Memory cache size: {stats['memory_cache_size']}")
        print("=" * 50)

    def cleanup_expired(self):
        """期限切れキャッシュを削除"""
        current_time = time.time()

        # メモリキャッシュ
        expired_keys = [
            key
            for key, entry in self._memory_cache.items()
            if current_time >= entry["expires_at"]
        ]
        for key in expired_keys:
            del self._memory_cache[key]

        # ディスクキャッシュ
        if self.enable_disk_cache:
            for cache_file in self.cache_dir.glob("*.pkl"):
                try:
                    with open(cache_file, "rb") as f:
                        cache_entry = pickle.load(f)

                    if current_time >= cache_entry["expires_at"]:
                        cache_file.unlink()
                except Exception:
                    pass

    def get_cache_size_mb(self) -> float:
        """
        ディスクキャッシュのサイズを取得（MB）

        Returns:
        --------
        size_mb : float
            キャッシュサイズ
        """
        if not self.enable_disk_cache or not self.cache_dir.exists():
            return 0.0

        total_bytes = sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl"))
        return total_bytes / 1024 / 1024


# グローバルキャッシュインスタンス
_global_cache = ResultCache(enable_disk_cache=False)


def get_global_cache() -> ResultCache:
    """グローバルキャッシュを取得"""
    return _global_cache


def enable_global_disk_cache(cache_dir: str = ".cache"):
    """グローバルディスクキャッシュを有効化"""
    global _global_cache
    _global_cache = ResultCache(cache_dir=cache_dir, enable_disk_cache=True)
