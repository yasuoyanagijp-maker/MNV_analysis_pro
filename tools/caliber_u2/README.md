# Caliber Uniformity U2 — packaging notes for release kits

## What changed
- **Default** `Caliber Uniformity Score` = U2 (device-locked NV Diameter CV + Dilated %)
- **Fallback** `Caliber Uniformity Score (PCA)` = previous Stability/PCA score
- **Maturity Index** = `50 + (U2 − Complexity) / 2` (uses U2, not PCA)
- **Maturity Index (PCA)** = same formula with PCA Caliber

Reference JSON: `resources/reference_metrics/caliber_u2_device_ref.json`

## Standalone CSV tool (no GUI)
```bash
# macOS / Linux
./tools/caliber_u2/compute_caliber_u2_from_csv.sh INPUT.csv
./tools/caliber_u2/compute_caliber_u2_from_csv.command INPUT.csv   # Finder double-click OK after chmod +x

# Windows
tools\caliber_u2\compute_caliber_u2_from_csv.bat INPUT.csv
```

Inserts `Caliber Uniformity Score (U2)` and `Maturity Index (U2)` to the right of existing columns.

## Release kit checklist
1. Include `resources/reference_metrics/caliber_u2_device_ref.json` (bundled via existing PyInstaller `resources/` datas).
2. Copy `scripts/distribution/compute_caliber_u2_from_csv.{bat,command,sh}` into the release folder (alongside README).
3. Copy `scripts/compute_caliber_u2_from_csv.py` (or ship a frozen one-file EXE later).
4. Rebuild app: `./build_mac.sh --build-only` / `./build_win.sh` as usual.

## Tests
```bash
python tools/caliber_u2/test_caliber_u2.py -v
```
