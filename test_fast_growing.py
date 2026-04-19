import cv2
import numpy as np
import time
from src.core.fast_region_growing import fast_region_growing

def create_dummy_image(size=(800, 800)):
    """テスト用のグラデーション＋ノイズ画像を作成"""
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    
    # 手動で対象物を描画 (中心付近にあって、徐々に色が薄くなる円)
    center = (400, 400)
    for r in range(200, 0, -5):
        color = int(255 * (1.0 - r/200.0))
        cv2.circle(img, center, r, (color, color, color), -1)
        
    # 全体にノイズを付加してリアルにする
    noise = np.random.normal(0, 15, (size[0], size[1], 3)).astype(np.int8)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img

def benchmark():
    img = create_dummy_image()
    seed = (400, 400) # 画像の中心付近
    
    # Warm up
    _ = fast_region_growing(img, seed, a=1.0)
    
    print("=== ベンチマーク開始 ===")
    times = []
    
    # aの値を徐々に大きくしながら実行時間を計測（長押しを模倣）
    a_values = np.arange(0.5, 5.0, 0.1)
    
    for a in a_values:
        start_t = time.perf_counter()
        mask = fast_region_growing(img, seed, a=a)
        end_t = time.perf_counter()
        
        elapsed_ms = (end_t - start_t) * 1000
        times.append(elapsed_ms)
        area = np.sum(mask > 0)
        
        print(f"a={a:.1f} | 処理時間: {elapsed_ms:.2f} ms | 抽出面積: {area} px")
        
    avg_ms = sum(times) / len(times)
    max_ms = max(times)
    print(f"\n結果: 平均 {avg_ms:.2f} ms / 最大 {max_ms:.2f} ms")
    
    # もし30ms以下なら要件達成
    if max_ms <= 30.0:
        print("✅ 目標パフォーマンスを達成しました。（30ms以下）")
    else:
        print("⚠️ パフォーマンスの改善の余地があります。")
        
if __name__ == "__main__":
    benchmark()
