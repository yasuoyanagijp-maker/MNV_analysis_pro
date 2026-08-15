#!/bin/bash

# ==========================================
# ARIAKE OCTA — distribution-parity launcher
# ==========================================
# Same entry as the packaged Mac app: wrapper.py
#   - ephemeral free ports for API + Flet (no fixed 8000/8550, no kill -9)
#   - native desktop window by default (FLET_USE_WEB=0), like ARIAKE_OCTA.app
#
# Examples:
#   ./run_flet.sh
#   FLET_USE_WEB=1 ./run_flet.sh          # browser UI (dev)
#   ARIAKE_API_PORT=8000 FLET_PORT=8550 ./run_flet.sh   # force ports (debug)

echo "Initializing ARIAKE OCTA (wrapper.py — same path as packaged app)..."

# Packaged default is native. Override with FLET_USE_WEB=1 for browser.
: "${FLET_USE_WEB:=0}"
export FLET_USE_WEB

: "${FLET_SERVER_IP:=127.0.0.1}"
export FLET_SERVER_IP

# Match packaged app: ephemeral ports unless caller opts in to keep env ports.
# Debug fixed ports: ARIAKE_KEEP_PORTS=1 ARIAKE_API_PORT=8000 FLET_PORT=8550 ./run_flet.sh
if [ "${ARIAKE_KEEP_PORTS:-0}" != "1" ]; then
    unset ARIAKE_API_PORT FLET_PORT
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

export PYTHONPATH=".:src"
export PYTHONUNBUFFERED=1

if [ -f "./.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source ./.venv/bin/activate
    PYTHON_BIN="${DIR}/.venv/bin/python"
else
    echo "Error: Virtual environment (.venv) not found!"
    echo "Please create it and install requirements first."
    exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
    echo "Error: $PYTHON_BIN not executable"
    exit 1
fi

# Stop leftover *this-repo* API/Flet only (never kill Cursor wholesale).
# Wrapper still picks ephemeral ports, so this is best-effort cleanup.
pkill -f "${DIR}/.venv/bin/python.*main_app.py" 2>/dev/null || true
pkill -f "${DIR}/.venv/bin/python.*src/api/main.py" 2>/dev/null || true
pkill -f "${DIR}/.venv/bin/python.*wrapper.py" 2>/dev/null || true
sleep 1

echo "Launching via wrapper.py (FLET_USE_WEB=$FLET_USE_WEB)..."
exec "$PYTHON_BIN" wrapper.py
