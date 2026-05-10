#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  echo "Missing .venv. Run scripts/setup.sh first."
  exit 1
fi

# shellcheck source=/dev/null
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests

