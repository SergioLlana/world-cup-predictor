#!/usr/bin/env bash
#
# Regenerate Superbru predictions (and group standings) with a date-stamped
# output filename so you can keep every run and watch how picks evolve.
#
#   data/predictions/picks_<approach>_<stamp>.csv
#   data/groups/groups_<approach>_<stamp>.csv
#
# <stamp> is the --as-of date (defaults to today, i.e. the day you generated it),
# so daily runs never overwrite each other. Override the <approach> segment with
# --label. Input files under data/input/ are wired in automatically when the
# chosen approach needs them.
#
# Usage:
#   scripts/generate_predictions.sh [options]
#
# Options:
#   --approach A     history | odds | xg | full
#                    (default: odds if data/input/odds.csv exists, else history)
#   --as-of DATE     train on matches before DATE; also the filename stamp
#                    (default: today)
#   --days N         predictions: only fixtures within N days of --as-of
#   --sims N         groups: Monte Carlo simulations per group (default wcpred: 1000000)
#   --odds-weight W  predictions: market vs model blend (default wcpred: 0.75)
#   --xg-alpha A     xG blend: alpha*goals + (1-alpha)*xG (default wcpred: 0.6)
#   --extra-time     predictions: resolve knockout draws through extra time
#   --shootout       predictions: also resolve ties on penalties (implies --extra-time)
#   --predict-only   only generate predictions (skip groups)
#   --groups-only    only generate group standings (skip predictions)
#   --label STR      filename segment instead of the approach name
#   --time           append _HHMM to the stamp (keep multiple runs per day)
#   -h, --help       show this help and exit
#
# Env vars: PYTHON (default: python3).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
INPUT_DIR="data/input"
ODDS_CSV="$INPUT_DIR/odds.csv"
XG_CSV="$INPUT_DIR/xg.csv"

APPROACH=""
ASOF=""
DAYS=""
SIMS=""
ODDS_WEIGHT=""
XG_ALPHA=""
EXTRA_TIME=0
SHOOTOUT=0
DO_PREDICT=1
DO_GROUPS=1
LABEL=""
WITH_TIME=0

usage() {
  cat <<'EOF'
Regenerate Superbru predictions and group standings with date-stamped outputs.

Usage: scripts/generate_predictions.sh [options]

Options:
  --approach A     history | odds | xg | full
                   (default: odds if data/input/odds.csv exists, else history)
  --as-of DATE     train on matches before DATE; also the filename stamp (default: today)
  --days N         predictions: only fixtures within N days of --as-of
  --sims N         groups: Monte Carlo simulations per group
  --odds-weight W  predictions: market vs model blend
  --xg-alpha A     xG blend: alpha*goals + (1-alpha)*xG
  --extra-time     predictions: resolve knockout draws through extra time
  --shootout       predictions: also resolve ties on penalties (implies --extra-time)
  --predict-only   only generate predictions (skip groups)
  --groups-only    only generate group standings (skip predictions)
  --label STR      filename segment instead of the approach name
  --time           append _HHMM to the stamp (keep multiple runs per day)
  -h, --help       show this help and exit

Env vars: PYTHON (default: python3).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --approach)     APPROACH="$2"; shift 2 ;;
    --as-of)        ASOF="$2"; shift 2 ;;
    --days)         DAYS="$2"; shift 2 ;;
    --sims)         SIMS="$2"; shift 2 ;;
    --odds-weight)  ODDS_WEIGHT="$2"; shift 2 ;;
    --xg-alpha)     XG_ALPHA="$2"; shift 2 ;;
    --extra-time)   EXTRA_TIME=1; shift ;;
    --shootout)     SHOOTOUT=1; shift ;;
    --predict-only) DO_GROUPS=0; shift ;;
    --groups-only)  DO_PREDICT=0; shift ;;
    --label)        LABEL="$2"; shift 2 ;;
    --time)         WITH_TIME=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

# Default approach: prefer the market signal when odds are available.
if [ -z "$APPROACH" ]; then
  if [ -f "$ODDS_CSV" ]; then APPROACH="odds"; else APPROACH="history"; fi
fi

# Filename stamp: the snapshot date (--as-of, else today), optionally + time.
STAMP="${ASOF:-$(date +%F)}"
[ "$WITH_TIME" = 1 ] && STAMP="${STAMP}_$(date +%H%M)"
[ -z "$LABEL" ] && LABEL="$APPROACH"

wcpred_cli() { "$PY" -m wcpred.cli "$@"; }

# Shared model/source flags for both subcommands.
common_args=(--approach "$APPROACH")
[ -n "$ASOF" ]        && common_args+=(--as-of "$ASOF")
[ -n "$ODDS_WEIGHT" ] && common_args+=(--odds-weight "$ODDS_WEIGHT")
[ -n "$XG_ALPHA" ]    && common_args+=(--xg-alpha "$XG_ALPHA")
case "$APPROACH" in
  odds|full)     [ -f "$ODDS_CSV" ] && common_args+=(--odds "$ODDS_CSV") ;;
esac
case "$APPROACH" in
  xg|full)       [ -f "$XG_CSV" ]   && common_args+=(--xg "$XG_CSV") ;;
esac

FAILED=()
log() { printf '\n=== %s ===\n' "$*"; }

if [ "$DO_PREDICT" = 1 ]; then
  log "Predictions — approach=$APPROACH → data/predictions/picks_${LABEL}_${STAMP}.csv"
  pargs=("${common_args[@]}")
  [ -n "$DAYS" ]      && pargs+=(--days "$DAYS")
  [ "$EXTRA_TIME" = 1 ] && pargs+=(--extra-time)
  [ "$SHOOTOUT" = 1 ]   && pargs+=(--shootout)
  pargs+=(--out "picks_${LABEL}_${STAMP}.csv")
  if ! wcpred_cli predict "${pargs[@]}"; then FAILED+=("predict"); fi
fi

if [ "$DO_GROUPS" = 1 ]; then
  log "Groups — approach=$APPROACH → data/groups/groups_${LABEL}_${STAMP}.csv"
  gargs=("${common_args[@]}")
  [ -n "$SIMS" ] && gargs+=(--sims "$SIMS")
  gargs+=(--out "groups_${LABEL}_${STAMP}.csv")
  if ! wcpred_cli groups "${gargs[@]}"; then FAILED+=("groups"); fi
fi

if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n!! Failed: %s\n' "${FAILED[*]}" >&2
  exit 1
fi
log "Done (stamp ${STAMP})"
