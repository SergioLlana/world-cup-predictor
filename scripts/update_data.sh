#!/usr/bin/env bash
#
# Incrementally refresh every wcpred data source into data/input/.
#
#   results.csv   — full re-download of the martj42 dataset (the canonical
#                   update; there is no incremental API, but the file is small)
#   xg.csv        — FotMob xG, incremental via the .done checkpoint; the last
#                   --xg-window days are re-fetched so matches that finished
#                   after the previous run get picked up
#   odds.csv      — The Odds API, upserted with --merge (needs ODDS_API_KEY;
#                   skipped with a notice if the key is absent)
#
# Each source is independent: a failure in one is reported but does not stop the
# others, and the script exits non-zero if any source failed.
#
# Usage:
#   scripts/update_data.sh [options]
#
# Options:
#   --xg-window N    trailing days of xG to re-fetch (default: 14)
#   --full-xg        rebuild xg.csv from scratch (ignore the .done checkpoint)
#   --skip-results   don't refresh results.csv
#   --skip-xg        don't refresh xg.csv
#   --skip-odds      don't refresh odds.csv
#   -h, --help       show this help and exit
#
# Env vars: PYTHON (default: python3), XG_WINDOW_DAYS, ODDS_API_KEY.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
INPUT_DIR="data/input"
XG_CSV="$INPUT_DIR/xg.csv"
XG_DONE="$XG_CSV.done"
ODDS_CSV="$INPUT_DIR/odds.csv"

XG_WINDOW_DAYS="${XG_WINDOW_DAYS:-14}"
FULL_XG=0
SKIP_RESULTS=0
SKIP_XG=0
SKIP_ODDS=0

usage() {
  cat <<'EOF'
Incrementally refresh every wcpred data source into data/input/.

Usage: scripts/update_data.sh [options]

Options:
  --xg-window N    trailing days of xG to re-fetch (default: 14)
  --full-xg        rebuild xg.csv from scratch (ignore the .done checkpoint)
  --skip-results   don't refresh results.csv
  --skip-xg        don't refresh xg.csv
  --skip-odds      don't refresh odds.csv
  -h, --help       show this help and exit

Env vars: PYTHON (default: python3), XG_WINDOW_DAYS, ODDS_API_KEY.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --xg-window)   XG_WINDOW_DAYS="$2"; shift 2 ;;
    --full-xg)     FULL_XG=1; shift ;;
    --skip-results) SKIP_RESULTS=1; shift ;;
    --skip-xg)     SKIP_XG=1; shift ;;
    --skip-odds)   SKIP_ODDS=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

mkdir -p "$INPUT_DIR"
FAILED=()
log() { printf '\n=== %s ===\n' "$*"; }
reldate() { "$PY" -c "from datetime import date,timedelta;print((date.today()-timedelta(days=$1)).strftime('$2'))"; }

wcpred_cli() { "$PY" -m wcpred.cli "$@"; }

# --- 1) Results: full refresh of the martj42 dataset -------------------------
if [ "$SKIP_RESULTS" = 0 ]; then
  log "Results — wcpred update-data"
  if ! wcpred_cli update-data; then FAILED+=("results"); fi
fi

# --- 2) xG: incremental backfill from FotMob ---------------------------------
if [ "$SKIP_XG" = 0 ]; then
  if [ "$FULL_XG" = 1 ]; then
    log "xG — full rebuild (--restart)"
    if ! "$PY" scripts/fetch_xg.py --restart --out "$XG_CSV"; then FAILED+=("xg"); fi
  elif [ -f "$XG_DONE" ]; then
    cutoff="$(reldate "$XG_WINDOW_DAYS" '%Y%m%d')"
    from_iso="$(reldate "$XG_WINDOW_DAYS" '%Y-%m-%d')"
    log "xG — incremental (re-fetching last ${XG_WINDOW_DAYS} days, from ${from_iso})"
    # Drop the trailing window from the .done checkpoint so days that were
    # marked done mid-jornada are retried (late-finishing matches, fresh xG).
    "$PY" - "$XG_DONE" "$cutoff" <<'PY'
import sys
path, cutoff = sys.argv[1], sys.argv[2]
with open(path) as f:
    days = [l.strip() for l in f if l.strip()]
with open(path, "w") as f:
    f.write("\n".join(sorted(d for d in days if d < cutoff)))
PY
    if ! "$PY" scripts/fetch_xg.py --from "$from_iso" --to "$(date +%F)" --out "$XG_CSV"; then
      FAILED+=("xg")
    fi
  else
    log "xG — first run (full backfill, this is slow)"
    if ! "$PY" scripts/fetch_xg.py --out "$XG_CSV"; then FAILED+=("xg"); fi
  fi
fi

# --- 3) Odds: upsert live 1X2 prices -----------------------------------------
if [ "$SKIP_ODDS" = 0 ]; then
  if [ -n "${ODDS_API_KEY:-}" ]; then
    log "Odds — fetch_odds.py --merge"
    if ! "$PY" scripts/fetch_odds.py --merge --out "$ODDS_CSV"; then FAILED+=("odds"); fi
  else
    log "Odds — skipped (set ODDS_API_KEY to enable; https://the-odds-api.com)"
  fi
fi

# --- summary -----------------------------------------------------------------
if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n!! Failed sources: %s\n' "${FAILED[*]}" >&2
  exit 1
fi
log "All requested data sources updated in ${INPUT_DIR}/"
