#!/bin/bash
# =============================================================================
# compute_caliber_u2_from_csv.command — macOS double-click / Terminal helper
# =============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $(basename "$0") INPUT.csv [-o OUTPUT.csv] [--inplace] [--size-class small|large|small_3mm]"
  echo
  echo "Example:"
  echo "  $(basename "$0") MNV_batch.csv"
  echo "  $(basename "$0") MNV_batch.csv -o MNV_batch_u2.csv"
  read -r -p "Press Enter to close..."
  exit 1
fi

PY=""
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "Python 3 not found."
  read -r -p "Press Enter to close..."
  exit 1
fi

"$PY" "$REPO_ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.py" "$@"
EC=$?
if [[ $EC -ne 0 ]]; then
  echo "ERROR: exit code $EC"
  read -r -p "Press Enter to close..."
fi
exit $EC
