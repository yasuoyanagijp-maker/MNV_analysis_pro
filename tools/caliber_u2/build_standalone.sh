#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
cd "$ROOT"
"$PY" -m pip install -q pyinstaller numpy
"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$ROOT/dist/caliber_u2_tool" \
  --workpath "$ROOT/build/caliber_u2_tool" \
  "$ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.spec"
echo "Binary: $ROOT/dist/caliber_u2_tool/compute_caliber_u2_from_csv"
file "$ROOT/dist/caliber_u2_tool/compute_caliber_u2_from_csv"
