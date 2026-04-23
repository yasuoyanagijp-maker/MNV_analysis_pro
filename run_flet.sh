#!/bin/bash

# ==========================================
# ARIAKE OCTA - Integrated Launch Script (macOS)
# ==========================================

echo "Initializing ARIAKE OCTA..."

# Flet UI mode (must match what main_app.py reads):
#   FLET_USE_WEB=1  (default) — browser, no OS folder dialog for get_directory_path
#   FLET_USE_WEB=0  — native Flet window, OS file/folder pickers
# Examples:  FLET_USE_WEB=0 ./run_flet.sh
: "${FLET_USE_WEB:=1}"
export FLET_USE_WEB
: "${FLET_PORT:=8550}"
export FLET_PORT

# Get the directory of the script and change to it
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# --- PORT CLEANUP FUNCTION ---
cleanup_port() {
    local port=$1
    echo "Checking port $port..."
    local pid=$(lsof -ti :$port)
    if [ ! -z "$pid" ]; then
        echo "Found existing process on port $port (PID: $pid). Cleaning up..."
        kill -9 $pid 2>/dev/null
        sleep 1
    fi
}

# Pre-flight: Clear ports to avoid "Address already in use" errors
cleanup_port 8000
cleanup_port "$FLET_PORT"

# 1. Activate Virtual Environment
if [ -f "./.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source ./.venv/bin/activate
else
    echo "Error: Virtual environment (.venv) not found!"
    echo "Please create it and install requirements first."
    exit 1
fi

# 2. Start FastAPI Backend Engine in the background
echo "Starting Backend Engine (FastAPI)..."
python src/api/main.py > backend.log 2>&1 &
BACKEND_PID=$!

echo "Backend engine started with PID: $BACKEND_PID"

# Wait a moment for the backend API to initialize
sleep 2

# 3. Start Flet Frontend Command Center
echo "Starting Command Center UI (Flet)..."

# Catch termination signals to properly close the backend
trap "echo 'Shutting down...'; kill $BACKEND_PID 2>/dev/null; cleanup_port 8000; cleanup_port $FLET_PORT; exit" INT TERM HUP

# Flet: --web with FLET_USE_WEB=1, or native window when FLET_USE_WEB=0
if [ "$FLET_USE_WEB" = "0" ] || [ "$FLET_USE_WEB" = "false" ] || [ "$FLET_USE_WEB" = "no" ] || [ "$FLET_USE_WEB" = "native" ]; then
    echo "Flet UI: native desktop window (FLET_USE_WEB=$FLET_USE_WEB)"
    flet run --port "$FLET_PORT" main_app.py
else
    echo "Flet UI: web browser (FLET_USE_WEB=$FLET_USE_WEB)"
    flet run --web --port "$FLET_PORT" main_app.py
fi

# 4. Cleanup on exit (if Flet exits normally)
echo "Closing application. Cleaning up background processes..."
kill $BACKEND_PID 2>/dev/null
cleanup_port 8000
cleanup_port "$FLET_PORT"

echo "ARIAKE OCTA session securely terminated."
