#!/bin/bash

# ==========================================
# ARIAKE OCTA - Integrated Launch Script (macOS)
# ==========================================

echo "Initializing ARIAKE OCTA..."

# Get the directory of the script and change to it
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

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
python src/api/main.py &
BACKEND_PID=$!

echo "Backend engine started with PID: $BACKEND_PID"

# Wait a moment for the backend API to initialize
sleep 2

# 3. Start Flet Frontend Command Center
echo "Starting Command Center UI (Flet)..."

# Catch termination signals to properly close the backend
trap "echo 'Shutting down...'; kill $BACKEND_PID; exit" INT TERM HUP

# Run Flet application (Web mode for better stability on Mac filesystem)
# If you prefer desktop mode, remove '--web'
flet run --web main_app.py

# 4. Cleanup on exit
echo "Closing application. Cleaning up background processes..."
kill $BACKEND_PID 2>/dev/null
wait $BACKEND_PID 2>/dev/null

echo "ARIAKE OCTA session securely terminated."
