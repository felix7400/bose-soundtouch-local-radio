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

if [ ! -f frontend/dist/index.html ]; then
  echo "Frontend build is missing. Run scripts/setup.sh or scripts/build_frontend.sh first."
  exit 1
fi

# shellcheck source=/dev/null
source .venv/bin/activate

ALIAS_PID=""
cleanup() {
  if [ -n "$ALIAS_PID" ]; then
    kill "$ALIAS_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [ -n "${APP_ALIAS_HOST:-}" ] && command -v avahi-publish-address >/dev/null 2>&1; then
  LOCAL_IPV4="$(hostname -I | awk '{print $1}')"
  if [ -n "$LOCAL_IPV4" ]; then
    avahi-publish-address --no-reverse "$APP_ALIAS_HOST" "$LOCAL_IPV4" >/tmp/soundtouch-local-avahi.log 2>&1 &
    ALIAS_PID=$!
  fi
fi

uvicorn app.main:app --app-dir backend --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8000}"
