#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

python3 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

cd frontend
npm install
npm run build

echo
echo "Setup complete."
echo "Run: scripts/run_app.sh"

