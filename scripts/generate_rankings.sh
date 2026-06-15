#!/usr/bin/env bash
#
# Regenerate the model's team-strength rankings with a date-stamped output
# filename so you can keep every run and watch how the ratings evolve.
#
#   data/rankings/ratings_<engine>_<stamp>.csv
#
# Unlike predictions, rankings come purely from the fitted model — they do not
# depend on the betting odds (the `--approach`), so there is no approach segment
# in the filename. Each CSV holds, for every team in the model: its
# confederation, attack/defence coefficients, the overall rating (attack −
# defence), the weighted mean opponent rating (the average difficulty of its
# training schedule) and, for the Elo engine, its current Elo.
#
# <stamp> is the --as-of date (defaults to today), so daily runs never overwrite
# each other and a past date regenerates that day's snapshot (training uses only
# matches before --as-of, so there is no leakage).
#
# Usage:
#   scripts/generate_rankings.sh [options]
#
# Options:
#   --engines LIST   comma-separated engines to run: dc | elo | bayes
#                    (default: dc). Each engine gets its own _<engine> segment.
#                    bayes needs the .[bayes] extra + CmdStan and is slow (MCMC).
#   --as-of DATE     train on matches before DATE; also the filename stamp
#                    (default: today)
#   --refresh        refresh data/input/ (results+xG+odds) via update_data.sh
#                    first, so already-played matches are picked up
#   --label STR      extra filename segment (ratings_<label>_<engine>_<date>.csv)
#   --time           append _HHMM to the stamp (keep multiple runs per day)
#   -h, --help       show this help and exit
#
# Env vars: PYTHON (default: python3).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"

ENGINES="dc"
ASOF=""
REFRESH=0
LABEL=""
WITH_TIME=0

usage() {
  cat <<'EOF'
Regenerate the model's team-strength rankings with a date-stamped output.

Usage: scripts/generate_rankings.sh [options]

Options:
  --engines LIST   comma-separated engines: dc | elo | bayes (default: dc).
                   Each engine gets its own _<engine> filename segment.
                   bayes needs the .[bayes] extra + CmdStan and is slow (MCMC).
  --as-of DATE     train on matches before DATE; also the filename stamp (default: today)
  --refresh        refresh data/input/ (results+xG+odds) via update_data.sh first
  --label STR      extra filename segment (ratings_<label>_<engine>_<date>.csv)
  --time           append _HHMM to the stamp (keep multiple runs per day)
  -h, --help       show this help and exit

Env vars: PYTHON (default: python3).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --engines) ENGINES="$2"; shift 2 ;;
    --as-of)   ASOF="$2"; shift 2 ;;
    --refresh) REFRESH=1; shift ;;
    --label)   LABEL="$2"; shift 2 ;;
    --time)    WITH_TIME=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

IFS=',' read -r -a ENGINE_LIST <<< "$ENGINES"
for e in "${ENGINE_LIST[@]}"; do
  case "$e" in
    dc|elo|bayes) ;;
    *) echo "Unknown engine: $e (expected dc|elo|bayes)" >&2; exit 2 ;;
  esac
done

# Refresh data/input/ first so already-played matches are picked up. A refresh
# failure is a warning, not fatal: generate with what we have.
if [ "$REFRESH" = 1 ]; then
  printf '\n=== Refreshing data/input/ via update_data.sh ===\n'
  if ! "$SCRIPT_DIR/update_data.sh"; then
    printf '\n!! update_data.sh reported a failure; continuing with existing data\n' >&2
  fi
fi

# Filename stamp: the snapshot date (--as-of, else today), optionally + time.
STAMP="${ASOF:-$(date +%F)}"
[ "$WITH_TIME" = 1 ] && STAMP="${STAMP}_$(date +%H%M)"

wcpred_cli() { "$PY" -m wcpred.cli "$@"; }

FAILED=()
log() { printf '\n=== %s ===\n' "$*"; }

for ENGINE in "${ENGINE_LIST[@]}"; do
  SEG="$ENGINE"
  [ -n "$LABEL" ] && SEG="${LABEL}_${ENGINE}"
  OUT="ratings_${SEG}_${STAMP}.csv"
  log "Rankings [$ENGINE] → data/rankings/${OUT}"
  rargs=(--engine "$ENGINE" --out "$OUT")
  [ -n "$ASOF" ] && rargs+=(--as-of "$ASOF")
  if ! wcpred_cli ratings "${rargs[@]}"; then FAILED+=("ratings[$ENGINE]"); fi
done

if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n!! Failed: %s\n' "${FAILED[*]}" >&2
  exit 1
fi
log "Done (stamp ${STAMP})"
