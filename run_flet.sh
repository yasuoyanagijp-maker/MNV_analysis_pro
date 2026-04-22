#!/bin/bash

# ==========================================
# ARIAKE OCTA - Integrated Launch Script (macOS)
# ==========================================

echo "Initializing ARIAKE OCTA..."

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
cleanup_port 8550

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
trap "echo 'Shutting down...'; kill $BACKEND_PID 2>/dev/null; cleanup_port 8000; cleanup_port 8550; exit" INT TERM HUP

# Run Flet application (Web mode for better stability on Mac filesystem)
# Using --web mode to avoid common socket issues with native windows on some macOS versions
flet run --web --port 8550 main_app.py > flet_latest.log 2>&1

# 4. Cleanup on exit (if Flet exits normally)
echo "Closing application. Cleaning up background processes..."
kill $BACKEND_PID 2>/dev/null
cleanup_port 8000
cleanup_port 8550

echo "ARIAKE OCTA session securely terminated."
