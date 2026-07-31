#!/usr/bin/env bash
# Assemble a local release folder for Caliber U2 CSV tool (+ wrappers).
# Does NOT replace the full ARIAKE_OCTA app build — run build_mac.sh / build_win.sh for that.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VER="${1:-1.3.0-caliber-u2}"
OUT="$ROOT/dist/ARIAKE_OCTA_caliber_u2_toolkit_${VER}"
mkdir -p "$OUT"

cp -f "$ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.py" "$OUT/"
cp -f "$ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.bat" "$OUT/"
cp -f "$ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.command" "$OUT/"
cp -f "$ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.sh" "$OUT/"
cp -f "$ROOT/tools/caliber_u2/README.md" "$OUT/README.md"
mkdir -p "$OUT/resources/reference_metrics"
cp -f "$ROOT/resources/reference_metrics/caliber_u2_device_ref.json" "$OUT/resources/reference_metrics/"

if [[ -x "$ROOT/dist/caliber_u2_tool/compute_caliber_u2_from_csv" ]]; then
  cp -f "$ROOT/dist/caliber_u2_tool/compute_caliber_u2_from_csv" "$OUT/"
  chmod +x "$OUT/compute_caliber_u2_from_csv"
fi
chmod +x "$OUT/compute_caliber_u2_from_csv.command" "$OUT/compute_caliber_u2_from_csv.sh" || true

cat > "$OUT/VERSION.txt" <<EOF
ARIAKE OCTA — Caliber Uniformity U2 toolkit
Version: ${VER}
Default Caliber Uniformity Score in app source: U2 (PCA kept as fallback column)
Standalone: compute_caliber_u2_from_csv (+ .bat / .command / .sh)
EOF

echo "Assembled $OUT"
ls -la "$OUT"
