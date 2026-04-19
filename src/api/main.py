import sys
import os
from pathlib import Path

# Add project root and src to sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from src.api.schemas import AnalysisRequest, MNVResult, VDRequest, VDResult, LoginRequest, AuthResponse
from core.mnv_pipeline import MNVPipeline
from core.vd_analysis import VDAnalyzer
import shutil
import cv2
import numpy as np
import uuid
import uvicorn
from datetime import datetime

app = FastAPI(title="ARIAKE OCTA Engine API")

# Store results in memory for now (or a simple cache)
results_cache = {}

@app.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    # Alpha version: Simple researcher authentication
    # Alpha version: Simple researcher authentication
    # In a real app, this would check against a DB with hashed passwords
    if request.password == "ariake2024":
        return AuthResponse(
            success=True, 
            message="Welcome, researcher.", 
            username=request.researcher_name
        )
    else:
        return AuthResponse(
            success=False, 
            message="Invalid credentials. Please contact the administrator."
        )

@app.post("/analyze/mnv", response_model=MNVResult)
async def analyze_mnv(request: AnalysisRequest):
    try:
        import base64
        # Create unique output directory for this run
        run_id = str(uuid.uuid4())
        output_dir = ROOT / "output" / "mnv" / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Handle ROI — priority: roi_mask_b64 > roi bbox > None (auto-detect)
        roi_mask = None
        
        if request.roi_mask_b64:
            # Decode pixel-accurate mask from base64
            mask_bytes = base64.b64decode(request.roi_mask_b64)
            mask_arr = np.frombuffer(mask_bytes, dtype=np.uint8)
            mask_img = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)
            if mask_img is not None:
                # Resize to match input image if needed
                img = cv2.imread(request.image_path, cv2.IMREAD_GRAYSCALE)
                if img is not None and mask_img.shape != img.shape:
                    mask_img = cv2.resize(mask_img, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                roi_mask = mask_img
        elif request.roi:
            img = cv2.imread(request.image_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                roi_mask = np.zeros(img.shape, dtype=np.uint8)
                h, w = img.shape
                x = max(0, min(request.roi.x, w-1))
                y = max(0, min(request.roi.y, h-1))
                rw = max(1, min(request.roi.w, w - x))
                rh = max(1, min(request.roi.h, h - y))
                cv2.rectangle(roi_mask, (x, y), (x + rw, y + rh), 255, -1)
        
        pipeline = MNVPipeline(
            scale_mm=request.scale_mm,
            save_stages=request.save_stages,
            enable_roi_refinement=request.intelligent_roi,
            verbose=True
        )
        
        # Call the actual engine
        res = pipeline.analyze(
            request.image_path, 
            output_dir=str(output_dir),
            roi_mask=roi_mask
        )
        
        # Find visualization files on disk
        viz_path = None
        for name in ["visualization_rgb.png", "debug_binary_combined.png"]:
            candidate = output_dir / name
            if candidate.exists():
                viz_path = str(candidate)
                break
        
        mask_path = str(output_dir / "debug_roi_mask.png") if (output_dir / "debug_roi_mask.png").exists() else None
        
        # Encode images as base64 for Flet Web compatibility
        def path_to_b64(path_str):
            if not path_str:
                return None
            try:
                with open(path_str, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return None
        
        viz_b64 = path_to_b64(viz_path)
        mask_b64_result = path_to_b64(mask_path)
        
        # Map all results to enriched schema
        return MNVResult(
            mnv_area_mm2=res.get("mnv_area_mm2", 0),
            vessel_area_mm2=res.get("vessel_area_mm2", 0),
            vessel_density=res.get("vessel_density", 0),
            vessel_length_mm=res.get("vessel_length_mm", 0),
            mean_diameter_um=res.get("mean_diameter_um", 0),
            tortuosity=res.get("tortuosity", 0),
            fractal_dimension=res.get("fractal_dimension", 0),
            trunk_pattern=res.get("trunk_pattern", "Unknown"),
            # Network metrics
            num_branches=res.get("num_branches", 0),
            num_junctions=res.get("num_junctions", 0),
            num_endpoints=res.get("num_endpoints", 0),
            num_loops=res.get("num_loops", 0),
            # Spatial distribution
            trunk_eccentricity=res.get("trunk_eccentricity", -1.0),
            complexity_score=res.get("complexity_score", 0.0),
            stability_score=res.get("stability_score", 0.0),
            maturity_index=res.get("maturity_index", 0.0),
            mnv_subtype=res.get("mnv_subtype", "Unknown"),
            # Flow deficit
            fd_percent_r1=res.get("FD_percent_R1", 0.0),
            fd_number_r1=res.get("FD_number_R1", 0),
            fd_percent_r2=res.get("FD_percent_R2", 0.0),
            fd_number_r2=res.get("FD_number_R2", 0),
            fd_percent_r3=res.get("FD_percent_R3", 0.0),
            fd_number_r3=res.get("FD_number_R3", 0),
            # Paths
            mask_path=mask_path,
            visualization_path=viz_path,
            # Base64 for Flet Web display
            visualization_base64=viz_b64,
            mask_base64=mask_b64_result,
        )
    except Exception as e:
        import traceback
        error_detail = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": type(e).__name__
        }
        print(f"Engine Error: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)

@app.post("/analyze/vd", response_model=VDResult)
async def analyze_vd(request: VDRequest):
    try:
        # Create unique output directory
        run_id = str(uuid.uuid4())
        output_dir = ROOT / "output" / "vd" / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        analyzer = VDAnalyzer(
            input_dir=Path(request.input_dir),
            output_dir=output_dir,
            scale_mm=request.scale_mm,
            side=request.side,
            sup_suffix=request.sup_suffix,
            deep_suffix=request.deep_suffix,
            single_image_mode=request.single_image_mode
        )
        res = analyzer.analyze()
        
        if not res:
             raise ValueError("No valid file pairs or single images found for VD analysis.")

        return VDResult(
            patient_ids=res.get("patient_ids", []),
            superficial_files=res.get("superficial_files", []),
            deep_files=res.get("deep_files", []),
            faz_areas=res.get("faz_areas", []),
            faz_circularities=res.get("faz_circularities", []),
            superficial_whole=res.get("superficial_whole", []),
            deep_whole=res.get("deep_whole", []),
            fractal_dimension_superficial=res.get("fractal_dimension_superficial", []),
            fractal_dimension_deep=res.get("fractal_dimension_deep", []),
            tortuosity_superficial=res.get("tortuosity_superficial", []),
            tortuosity_deep=res.get("tortuosity_deep", [])
        )
    except Exception as e:
        import traceback
        error_detail = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "type": type(e).__name__
        }
        print(f"VD Engine Error: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)

@app.get("/detect")
async def detect_analysis_type(path: str):
    """
    Smart detection logic:
    - If path is a file and ends with 1.tif/2.tif, suggest VD single mode.
    - If path is a folder, look for pairs, suggest VD batch.
    - Otherwise suggest MNV.
    """
    p = Path(path)
    if not p.exists():
        return {"type": "unknown", "reason": "Path does not exist"}
    
    if p.is_file():
        name = p.name.lower()
        if "1.tif" in name or "2.tif" in name:
            return {"type": "VD", "mode": "single", "suggested_scale": 6.0}
        return {"type": "MNV", "mode": "single", "suggested_scale": 6.0}
    else:
        # Check for VD pairs in folder
        tifs = list(p.glob("*.tif")) + list(p.glob("*.TIF"))
        if any("1.tif" in f.name.lower() for f in tifs) and any("2.tif" in f.name.lower() for f in tifs):
            return {"type": "VD", "mode": "batch", "suggested_scale": 6.0}
        return {"type": "MNV", "mode": "batch", "suggested_scale": 6.0}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    return results_cache.get(job_id, {"status": "not_found"})

@app.get("/ls")
async def list_directory(path: str = None):
    """Lists contents of a directory for the custom file explorer."""
    if not path or path == "":
        path = str(Path.home())
    
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return {"error": "Invalid directory path", "path": path}
    
    try:
        items = []
        # Add parent directory
        if p.parent != p:
            items.append({"name": "..", "path": str(p.parent), "is_dir": True})
            
        for item in sorted(p.iterdir()):
            if item.name.startswith("."): continue
            items.append({
                "name": item.name,
                "path": str(item.absolute()),
                "is_dir": item.is_dir()
            })
        return {"items": items, "current_path": str(p.absolute())}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
