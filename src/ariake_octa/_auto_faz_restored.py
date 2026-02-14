"""Restored compact auto_faz_optimizer module"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Tuple, Optional, Dict
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from skimage import draw


@dataclass
class FAZReferenceConfig:
    typical_diameter_mm: float = 0.6
    diameter_range_mm: Tuple[float, float] = (0.4, 0.9)
    typical_circularity: float = 0.85
    circularity_tolerance: float = 0.2
    center_offset_ratio: float = 0.1


@dataclass
class OptimizedParameters:
    min_area_mm2: float
    max_area_mm2: float
    min_circularity: float
    max_circularity: float
    search_radius_ratio: float
    image_size: Tuple[int, int]
    pixel_size_mm: float
    optimization_score: float
    timestamp: str


class ReferenceFAZGenerator:
    def __init__(self, config: Optional[FAZReferenceConfig] = None):
        self.config = config or FAZReferenceConfig()

    def generate_reference_faz(
        self, image_shape: Tuple[int, int], pixel_size_mm: float = 0.00744
    ):
        h, w = image_shape
        cy, cx = h // 2, w // 2
        radius_px = (self.config.typical_diameter_mm / 2) / pixel_size_mm
        rr, cc = draw.disk((cy, cx), radius_px, shape=image_shape)
        m = np.zeros(image_shape, dtype=bool)
        m[rr, cc] = True
        return m

    def get_expected_metrics(
        self, image_shape: Tuple[int, int], pixel_size_mm: float = 0.00744
    ) -> Dict:
        min_d, max_d = self.config.diameter_range_mm
        min_area = np.pi * (min_d / 2) ** 2
        max_area = np.pi * (max_d / 2) ** 2
        min_circ = max(
            0.3, self.config.typical_circularity - self.config.circularity_tolerance
        )
        h, w = image_shape
        max_center_offset = min(h, w) * self.config.center_offset_ratio
        search_radius_ratio = max_center_offset / min(h, w)
        return {
            "min_area_mm2": float(min_area),
            "max_area_mm2": float(max_area),
            "min_circularity": float(min_circ),
            "max_circularity": 1.0,
            "search_radius_ratio": float(search_radius_ratio),
        }


class AutoFAZOptimizer:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        config: Optional[FAZReferenceConfig] = None,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else Path("faz_params_cache")
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.config = config or FAZReferenceConfig()
        self.ref_generator = ReferenceFAZGenerator(self.config)

    def get_optimal_parameters(
        self,
        image_shape: Tuple[int, int],
        pixel_size_mm: float = 0.00744,
        force_recalculate: bool = False,
    ) -> OptimizedParameters:
        key = hashlib.md5(f"{image_shape}_{pixel_size_mm:.6f}".encode()).hexdigest()[
            :16
        ]
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists() and not force_recalculate:
            with open(cache_file, "r") as f:
                data = json.load(f)
            return OptimizedParameters(**data)
        expected = self.ref_generator.get_expected_metrics(image_shape, pixel_size_mm)
        params = OptimizedParameters(
            min_area_mm2=expected["min_area_mm2"],
            max_area_mm2=expected["max_area_mm2"],
            min_circularity=expected["min_circularity"],
            max_circularity=expected["max_circularity"],
            search_radius_ratio=expected["search_radius_ratio"],
            image_size=image_shape,
            pixel_size_mm=pixel_size_mm,
            optimization_score=1.0,
            timestamp=datetime.now().isoformat(),
        )
        with open(cache_file, "w") as f:
            json.dump(asdict(params), f, indent=2)
        return params

    def clear_cache(self):
        for f in self.cache_dir.glob("*.json"):
            f.unlink()


def get_auto_optimized_detector(
    vessel_image,
    pixel_size_mm: float = 0.00744,
    use_test_detection: bool = False,
    cache_dir: Optional[Path] = None,
):
    # local import to avoid circular import problems
    from ariake_octa.enhanced_faz_detection import ImprovedFAZDetector

    optimizer = AutoFAZOptimizer(cache_dir=cache_dir)
    params = optimizer.get_optimal_parameters(vessel_image.shape, pixel_size_mm)
    detector = ImprovedFAZDetector(
        min_area_mm2=params.min_area_mm2,
        max_area_mm2=params.max_area_mm2,
        min_circularity=params.min_circularity,
        max_circularity=params.max_circularity,
        search_radius_ratio=params.search_radius_ratio,
        pixel_size_mm=params.pixel_size_mm,
        use_adaptive_preprocessing=True,
        remove_small_particles=True,
    )
    return detector, params
