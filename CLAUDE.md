# CLAUDE.md

`wcpred`: predicts FIFA World Cup 2026 scorelines, picking the score that
maximises **expected Superbru points** (3 exact / 1.5 outcome+close / 1 outcome).
The optimal pick is *not* the most likely score — see `scoring.best_prediction`.

## Commands

```bash
pip install -e .                 # installs the `wcpred` console script
wcpred update-data               # download/refresh data/input/results.csv (run first)
scripts/update_data.sh           # refresh ALL sources (results+xG+odds) incrementally
scripts/generate_predictions.sh  # date-stamped picks + group standings (track evolution)
wcpred predict --approach odds --odds data/input/odds.csv --days 3
wcpred backtest --tournament all      # validation: ~295 pts / 290 matches
wcpred tune                           # hyperparameter grid search (no xG)
wcpred ratings --top 20
```

No test suite — `backtest --tournament all` is the regression check after
touching the model. It covers six tournaments (wc2018, euro2021, copa2021,
wc2022, euro2024, copa2024) with a rolling per-matchday re-fit (the live
`--as-of` protocol; `--static` for a single pre-tournament fit) and reports
Superbru points plus 1X2 RPS and exact-score log-loss. Tune on RPS/log-loss
(low variance), use points to break ties — points alone are too noisy on
~64 matches per tournament.

## Architecture (`wcpred/`)

Data flows: `data.prepare_training` → `model.DixonColes.fit` →
`predict.predict_fixtures` → `scoring.best_prediction`.

- `config.py` — all hyperparameters and scoring constants; change tuning here.
- `data.py` — download/load `results.csv`, build the weighted training set
  (time decay, tournament weights, optional xG blend or goal-margin cap),
  list upcoming fixtures.
- `model.py` — Dixon-Coles (weighted Poisson + rho low-score correction).
  Produces per-team attack/defence ratings and score-probability matrices.
- `scoring.py` — Superbru points, Closeness Index, expected-points optimiser.
- `odds.py` — odds → de-vigged 1X2 probs → market-implied score matrix.
- `predict.py` — pipeline blending model + odds (`0.75*market + 0.25*model`).
- `backtest.py` — six past tournaments, rolling re-fit, Superbru/RPS/log-loss
  metrics, and the `tune` hyperparameter grid search.
- `cli.py` — argparse entry point (`main`); subcommands map to `cmd_*`.

## Conventions

- Generated files live under `data/`, never the project root:
  inputs in `data/input/` (`results.csv`/`odds.csv`/`xg.csv`),
  `predict --out` in `data/predictions/`, `groups --out` in `data/groups/`.
  Paths are set in `config.py` (`INPUT_DIR`/`PREDICTIONS_DIR`/`GROUPS_DIR`,
  `RESULTS_PATH`); writers `os.makedirs` their target, and `cli.resolve_out`
  routes a bare `--out` filename into the right folder.
- Team names must match the martj42 dataset exactly (e.g. `United States`,
  `South Korea`, `Czech Republic`, `Ivory Coast`, `Turkey`).
- Score matrices are `P[home_goals, away_goals]` over a `0..MAX_GOALS` grid.
- `--as-of` controls the train/predict cutoff — training uses only matches
  *before* it, so past results inform future picks.
- `predict --extra-time`/`--shootout` resolve knockout ties (extra time at
  `EXTRA_TIME_FRACTION` of the scoring rate, then a penalty win). Both are
  **off by default** — Superbru scores the 90' result, so leave them off for it.
- xG source is `scripts/fetch_xg.py` (FotMob public JSON API). FBref is **not**
  an option — it lost its Opta xG feed in Jan 2026. The script writes `xg.csv`
  in the `date,home_team,away_team,home_xg,away_xg` format `data.py` expects.
- Data-source landscape, coverage cutoffs and gotchas: `docs/data-sources.md`.
- Known modelling limitations (e.g. ratings of teams from weakly-connected
  confederations like the AFC are schedule-inflated): `docs/known-limitations.md`.
  Key facts: FotMob xG only goes back to ~mid-2022; historical odds have no
  free source (The Odds API history is paid, 2020+); the model trains on
  goals/xG but never on odds (odds are a predict-time blend only).

Full usage, data sources and tuning notes live in `README.md`.
