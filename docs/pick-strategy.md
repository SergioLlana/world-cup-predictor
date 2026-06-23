# Scoreline pick strategy (`--pick-strategy`)

The model produces a **probability matrix** `P[home_goals, away_goals]` per match.
Turning that matrix into **one scoreline** to bet is a separate step —
`scoring.select_prediction`, independent of the model and tuning. There are two
strategies:

- **`ev`** (default, regenerable): the scoreline that **maximises expected Penka
  points** (`scoring.best_prediction`, `argmax E[pts]`). Optimal in isolation but
  **too conservative**: it tends to put 1-0 on the favourite.
- **`outcome`**: the **most likely 1X2 outcome** (1/X/2) and, within it, the **most
  likely scoreline** (`scoring.best_prediction_outcome`).

## Why `outcome` scores more

Compared over the six backtest tournaments (rolling, `dc` engine, Penka):

| strategy | points | pts/match |
|---|---:|---:|
| **`outcome`** | **643** | **2.217** |
| `ev` (default) | 594 | 2.048 |

**+8% Penka points.** And over the 28 already-played WC 2026 matches
(odds/dc reconstructed): **45 pts (outcome) vs 38 pts (ev)**, +18%.

The key finding: `outcome` does **not** win by predicting more draws (it predicts
almost none, like `ev`). It wins by choosing **better win scorelines**. The
expected-value optimiser is too conservative and defaults to 1-0; `outcome` puts the
favourite's *most likely* win scoreline (2-0, 2-1…), which catches more exacts
(5 pts) and goal differences (3 pts) where `ev` settled for "winner only" (2 pts).

What does **not** work (measured and discarded): forcing draws when `P_X` exceeds a
threshold. The model almost never assigns >30% to a draw — not even in this
draw-heavy World Cup — so the rule barely fires. That is a **calibration** limit of
the probabilities, not of the pick step: you cannot "choose" draws the model doesn't
give you.

## In the CSVs and the web app

Every row of `data/predictions/picks_*.csv` carries **both** predictions
(`predict.predict_fixtures` always computes them from the same matrix):

- `pick` / `expected_points` → `ev` strategy.
- `pick_outcome` / `expected_points_outcome` → `outcome` strategy.

The web app (`webapp/`) defaults to **Elo engine + `outcome` strategy** with a
toggle ("Marcador más probable") that switches which column is shown — without
reloading, since both travel in the same CSV. Old snapshots (only `ev`) fall back to
`pick` (`app.js:pickOf`). `scripts/enrich_picks_outcome.py` adds the `pick_outcome`
column to old snapshots **without touching** the `ev` columns.

## Regenerability rule

The production strategy for analysis (CLI/backtest) stays on **`ev`** on purpose: the
`data/predictions/` snapshots reproduce identically in their `ev` columns.
`outcome` is opt-in on the CLI:

```bash
wcpred predict --approach odds --odds data/input/odds.csv --pick-strategy outcome
scripts/generate_predictions.sh --pick-strategy outcome   # live workflow
wcpred backtest --tournament all --pick-strategy outcome   # re-validate
```

Past snapshots are not regenerated with `outcome`: already-played matches were bet
with `ev`, and rewriting history would break the regenerability rule. `outcome` is
used **from today onward**.
