
import sys
import os
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("trace_mnv")

from core.mnv_pipeline import MNVPipeline
import numpy as np
import cv2

def trace_analysis():
    # Attempt to use the same image as the browser subagent
    image_path = "/tmp/mnv_samples/Main Report1.png"
    if not os.path.exists(image_path):
        # Fallback to any image in common locations or create a dummy one
        logger.error(f"Test image not found: {image_path}")
        return

    output_dir = ROOT / "output" / "trace_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create a dummy ROI mask (circle in the center)
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    h, w = img.shape
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(roi_mask, (w//2, h//2), min(w, h)//4, 255, -1)

    pipeline = MNVPipeline(scale_mm=6.0)
    
    logger.info("Starting MNV analysis trigger...")
    try:
        res = pipeline.analyze(
            image_path,
            output_dir=str(output_dir),
            roi_mask=roi_mask
        )
        logger.info("Analysis completed successfully!")
        print(f"Result metrics: {res.get('metrics', {}).keys()}")
    except Exception as e:
        logger.error("Analysis failed!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    trace_analysis()
