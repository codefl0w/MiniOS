#!/usr/bin/env bash
set -e

echo "======================================"
echo "      MiniOS Installation Script      "
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

# 2. Handle directory (clone if script was run outside repository via curl)
REPO_URL="https://github.com/codefl0w/MiniOS.git"
if [ ! -f "main.py" ]; then
    if [ -d "MiniOS" ]; then
        echo "[+] Entering existing MiniOS directory..."
        cd MiniOS
    else
        echo "[+] Cloning MiniOS repository..."
        git clone "$REPO_URL" MiniOS
        cd MiniOS
    fi
fi

CURRENT_DIR="$(pwd)"
echo "[+] Working directory: $CURRENT_DIR"

# 3. Create virtual environment
VENV_DIR="$CURRENT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[+] Creating virtual environment in .venv..."
    $PYTHON -m venv "$VENV_DIR"
else
    echo "[+] Existing virtual environment found in .venv."
fi

# 4. Activate virtual environment
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# 5. Install dependencies
echo "[+] Installing dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "[+] Dependencies installed successfully."

# 6. Configure .env
if [ ! -f ".env" ]; then
    echo "[+] Creating .env from .env.example..."
    cp .env.example .env
    # Generate secure random secret for session cookies
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
    echo "[+] Existing .env file found. Preserving current configuration."
fi

echo "======================================"
echo "    MiniOS Installed Successfully!    "
echo "======================================"

# 7. Check if running on PythonAnywhere
IS_PA=false
if [ -n "$PYTHONANYWHERE_SITE" ] || [ -n "$PYTHONANYWHERE_DOMAIN" ] || echo "$HOSTNAME" | grep -qi "pythonanywhere"; then
    IS_PA=true
fi

if [ "$IS_PA" = true ]; then
    PA_USER=$(whoami)
    echo ""
    echo "--- PythonAnywhere Setup Instructions ---"
    echo "1. Go to the 'Web' tab in your PythonAnywhere dashboard."
    echo "2. If you haven't created a web app yet, click 'Add a new web app' -> Manual configuration -> Python 3.10 (or 3.11)."
    echo "3. In the 'Virtualenv' section, set path to:"
    echo "     /home/$PA_USER/MiniOS/.venv"
    echo "4. In the 'Code' section, set 'Source code' and 'Working directory' to:"
    echo "     /home/$PA_USER/MiniOS"
    echo "5. Click on the WSGI configuration file link and replace contents with:"
    echo "---------------------------------------------------------"
    echo "import sys"
    echo "path = '/home/$PA_USER/MiniOS'"
    echo "if path not in sys.path:"
    echo "    sys.path.append(path)"
    echo "from main import application"
    echo "---------------------------------------------------------"
    echo "6. Click the green 'Reload <your-username>.pythonanywhere.com' button at the top."
    echo ""
else
    echo ""
    echo "To start MiniOS locally:"
    echo "  source .venv/bin/activate"
    echo "  python main.py"
    echo ""
    echo "MiniOS will run at: http://127.0.0.1:2000/"
    echo ""
fi
