#!/usr/bin/env bash
# =========================================================================
#  Enterprise Face Recognition Attendance System (FRAS) — Linux/macOS Runner
# =========================================================================

set -e

echo "========================================================================="
echo "  Enterprise Face Recognition Attendance System (FRAS)"
echo "========================================================================="
echo ""

# Check python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed!"
    exit 1
fi

# Install dependencies
echo "[*] Checking dependencies..."
pip install -r requirements.txt --quiet

# Launch Uvicorn
echo "[*] Starting FRAS Enterprise on http://127.0.0.1:8000 ..."
python3 main.py
