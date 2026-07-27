#!/bin/bash
# Launch discordance regrade UI (local browser server on port 8766).
# Pass-through args, e.g.:
#   scripts/graefe_revision/run_regrade_ui.sh
#   scripts/graefe_revision/run_regrade_ui.sh --start-at B020
#
# Queue: documentation/graefe_revision/grading/regrade_queue.csv
# After finishing: .venv/bin/python scripts/graefe_revision/compute_agreement.py
cd "$(dirname "$0")/../.." || exit 1

EXTRA=()
START_AT=""
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

URL="http://127.0.0.1:8766/"
if [[ -n "$START_AT" ]]; then
  URL="http://127.0.0.1:8766/?start_at=${START_AT}"
fi

echo "Starting regrade server → ${URL}"
echo "Queue: documentation/graefe_revision/grading/regrade_queue.csv"
echo "After regrade: .venv/bin/python scripts/graefe_revision/compute_agreement.py"
exec .venv/bin/python scripts/graefe_revision/regrade_server.py --port 8766 "${EXTRA[@]}"
