#!/bin/bash
# Launch blind MNV subtype grading UI (local browser server — not Flet).
# Pass-through args, e.g.:
#   scripts/graefe_revision/run_grade_ui.sh
#   scripts/graefe_revision/run_grade_ui.sh --start-at B017
#
# Opens http://127.0.0.1:8765/?start_at=... when --start-at is given.
cd "$(dirname "$0")/../.." || exit 1

START_AT=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-at)
      START_AT="${2:-}"
      EXTRA+=(--start-at "$START_AT")
      shift 2
      ;;
    --start-at=*)
      START_AT="${1#*=}"
      EXTRA+=(--start-at "$START_AT")
      shift
      ;;
    *)
      EXTRA+=("$1")
      shift
      ;;
  esac
done

# If no --start-at, resolve first ungraded for the browser URL hint (server does the same).
if [[ -z "$START_AT" ]]; then
  START_AT="$(.venv/bin/python -c "
import sys
sys.path.insert(0, 'scripts/graefe_revision')
import interactive_grade as ig
g, _ = ig._load()
n = ig._next_ungraded(g)
print(n['blind_id'] if n is not None else '')
")"
  if [[ -n "$START_AT" ]]; then
    EXTRA+=(--start-at "$START_AT")
  fi
fi

URL="http://127.0.0.1:8765/"
if [[ -n "$START_AT" ]]; then
  URL="http://127.0.0.1:8765/?start_at=${START_AT}"
fi

echo "Starting grade server → ${URL}"
exec .venv/bin/python scripts/graefe_revision/grade_server.py "${EXTRA[@]}"
