#!/bin/zsh
set -e
cd "$(dirname "$0")"

PORT=8765

# --- 1. Homebrew (needed to install Python/Node/ffmpeg if they're missing) ---
if ! command -v brew >/dev/null 2>&1; then
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  else
    echo "Homebrew not found — installing it now (this may ask for your Mac password, and can take a few minutes)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
      eval "$(/usr/local/bin/brew shellenv)"
    else
      echo "ERROR: Homebrew installation did not complete. Please install it manually from https://brew.sh and re-run this file."
      exit 1
    fi
  fi
fi

# --- 2. Python 3 ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python..."
  brew install python3
fi
PYTHON=$(command -v python3)

# --- 3. Node.js / npm ---
if ! command -v npm >/dev/null 2>&1; then
  echo "Installing Node.js..."
  brew install node
fi

# --- 4. ffmpeg (needed by yt-dlp to merge some video+audio streams) ---
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Installing ffmpeg..."
  brew install ffmpeg
fi

# --- 5. Python virtualenv + backend dependencies ---
VENV=backend/venv
[ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"
source "$VENV/bin/activate"

REQ_HASH_FILE="$VENV/.requirements.sha256"
CURRENT_HASH=$(shasum -a 256 backend/requirements.txt | awk '{print $1}')
if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat "$REQ_HASH_FILE" 2>/dev/null)" != "$CURRENT_HASH" ]; then
  echo "Installing backend dependencies (fastapi, yt-dlp, gallery-dl, ...)..."
  pip install -q --upgrade pip
  pip install -q -r backend/requirements.txt
  echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
fi

# --- 6. Frontend build (only if missing or source changed) ---
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src -newer frontend/dist/index.html 2>/dev/null)" ]; then
  echo "Building frontend..."
  (cd frontend && npm install && npm run build)
fi

# --- 7. Run ---
echo "Starting server on http://localhost:$PORT ..."
( sleep 1 && open "http://localhost:$PORT" ) &
exec "$VENV/bin/uvicorn" app.main:app --app-dir backend --host 127.0.0.1 --port $PORT
