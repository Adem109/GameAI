#!/bin/bash
# Double-click to play Cozy Roads (first run installs pygame-ce, ~1 minute).
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First launch: setting up (one time only)..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "Setup failed"; read -r; exit 1; }
fi
.venv/bin/python run_game.py
