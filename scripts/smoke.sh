#!/usr/bin/env bash
#
# Minimal smoke check (~1 min). NOT a test suite — the regression check after
# touching the model is still `wcpred backtest --tournament all` — but that
# command itself sat broken on main for two weeks once (docs/next-steps.md §4)
# because nothing exercised the CLI paths. This does, cheaply:
#
#   backtest  — the dc and elo CLI paths (static, one tournament)
#   predict   — the fixture pipeline (model fit + upcoming fixtures + picks)
#   groups    — the group-stage Monte Carlo
#   simulate  — the full-bracket Monte Carlo (thirds table + knockouts)
#
# Run it after touching cli.py / backtest.py / the engines, before committing.
# --as-of is pinned inside the 2026 group stage so the fixture commands keep
# finding fixtures (and stay reproducible) after the tournament ends; training
# still uses whatever results.csv currently holds before that date.
#
# Usage: scripts/smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."

AS_OF=2026-06-15

run() { echo; echo "==> $*"; "$@" > /dev/null; }

run wcpred backtest --tournament wc2022 --static
run wcpred backtest --tournament wc2022 --static --engine elo
run wcpred predict  --approach history --as-of "$AS_OF" --days 2
run wcpred groups   --approach history --as-of "$AS_OF" --sims 2000
run wcpred simulate --approach history --as-of "$AS_OF" --sims 2000

echo
echo "smoke OK"
