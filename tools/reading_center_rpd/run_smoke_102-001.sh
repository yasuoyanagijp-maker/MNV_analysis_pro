#!/usr/bin/env bash
# Smoke-run on Micron training dual-read pair (102-001).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
DATA="$ROOT/documentation/micron_training_20260727"
OUT="$DATA/rc_tool_smoke_102-001"

"$PY" "$ROOT/tools/reading_center_rpd/compute_adopted_from_dual_csv.py" \
  --site-csv "$DATA/mnv_batch_20260726_145327_3c94f5.csv" \
  --reader2-csv "$DATA/mnv_batch_20260731_162922_e4fae1.csv" \
  --out-dir "$OUT" \
  --prefix 102-001 \
  --rpd-threshold 20 \
  --size-class small_3mm \
  --site-label Inoda \
  --reader2-label Inoue \
  --keep-u2-csv

echo "OK: $OUT"
