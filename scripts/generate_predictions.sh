#!/usr/bin/env bash
#
# Regenerate Penka predictions, group standings and a full-tournament
# simulation with a date-stamped output filename so you can keep every run and
# watch how picks, standings and title odds evolve.
#
#   data/predictions/picks_<approach>_<stamp>.csv
#   data/groups/groups_<approach>_<stamp>.csv
#   data/simulations/sim_<approach>_<stamp>.csv
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
#   --engines LIST   comma-separated engines to run: dc | elo | bayes
#                    (default: dc). Each engine adds an _<engine> label segment
#                    (picks_<approach>_dc_<date>.csv etc.). bayes needs the
#                    .[bayes] extra + CmdStan and is slow (MCMC).
#   --as-of DATE     train on matches before DATE; also the filename stamp.
#                    Past dates pick the matching data/input/odds/ snapshot
#                    (default: today)
#   --days N         predictions: only fixtures within N days of --as-of
#   --sims N         groups + simulation: Monte Carlo count (wcpred defaults:
#                    groups 1000000, simulation 100000)
#   --odds-weight W  predictions: market vs model blend (default wcpred: 1.0)
#   --xg-alpha A     xG blend: alpha*goals + (1-alpha)*xG (default wcpred: 0.6)
#   --extra-time     predictions: resolve knockout draws through extra time
#   --shootout       predictions: also resolve ties on penalties (implies --extra-time)
#   --refresh        refresh data/input/ (results+xG+odds) via update_data.sh first,
#                    so already-played matches are picked up before generating
#   --predict-only   only generate predictions
#   --groups-only    only generate group standings
#   --simulate-only  only generate the full-tournament simulation
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
ENGINES="dc"
ASOF=""
DAYS=""
SIMS=""
ODDS_WEIGHT=""
XG_ALPHA=""
EXTRA_TIME=0
SHOOTOUT=0
DO_PREDICT=1
DO_GROUPS=1
DO_SIMULATE=1
REFRESH=0
LABEL=""
WITH_TIME=0

usage() {
  cat <<'EOF'
Regenerate Penka predictions, group standings and a full-tournament
simulation with date-stamped outputs.

Usage: scripts/generate_predictions.sh [options]

Options:
  --approach A     history | odds | xg | full
                   (default: odds if data/input/odds.csv exists, else history)
  --engines LIST   comma-separated engines: dc | elo | bayes (default: dc).
                   Each engine adds an _<engine> filename segment.
                   bayes needs the .[bayes] extra + CmdStan and is slow (MCMC).
  --as-of DATE     train on matches before DATE; also the filename stamp (default: today)
  --days N         predictions: only fixtures within N days of --as-of
  --sims N         groups + simulation: Monte Carlo count
  --odds-weight W  predictions: market vs model blend
  --xg-alpha A     xG blend: alpha*goals + (1-alpha)*xG
  --extra-time     predictions: resolve knockout draws through extra time
  --shootout       predictions: also resolve ties on penalties (implies --extra-time)
  --refresh        refresh data/input/ (results+xG+odds) via update_data.sh first
  --predict-only   only generate predictions
  --groups-only    only generate group standings
  --simulate-only  only generate the full-tournament simulation
  --label STR      filename segment instead of the approach name
  --time           append _HHMM to the stamp (keep multiple runs per day)
  -h, --help       show this help and exit

Env vars: PYTHON (default: python3).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --approach)     APPROACH="$2"; shift 2 ;;
    --engines)      ENGINES="$2"; shift 2 ;;
    --as-of)        ASOF="$2"; shift 2 ;;
    --days)         DAYS="$2"; shift 2 ;;
    --sims)         SIMS="$2"; shift 2 ;;
    --odds-weight)  ODDS_WEIGHT="$2"; shift 2 ;;
    --xg-alpha)     XG_ALPHA="$2"; shift 2 ;;
    --extra-time)   EXTRA_TIME=1; shift ;;
    --shootout)     SHOOTOUT=1; shift ;;
    --refresh)      REFRESH=1; shift ;;
    --predict-only)  DO_GROUPS=0; DO_SIMULATE=0; shift ;;
    --groups-only)   DO_PREDICT=0; DO_SIMULATE=0; shift ;;
    --simulate-only) DO_PREDICT=0; DO_GROUPS=0; shift ;;
    --label)        LABEL="$2"; shift 2 ;;
    --time)         WITH_TIME=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

