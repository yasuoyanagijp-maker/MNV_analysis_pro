from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class ROI(BaseModel):
    x: int
    y: int
    w: int
    h: int

class AnalysisRequest(BaseModel):
    image_path: str
    scale_mm: float = 6.0
    save_stages: bool = True
    roi: Optional[ROI] = None
    roi_mask_b64: Optional[str] = None  # Base64-encoded pixel-accurate mask (priority over roi bbox)
    intelligent_roi: bool = True

class MNVResult(BaseModel):
    result_type: str = "MNV"
    source_filename: str = ""
    analysis_timestamp: str = ""
    mnv_area_mm2: float
    vessel_area_mm2: float
    vessel_density: float
    vessel_length_mm: float
    mean_diameter_um: float
    tortuosity: float
    fractal_dimension: float
    trunk_pattern: str
    # Network metrics
    num_branches: int = 0
    num_junctions: int = 0
    num_endpoints: int = 0
    num_loops: int = 0
    # Spatial distribution
    trunk_eccentricity: float = -1.0
    complexity_score: float = 0.0
    stability_score: float = 0.0
    maturity_index: float = 0.0
    mnv_subtype: str = "Unknown"
    # Advanced Spatial Metrics (New)
    diameter_center_mean: float = 0.0
    diameter_periphery_mean: float = 0.0
    diameter_ratio: float = 1.0
    thick_vessel_center_ratio: float = 0.0
    thick_vessel_periphery_ratio: float = 0.0
    angular_distribution_cv: float = 0.0
    radial_uniformity: float = 0.0
    # Pattern Logic Scores (New)
    tier1_score: float = 0.0
    tier2_score: float = 0.0
    tier3_score: float = 0.0
    tier4_score: float = 0.0
    # Flow deficit
    fd_percent_r1: float = 0.0
    fd_number_r1: int = 0
    fd_percent_r2: float = 0.0
    fd_number_r2: int = 0
    fd_percent_r3: float = 0.0
    fd_number_r3: int = 0
    # Paths
    binary_path: Optional[str] = None
    mask_path: Optional[str] = None
    visualization_path: Optional[str] = None
    # Base64-encoded images for Flet Web display (avoids local path issues)
    visualization_base64: Optional[str] = None
    mask_base64: Optional[str] = None
    # Pipeline scalars for ImageJ-compatible CSV (same keys as MNVPipeline.analyze minus arrays)
    csv_metrics: Optional[Dict[str, Any]] = None

class VDRequest(BaseModel):
    input_dir: str
    output_dir: str
    scale_mm: float = 6.0
    side: str = "right"
    sup_suffix: str = "1.tif"
    deep_suffix: str = "2.tif"
    single_image_mode: bool = False

class VDResult(BaseModel):
    result_type: str = "VD"
    source_filename: str = ""
    analysis_timestamp: str = ""
    patient_ids: List[str]
    superficial_files: List[str]
    deep_files: List[str]
    faz_areas: List[float]
    faz_circularities: List[float]
    superficial_whole: List[float]
    deep_whole: List[float]
    fractal_dimension_superficial: List[float]
    fractal_dimension_deep: List[float]
    tortuosity_superficial: List[float]
    tortuosity_deep: List[float]

class LoginRequest(BaseModel):
    researcher_name: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    message: str
    username: Optional[str] = None
