#!/usr/bin/env bash
# Tight-sigma_conf sensitivity sweep (docs/bayesian-engine.md).
# Six-tournament static backtest of the dynamic Bayesian Dixon-Coles at a
# grid of confederation-offset prior scales, with the bridge audit + control cases.
set -u
cd "$(dirname "$0")/../../.."   # repo root
OUT="data/experiments/sigma_conf_sweep"
ASOF="2026-06-14"
SCALES="0.5 0.25 0.1 0.05 0.01"

for s in $SCALES; do
  echo "================ sigma_conf_scale=$s ================"
  log="$OUT/backtest_${s}.log"
  python3 -m wcpred.cli backtest --tournament all --static --engine bayes \
      --bayes-dynamic --bayes-block halfyear --bayes-sigma-conf "$s" \
      --bridge-audit > "$log" 2>&1
  grep -iE "^Backtest|bias_a|CONMEBOL|CONCACAF|inter-confederation" "$log" \
      || tail -5 "$log"
  echo "---- control cases scale=$s ----"
  python3 "$OUT/control_cases.py" "$s" "$ASOF" > "$OUT/control_cases_${s}.log" 2>&1
  cat "$OUT/control_cases_${s}.log"
done
echo "================ SWEEP DONE ================"
