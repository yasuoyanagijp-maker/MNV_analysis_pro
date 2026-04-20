import cv2
import numpy as np
import time

def fast_region_growing(img: np.ndarray, seed: tuple[int, int], a: float, window_size: int = 5) -> np.ndarray:
    """
    OpenCVを用いた高速なリージョングローイング関数。
    シード点周囲の局所統計量(μ, σ)を基準に、許容範囲 μ ± a*σ を満たし、
    かつシード点と連結している画素のみを抽出する。
    """
    x, y = seed
    h, w = img.shape[:2]
    
    # 画像範囲外のシードのセーフティチェック
    if x < 0 or x >= w or y < 0 or y >= h:
        return np.zeros((h, w), dtype=np.uint8)
        
    # 1. 局所統計量 (μ, σ) の計算
    half_w = window_size // 2
    y_min, y_max = max(0, y - half_w), min(h, y + half_w + 1)
    x_min, x_max = max(0, x - half_w), min(w, x + half_w + 1)
    
    roi_init = img[y_min:y_max, x_min:x_max]
    
    if len(img.shape) == 3: # カラー画像
        mu = np.mean(roi_init, axis=(0, 1))
        sigma = np.std(roi_init, axis=(0, 1))
    else: # グレースケール
        mu = np.mean(roi_init)
        sigma = np.std(roi_init)
        
    # 標準偏差が0（単一色）の場合、抽出範囲を持たせるために最低値を設定
    sigma = np.maximum(sigma, 0.5)
    
    # 2. 許容範囲の計算 [μ - a*σ, μ + a*σ]
    low = np.clip(mu - a * sigma, 0, 255)
    high = np.clip(mu + a * sigma, 0, 255)
    
    if isinstance(low, np.ndarray):
        low = tuple(low.tolist())
        high = tuple(high.tolist())
    else:
        low = float(low)
        high = float(high)
        
    # 3. ポテンシャルマスクの一括生成
    potential_mask = cv2.inRange(img, low, high)
    
    # 4. シード点からの連結成分抽出 (floodFillを使用)
    if potential_mask[y, x] == 0:
        return np.zeros((h, w), dtype=np.uint8)
        
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    flood_mask[1:-1, 1:-1] = np.where(potential_mask == 0, 1, 0).astype(np.uint8)
    
    flags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY
    image_dummy = np.zeros((h, w), dtype=np.uint8)
    cv2.floodFill(image_dummy, flood_mask, seed, 0, 0, 0, flags)
    
    result_mask = np.where(flood_mask[1:-1, 1:-1] == 255, 255, 0).astype(np.uint8)
    
    return result_mask
