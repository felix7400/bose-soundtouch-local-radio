#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

if [ ! -d .venv ]; then
  echo "Missing .venv. Run scripts/setup.sh first."
  exit 1
fi

# shellcheck source=/dev/null
source .venv/bin/activate

uvicorn app.main:app --app-dir backend --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8000}" &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd frontend
exec npm run dev

