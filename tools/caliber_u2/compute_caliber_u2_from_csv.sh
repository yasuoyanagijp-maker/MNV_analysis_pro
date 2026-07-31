#!/usr/bin/env bash
# =============================================================================
# compute_caliber_u2_from_csv.sh — Unix/mac CLI wrapper (release kit)
# =============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $(basename "$0") INPUT.csv [-o OUTPUT.csv] [--inplace] [--size-class small|large|small_3mm]" >&2
  exit 1
fi

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi

exec "$PY" "$REPO_ROOT/tools/caliber_u2/compute_caliber_u2_from_csv.py" "$@"
