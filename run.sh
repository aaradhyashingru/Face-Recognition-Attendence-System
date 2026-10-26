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

# Initialize .env from .env.example if missing
if [ ! -f .env ] && [ -f .env.example ]; then
    echo "[*] Initializing .env configuration from .env.example..."
    cp .env.example .env
fi

# Install dependencies
echo "[*] Checking dependencies..."
pip install -r requirements.txt --quiet

# Launch Uvicorn
echo "[*] Starting FRAS Enterprise Server..."
echo "[*] Admin management CLI available via: python3 manage_admin.py"
python3 main.py
