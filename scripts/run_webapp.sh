#!/usr/bin/env bash
#
# Launch the local prediction web app (webapp/server.py) on http://localhost:8026
#
#   scripts/run_webapp.sh [--port N]
#
# Needs the `web` extra: uv sync --extra web   (or pip install -e '.[web]')

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PORT=8026
[ "${1:-}" = "--port" ] && PORT="$2"

if command -v uv >/dev/null 2>&1; then
  exec uv run uvicorn webapp.server:app --port "$PORT"
else
  exec python3 -m uvicorn webapp.server:app --port "$PORT"
fi