# Engines to run (comma-separated, e.g. dc,elo,bayes). Each engine gets an
# _<engine> label segment so their CSVs don't collide: dc → picks_<approach>_dc_
# <date>.csv (the production model the webapp reads), elo/bayes likewise (the
# webapp's regex only matches _dc, so elo/bayes stay invisible there). 'bayes'
# needs the .[bayes] extra + CmdStan and is slow (MCMC); a failure there is
# reported, not fatal.
IFS=',' read -r -a ENGINE_LIST <<< "$ENGINES"
for e in "${ENGINE_LIST[@]}"; do
  case "$e" in
    dc|elo|bayes) ;;
    *) echo "Unknown engine: $e (expected dc|elo|bayes)" >&2; exit 2 ;;
  esac
done

# Refresh data/input/ first so already-played matches (and fresh odds) are
# picked up. Done before the approach default below, since that checks for
# odds.csv. A refresh failure is a warning, not fatal: generate with what we have.
if [ "$REFRESH" = 1 ]; then
  printf '\n=== Refreshing data/input/ via update_data.sh ===\n'
  if ! "$SCRIPT_DIR/update_data.sh"; then
    printf '\n!! update_data.sh reported a failure; continuing with existing data\n' >&2
  fi
fi

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
  odds|full)
    # Frozen-in-time: for a past --as-of, use the odds snapshot in force that
    # morning (data/input/odds/, see wcpred.data.resolve_odds_path) so later
    # market moves don't leak into a regenerated run.
    ODDS_FILE="$ODDS_CSV"
    if [ -n "$ASOF" ]; then
      resolved="$("$PY" -c "from wcpred.data import resolve_odds_path; print(resolve_odds_path('$ASOF') or '')")"
      if [ -n "$resolved" ]; then
        ODDS_FILE="$resolved"
        [ "$resolved" != "$ODDS_CSV" ] && printf 'Using odds snapshot %s for --as-of %s\n' "$resolved" "$ASOF"
      else
        printf 'WARNING: no odds snapshot in force for %s (see config.ODDS_CUTOVER); falling back to live %s (possible leakage)\n' \
          "$ASOF" "$ODDS_CSV" >&2
      fi
    fi
    [ -f "$ODDS_FILE" ] && common_args+=(--odds "$ODDS_FILE")
    ;;
esac
case "$APPROACH" in
  xg|full)       [ -f "$XG_CSV" ]   && common_args+=(--xg "$XG_CSV") ;;
esac

FAILED=()
log() { printf '\n=== %s ===\n' "$*"; }

for ENGINE in "${ENGINE_LIST[@]}"; do
  # Every engine (dc included) gets an _<engine> label segment and passes the
  # explicit --engine flag, so the three engines' CSVs never collide. The webapp
  # engine picker reads whichever segment is selected (picks_<approach>_<engine>_
  # <date>.csv); dc stays the default.
  ENG_LABEL="${LABEL}_${ENGINE}"

  if [ "$DO_PREDICT" = 1 ]; then
    log "Predictions [$ENGINE] — approach=$APPROACH → data/predictions/picks_${ENG_LABEL}_${STAMP}.csv"
    pargs=("${common_args[@]}" --engine "$ENGINE")
    [ -n "$DAYS" ]      && pargs+=(--days "$DAYS")
    [ "$EXTRA_TIME" = 1 ] && pargs+=(--extra-time)
    [ "$SHOOTOUT" = 1 ]   && pargs+=(--shootout)
    pargs+=(--out "picks_${ENG_LABEL}_${STAMP}.csv")
    if ! wcpred_cli predict "${pargs[@]}"; then FAILED+=("predict[$ENGINE]"); fi
  fi

  if [ "$DO_GROUPS" = 1 ]; then
    log "Groups [$ENGINE] — approach=$APPROACH → data/groups/groups_${ENG_LABEL}_${STAMP}.csv"
    gargs=("${common_args[@]}" --engine "$ENGINE")
    [ -n "$SIMS" ] && gargs+=(--sims "$SIMS")
    gargs+=(--out "groups_${ENG_LABEL}_${STAMP}.csv")
    if ! wcpred_cli groups "${gargs[@]}"; then FAILED+=("groups[$ENGINE]"); fi
  fi

  if [ "$DO_SIMULATE" = 1 ]; then
    log "Simulation [$ENGINE] — approach=$APPROACH → data/simulations/sim_${ENG_LABEL}_${STAMP}.csv"
    sargs=("${common_args[@]}" --engine "$ENGINE")
    [ -n "$SIMS" ] && sargs+=(--sims "$SIMS")
    sargs+=(--out "sim_${ENG_LABEL}_${STAMP}.csv")
    if ! wcpred_cli simulate "${sargs[@]}"; then FAILED+=("simulate[$ENGINE]"); fi
  fi
done

if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n!! Failed: %s\n' "${FAILED[*]}" >&2
  exit 1
fi
log "Done (stamp ${STAMP})"
