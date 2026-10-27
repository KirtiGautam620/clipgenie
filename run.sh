#!/bin/bash
# Starts ClipGenie: the backend (port 8000) and the web page (port 5173). Stop with Ctrl+C.
set -e
cd "$(dirname "$0")"

# --- one-time setup (skipped when already done) ---
if [ ! -d backend/.venv ]; then
  echo "First run: creating the Python environment (this takes a few minutes)..."
  uv venv --python 3.12 backend/.venv
  uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "First run: installing the web page packages..."
  (cd frontend && npm install)
fi
if [ ! -f data/music/library.json ]; then
  echo "Creating the starter music tracks..."
  (cd backend && .venv/bin/python tools/make_starter_music.py)
fi

# --- the local AI (optional: without it, clips are chosen by a basic method) ---
if ! curl -s localhost:11434/api/version > /dev/null; then
  if command -v ollama > /dev/null; then
    echo "Starting Ollama..."
    ollama serve > /dev/null 2>&1 &
    sleep 3
  else
    echo "Ollama is not installed. ClipGenie will still work, with basic clip choosing."
  fi
fi
if command -v ollama > /dev/null && ! ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
  echo "Tip: run 'ollama pull qwen2.5:3b' once to enable the AI highlight finder (about 2 GB)."
fi

# --- run both servers, and stop both on Ctrl+C ---
(cd backend && exec .venv/bin/uvicorn app.main:app --port 8000) &
BACKEND=$!
(cd frontend && exec npm run dev) &
FRONTEND=$!
trap 'kill $BACKEND $FRONTEND 2>/dev/null' EXIT INT TERM

echo
echo "ClipGenie is starting. Open  http://localhost:5173  in your browser."
wait
