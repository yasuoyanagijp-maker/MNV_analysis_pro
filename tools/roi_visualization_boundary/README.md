# ROI visualization-boundary pilots (Method A–F)

Offline dual-read experiments around ColorMask (RGB-viz difference) and
hand-drawn ROI. **Most of this tree is pilot-only.** The production app
does not run Method D outward snap, Method E nudge, Method F, fill-holes,
or Method C enclosure.

## Production vs pilot

| What | Where | In the app? |
|---|---|---|
| **A** — hand-drawn ROI (current analysis mask) | Flet ROI page → `MNVPipeline.analyze` | **Yes** (default) |
| ColorMask extract (locked Method B formula) | `src/ariake_octa/mnv/color_mask.py` | **Yes** (shared helper) |
| 着色画像 / 余白trim (ColorMask ∩ ROI), opt-in preview | `src/flet_ui/pages/roi_selection.py` | **Yes** (Accept required; Undo) |
| Vsl Density as percent (not aVDI) | `results_screen.py`, `report_generator.py`, `shared.py`, `visualization_rgb.py` | **Yes** |
| `intelligent_roi` (auto-ROI contour refine) | unchanged | **Yes** (auto-ROI only; hand ROI still skips) |
| **B** — ColorMask *as* the analysis ROI | `method_b/` | No |
| **B′** — keep enclosed padding holes | `method_b/prime/` | No |
| **C** — ColorMask enclosure as ROI | recorded in Method B notes | **Rejected** |
| **D** — μm outward snap (Pass-2 seed dilate) | `method_d/` | No |
| **D fill/close** — holes + morph close on inward | `method_d_fill_holes/` | No |
| **E** — contour nudge onto ColorMask | `method_e/` | No |
| **F** — asymmetric hybrid (D inward + E outward) | `method_f/` | No |

Import the locked extract from the production module, not from these pilots:

```python
from ariake_octa.mnv.color_mask import extract_color_mask
```

## Layout

```
tools/roi_visualization_boundary/
  README.md                 # this index
  lib/                      # shared case paths + I/O for the pilots
  method_b/                 # ColorMask-as-ROI + adoption / B′
  method_d/                 # μm outward snap
  method_e/                 # contour nudge
  method_f/                 # asymmetric hybrid
  method_d_fill_holes/      # fill / close density test
```

Each method folder has a README with the definition, n=3 CIRRUS 3 mm
results, and how to re-run. Shared helpers live in `lib/` so D/E/F do
not import the Method B runner.

## QA images (local only)

Scripts write overlays under `qa/` or `method_b/qa_masks/` (~800 PNGs).
Those folders are gitignored: they can contain full-res, patient-adjacent
filenames. Re-run the script if you need them. CSV summaries in each
method folder are enough to review RPD.

Adoption dumps that still carry original export filenames
(`method_b/adoption/MNV_batch_methodB_*.csv`, `*_adopted_values.csv`,
`comparison.json`, `method_b/prime/method_b_prime_comparison.json`)
also stay local.

## Run (needs local Desktop dual-read exports)

```bash
.venv/bin/python tools/roi_visualization_boundary/method_b/method_b_visualization_boundary.py
.venv/bin/python tools/roi_visualization_boundary/method_d/method_d_colormask_snap.py
.venv/bin/python tools/roi_visualization_boundary/method_e/method_e_contour_snap.py
.venv/bin/python tools/roi_visualization_boundary/method_f/method_f_asymmetric_snap.py
.venv/bin/python tools/roi_visualization_boundary/method_d_fill_holes/compute_method_d_fill_holes.py
```
