# Requires -Version 5.1
$ErrorActionPreference = "Stop"

Write-Host "======================================"
Write-Host "    MiniOS Installer & Auto-Updater   "
Write-Host "======================================"

# 1. Detect Python executable
$PYTHON = ""
$candidates = @("py", "python3", "python")
foreach ($cmd in $candidates) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $PYTHON = $cmd
        break
    }
}

if (-not $PYTHON) {
    Write-Host "[!] Error: Python not found. Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Red
    exit 1
}

$pyVersion = & $PYTHON --version 2>&1
Write-Host "[+] Using Python: $pyVersion ($PYTHON)"

# 2. Handle directory, install, or update
$REPO_URL = "https://github.com/codefl0w/MiniOS.git"

if (-not (Test-Path "main.py")) {
    if (Test-Path "MiniOS\main.py") {
        Write-Host "[+] Found existing MiniOS directory. Entering..."
        Set-Location "MiniOS"
    } else {
        Write-Host "[+] Cloning MiniOS from $REPO_URL..."
        git clone $REPO_URL MiniOS
        Set-Location "MiniOS"
    }
}

# If inside a git repository, pull latest updates (preserving databases and uncommitted files)
if (Test-Path ".git") {
    $dirty = & git status --porcelain
    if (-not $dirty) {
        Write-Host "[+] Updating MiniOS source from Git (preserving databases and settings)..."
        try {
            git fetch origin main --quiet
            git reset --hard origin/main --quiet
            Write-Host "[+] Code updated to latest commit."
        } catch {
            Write-Host "[!] Git update skipped: $_"
        }
    }
}

$CURRENT_DIR = (Get-Location).Path
Write-Host "[+] Working directory: $CURRENT_DIR"

# 3. Create or update virtual environment
$VENV_DIR = Join-Path $CURRENT_DIR ".venv"
if (-not (Test-Path $VENV_DIR)) {
    Write-Host "[+] Creating virtual environment in .venv..."
    & $PYTHON -m venv $VENV_DIR
} else {
    Write-Host "[+] Using virtual environment in .venv."
}

# 4. Activate virtual environment
$ACTIVATE_SCRIPT = Join-Path $VENV_DIR "Scripts\Activate.ps1"
if (Test-Path $ACTIVATE_SCRIPT) {
    try {
        & $ACTIVATE_SCRIPT
    } catch {
        $env:VIRTUAL_ENV = $VENV_DIR
        $env:PATH = "$(Join-Path $VENV_DIR 'Scripts');$env:PATH"
    }
} else {
    $env:VIRTUAL_ENV = $VENV_DIR
    $env:PATH = "$(Join-Path $VENV_DIR 'Scripts');$env:PATH"
}

# 5. Install / upgrade dependencies
Write-Host "[+] Installing/updating dependencies from requirements.txt..."
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
Write-Host "[+] Dependencies up to date."

# 6. Configure .env if missing
$ENV_FILE = Join-Path $CURRENT_DIR ".env"
$ENV_EXAMPLE = Join-Path $CURRENT_DIR ".env.example"

if (-not (Test-Path $ENV_FILE)) {
    Write-Host "[+] Creating .env from .env.example..."
    Copy-Item $ENV_EXAMPLE $ENV_FILE

    try {
        $secret = python -c "import secrets; print(secrets.token_hex(24))"
    } catch {
        $secret = [System.Guid]::NewGuid().ToString("N")
    }

    if ($secret) {
        $content = Get-Content $ENV_FILE -Raw
        $content = $content -replace "MINIGRAM_SECRET=change_this_secret", "MINIGRAM_SECRET=$secret"
        Set-Content -Path $ENV_FILE -Value $content -NoNewline
    }
    Write-Host "[+] Generated random MINIGRAM_SECRET in .env"
} else {
    Write-Host "[+] Existing .env file preserved."
}

Write-Host "======================================"
Write-Host "    MiniOS Ready & Up To Date!        "
Write-Host "======================================"
Write-Host ""
Write-Host "To run MiniOS:"
Write-Host "  .\.venv\Scripts\activate"
Write-Host "  python main.py"
Write-Host ""
Write-Host "URL: http://127.0.0.1:2000/"
Write-Host ""
