#!/usr/bin/env bash
set -e

echo "======================================"
echo "    MiniOS Installer & Auto-Updater   "
echo "======================================"

# 1. Detect Python executable
PYTHON=""
for cmd in python3.11 python3.10 python3.12 python3.9 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[!] Error: Python 3 not found. Please install Python 3.8+."
    exit 1
fi

echo "[+] Using Python: $($PYTHON --version 2>&1) ($PYTHON)"

# 2. Handle directory, install, or update
REPO_URL="https://github.com/codefl0w/MiniOS.git"

if [ ! -f "main.py" ]; then
    if [ -d "MiniOS" ]; then
        echo "[+] Found existing MiniOS directory. Entering..."
        cd MiniOS
    else
        echo "[+] Cloning MiniOS from $REPO_URL..."
        git clone "$REPO_URL" MiniOS
        cd MiniOS
    fi
fi

# If inside a git repository, pull latest updates (force-update without touching databases/.env)
if [ -d ".git" ]; then
    echo "[+] Updating MiniOS source from Git (preserving databases and settings)..."
    git fetch origin main --quiet || true
    git reset --hard origin/main --quiet || true
    echo "[+] Code updated to latest commit."
fi

CURRENT_DIR="$(pwd)"
echo "[+] Working directory: $CURRENT_DIR"

# 3. Create or update virtual environment
VENV_DIR="$CURRENT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[+] Creating virtual environment in .venv..."
    $PYTHON -m venv "$VENV_DIR"
else
    echo "[+] Using virtual environment in .venv."
fi

# Activate virtual environment
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# 4. Install / upgrade dependencies
echo "[+] Installing/updating dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "[+] Dependencies up to date."

# 5. Configure .env if missing
if [ ! -f ".env" ]; then
    echo "[+] Creating .env from .env.example..."
    cp .env.example .env
    SECRET=$(python -c "import secrets; print(secrets.token_hex(24))" 2>/dev/null || openssl rand -hex 24 2>/dev/null || echo "minios_secret_$(date +%s)")
    if [ -n "$SECRET" ]; then
        if sed --version >/dev/null 2>&1; then
            sed -i "s/MINIGRAM_SECRET=change_this_secret/MINIGRAM_SECRET=$SECRET/" .env
        else
            sed -i '' "s/MINIGRAM_SECRET=change_this_secret/MINIGRAM_SECRET=$SECRET/" .env
        fi
    fi
    echo "[+] Generated random MINIGRAM_SECRET in .env"
else
    echo "[+] Existing .env file preserved."
fi

# 6. Automate PythonAnywhere WSGI configuration
IS_PA=false
WSGI_FILES=$(ls /var/www/*_wsgi.py 2>/dev/null || true)

if [ -n "$PYTHONANYWHERE_SITE" ] || [ -n "$PYTHONANYWHERE_DOMAIN" ] || [ -n "$WSGI_FILES" ] || echo "$HOSTNAME" | grep -qi "pythonanywhere"; then
    IS_PA=true
fi

if [ "$IS_PA" = true ] && [ -n "$WSGI_FILES" ]; then
    echo "[+] Detected PythonAnywhere environment."
    for wsgi_file in $WSGI_FILES; do
        echo "[+] Writing automated WSGI configuration to $wsgi_file..."
        cat <<EOF > "$wsgi_file"
import os
import sys

path = '$CURRENT_DIR'
if path not in sys.path:
    sys.path.insert(0, path)

os.chdir(path)

from main import application
EOF
        # Touch WSGI file to trigger uWSGI application reload on PythonAnywhere
        touch "$wsgi_file"
        echo "[+] Reload triggered on $wsgi_file."
    done
fi

echo "======================================"
echo "    MiniOS Ready & Up To Date!        "
echo "======================================"

if [ "$IS_PA" = true ]; then
    PA_USER=$(whoami)
    echo ""
    echo "--- PythonAnywhere Check ---"
    echo "WSGI file automatically configured and reloaded!"
    echo "Make sure your Web tab has:"
    echo "  - Virtualenv: $CURRENT_DIR/.venv"
    echo "  - Source code: $CURRENT_DIR"
    echo ""
else
    echo ""
    echo "To run MiniOS:"
    echo "  source .venv/bin/activate"
    echo "  python main.py"
    echo ""
    echo "URL: http://127.0.0.1:2000/"
    echo ""
fi
