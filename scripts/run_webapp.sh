#!/usr/bin/env bash
#
# Launch the local prediction web app (webapp/server.py) on http://localhost:8026
#
#   scripts/run_webapp.sh [--port N] [--lan | --tailscale] [--s3]
#
#   --lan        listen on 0.0.0.0 (reachable from the local Wi-Fi, e.g. a phone)
#   --tailscale  bind only to the Mac's Tailscale IP (reachable from your tailnet
#                anywhere, invisible to the LAN and the public internet)
#   --s3         pull data/ from the wcpred-data S3 bucket on startup (needs the
#                'wcpred' AWS profile); re-sync later with POST /api/pull
#
# Needs the `web` extra: uv sync --extra web   (or pip install -e '.[web]')

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

tailscale_bin() {
  if command -v tailscale >/dev/null 2>&1; then
    echo tailscale
  elif [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
    # macOS App Store install does not put the CLI on PATH
    echo /Applications/Tailscale.app/Contents/MacOS/Tailscale
  else
    echo "error: tailscale CLI not found (is Tailscale installed and running?)" >&2
    return 1
  fi
}

PORT=8026
HOST=127.0.0.1

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --lan) HOST=0.0.0.0; shift ;;
    --s3) export WCPRED_SYNC_S3=1; shift ;;
    --tailscale)
      TS="$(tailscale_bin)"
      HOST="$("$TS" ip -4)" || { echo "error: could not get Tailscale IP (logged in?)" >&2; exit 1; }
      shift ;;
    *) echo "usage: scripts/run_webapp.sh [--port N] [--lan | --tailscale] [--s3]" >&2; exit 1 ;;
  esac
done

echo "Serving on http://$HOST:$PORT"

# Prefer a project-local .venv (created with a supported Python, >=3.9) so the
# launcher doesn't fall back to whatever interpreter happens to be on PATH.
if [ -x .venv/bin/uvicorn ]; then
  exec .venv/bin/python -m uvicorn webapp.server:app --host "$HOST" --port "$PORT"
elif command -v uv >/dev/null 2>&1; then
  exec uv run uvicorn webapp.server:app --host "$HOST" --port "$PORT"
else
  exec python3 -m uvicorn webapp.server:app --host "$HOST" --port "$PORT"
fi
