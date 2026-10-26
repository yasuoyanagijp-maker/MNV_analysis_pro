# PDR NVE / NVD analysis (wide-field OCTA)

Standalone module for **neovascularization elsewhere / at the disc (NVE/NVD)** on **15 × 15 mm** OCTA en-face pairs (before vs after anti-VEGF). It reuses ARIAKE vessel segmentation, skeleton / Euler / fractal / caliber code and the existing ROI 余白trim, but it is **not** the MNV app:

- **Raw metrics only.** No 0–100 standardized scores, no maturity index, no MNV reference distributions (those are 3 × 3 / 6 × 6 mm MNV populations and do not apply here).
- **Does not change** MNV/VD pipelines, Flet routes, or release assets.
- Pixel size is an **input** (default 15 mm / image width ≈ 14.65 µm/px at 1024 px) and is written into every CSV.

## Requirements

Same pinned stack as the repo (`requirements.txt`, Python 3.9–3.12). No new dependencies.

```bash
export PYTHONPATH=".:src"
```

## CLI

```bash
python -m ariake_octa.pdr_nve \
  --before path/to/ILM+49_before.png \
  --after  path/to/ILM+49_after.png \
  --register-before path/to/VRI+Retina_Global_before.png \
  --register-after  path/to/VRI+Retina_Global_after.png \
  --output out/case1 \
  --case-id case1 \
  --scan-size-mm 15 \
  --pixel-width 1024
```

Or mean/sum every slab (same idea as stack_reg Image 5):

```bash
python -m ariake_octa.pdr_nve \
  --before ilm49_before.png --after ilm49_after.png \
  --register-before vri_before.png --register-before retina_before.png --register-before global_before.png \
  --register-after  vri_after.png  --register-after  retina_after.png  --register-after  global_after.png \
  --register-combine mean \
  --output out/case1 --case-id case1 --scan-size-mm 15
```

Convenience wrapper (sets `sys.path`):

```bash
python tools/pdr_nve/run_pdr_nve.py --before ... --after ... --output ... --case-id case1
```

### Important options

| Option | Meaning |
|--------|---------|
| `--scan-size-mm` / `--pixel-width` / `--um-per-px` | Physical scale. Recorded in the CSV. |
| `--roi-mask` / `--roi-polygon` | Shared freeform ROI in **before** pixels (after is registered first). |
| `--roi-mode auto\|full` | If no mask/polygon: density-based lesion contour, or whole frame. |
| `--no-register` | Pair already aligned. |
| `--register-before` / `--register-after` | **Registration-only slabs** (repeatable). Do **not** align on the ILM+49 analysis slab after treatment — NVE vanishes. Prefer Retina, device **VRI+Retina Global**, or every exported slab. Combined with `--register-combine` (default `mean` = stack_reg Image 5 / ImageJ Z-project average; `sum` is a rescaled total). The estimated transform is then applied to the analysis pair. |
| `--large-vessel-um` | Diameter gate for trunk vessels (default 100 µm). |
| `--exclude-disc` | Optional compact disc punch-out. |
| `--segment-mode mnv\|adaptive` | MNV preprocessor (default) or CLAHE+Li fallback. |
| `--no-trim-border` / `--no-trim-roi` | Disable export-border crop / 余白trim. |

Standalone Flet UI (optional, **not** wired into the MNV dashboard):

```bash
PYTHONPATH=.:src python -m ariake_octa.pdr_nve.ui
```

## Outputs (per case)

All names start with `{case_id}_` so they can be opened without a sidecar.

| File | Contents |
|------|----------|
| `{id}_metrics.csv` | One row: scale, registration, quality flags, `before_*` / `after_*` / `pct_*` raw metrics. |
| `{id}_params.json` | Run config and output file list. |
| `{id}_overlay_qa.png` | Montage: raw+ROI, registration checker, ARIAKE RGB, masks. |
| `{id}_before_rgb.png` / `{id}_after_rgb.png` | Same subtractive RGB as the MNV app (yellow = vessels, red = large-caliber, gray = background), with a scale bar. `after_*` is in the **registered** before frame. |
| `{id}_{before\|after}_vessel_mask.png` | Binary vessel mask used for that frame. |
| `{id}_{before\|after}_roi_mask.png` | Shared ROI (identical pair; after is registered). |
| `{id}_shared_roi_mask.png` | Same ROI, single copy. |
| `{id}_{before\|after}_vessel_mask_no_large.png` | Vessels after large-caliber exclusion. |
| `{id}_{before\|after}_large_vessel_mask.png` | Large-caliber / trunk mask. |
| `{id}_register_ref_before.png` / `_after.png` / `_after_warped.png` | Combined registration slabs (only if `--register-before/after` were given). |

### Metrics (raw)

Vessel area density, skeleton length density, branch-point (junction) density, loop count / Euler number, box-counting fractal dimension, gliding-box lacunarity, mean and CV of vessel caliber **with and without** large vessels, plus ImageJ-style distance-map diameter as extra ingredients. Percent change is `(after − before) / before × 100`.

Quality flags (SNR, contrast, registration CC, empty vessels, full-field ROI, …) and `exclude_suggested` are recorded; they are sanity checks, not a clinical exclusion protocol.

## How existing code is reused

- Vessel binary: `core.vessel_detection.MNVPreprocessor` + large-image filter params.
- Skeleton / Euler / fractal / ImageJ diameter: `core.skeleton_analysis`.
- RGB: `ariake_octa.mnv.visualization_rgb.VisualizationRGB` (large-caliber map in the high-skew / red channel).
- ROI 余白trim: method-B-prime rule (drop only uncolored padding that touches the ROI exterior).
- Registration idea: `yasuoyanagijp-maker/stack_reg` (CLAHE, pyramid ECC affine, ORB+RANSAC refine, `WARP_INVERSE_MAP`, **Image 5 = average of the stack**). That repo is **not** imported or modified. Estimate the transform on a persistent slab (Retina / VRI+Retina Global / mean of all slabs) and warp the analysis slab. Phase-correlation seeds translation because same-size `matchTemplate` is a no-op for unregistered visit pairs. If no register slabs are given, the tool falls back to the analysis pair and flags `registration_on_analysis_slab`.

## Tests

```bash
PYTHONPATH=.:src python -m unittest tools.pdr_nve.test_pdr_nve
```

## What this is not

Two sample ILM+49 slabs only; **no clinical validation**. Images are display-rendered exports without embedded scale. Default VRI slabs often miss flat NVE; ILM−241 to ILM+49 showed the network in the samples but also retinal trunks / RPC — hence the large-vessel filter and freeform ROI. Treat slab choice as an observation, not a protocol.
