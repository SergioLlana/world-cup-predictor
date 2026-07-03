# CLAUDE.md

`wcpred`: predicts FIFA World Cup 2026 scorelines, picking the score that
maximises **expected Penka points**. The optimal pick is *not* the most likely
score — see `scoring.best_prediction`.

Full walkthrough of how the model works: `docs/models-explained.md`. README has
end-user usage and data setup.

## Commands

```bash
pip install -e .                 # installs the `wcpred` console script
wcpred update-data               # download/refresh data/input/results.csv (run first)
scripts/update_data.sh           # refresh ALL sources (results+xG+odds) incrementally
scripts/generate_predictions.sh  # date-stamped picks + group standings (track evolution)
scripts/generate_rankings.sh     # date-stamped model rankings (--as-of, --engines)
scripts/run_webapp.sh            # local dashboard on :8026 (needs `.[web]` extra)
scripts/smoke.sh                 # ~1 min CLI smoke: run after touching cli.py/
                                 # backtest.py/the engines, before committing

wcpred predict   --approach odds --odds data/input/odds.csv --days 3
wcpred groups    --approach odds --odds data/input/odds.csv   # MC group standings
wcpred simulate  --approach odds --odds data/input/odds.csv   # full bracket → champion
wcpred ratings   --top 20
wcpred backtest  --tournament all     # regression check: ~594 Penka pts / 290 matches
wcpred tune                           # hyperparameter grid search (no xG)
wcpred tune --elo-engine              # coordinate-tune the Elo engine
```

`--engine {dc,elo,bayes}` works on every subcommand (default `dc`). `--bridge-audit`
adds the inter-confederation calibration table to `backtest`. The Bayesian engine
needs the `.[bayes]` extra + a one-off CmdStan install and is static-only.

## Architecture (`wcpred/`)

Data flow: `data.prepare_training` → `model.DixonColes.fit` →
`predict.predict_fixtures` → `scoring.best_prediction`.

- `config.py` — all hyperparameters and scoring constants; change tuning here.
- `data.py` — load `results.csv`, build the weighted training set (time decay,
  tournament weights, optional xG blend), list upcoming fixtures.
- `model.py` — Dixon-Coles (weighted Poisson + rho low-score correction). The
  default `dc` engine. See `docs/models-explained.md`.
- `model_elo.py` — `EloDixonColes`, the opt-in `--engine elo`. See `docs/elo-engine.md`.
- `model_bayes.py` + `stan/*.stan` — `BayesianDixonColes`, the opt-in `--engine bayes`
  (hierarchical confederation-offset prior). See `docs/bayesian-engine.md`.
- `anchor.py` — two-timescale confederation re-anchoring (a rejected robustness
  experiment, available via `CONF_ANCHOR_BETA` / `--anchor-beta`). See
  `docs/known-limitations.md`.
- `scoring.py` — Penka/Superbru points, Closeness Index, and the scoreline pick
  step (`ev` default vs `outcome`). See `docs/pick-strategy.md`.
- `odds.py` — odds → margin-free 1X2 probs → market-implied score matrix.
- `predict.py` — pipeline blending model + odds (`ODDS_WEIGHT = 1.0`: 1X2 from the
  market, model shapes scorelines within each outcome).
- `groups.py` / `tournament.py` — Monte Carlo group standings / full-tournament
  bracket; played matches enter with their real result.
- `thirds_table.py` — FIFA Annex-C allocation of the 8 best thirds (auto-generated
  by `scripts/experiments/build_thirds_table.py`).
- `confederations.py` — confederation inference + bridge/opponent metrics.
- `backtest.py` — six past tournaments, rolling re-fit, RPS/log-loss/points, `tune`.
- `cli.py` — argparse entry point; subcommands map to `cmd_*`.

## Web app (`webapp/`)

FastAPI (`server.py`, install `.[web]`, port 8026) serving a JSON API over the
date-stamped CSVs in `data/`, plus a vanilla-JS frontend (`static/`). Every data
endpoint takes `approach` (odds/history) and `engine` (dc/elo/bayes, **default elo**);
the pick strategy (`ev`/`outcome`, **default outcome**) is a client-side column
toggle, not a filename segment. `POST /api/refresh` re-runs the generators in the
background. Tabs: advancement probabilities, group positions, calendar, rankings,
connectivity. See `docs/webapp-public-deploy-plan.md` for the public deploy plan.

## Conventions & rules for agents

- **Regenerability (hard rule).** The default `dc` model must stay byte-for-byte
  regenerable: new parameters default-off, never regenerate past snapshots with a
  changed model, and keep experiment outputs outside
  `data/predictions|groups|simulations` (use `data/experiments/`). `elo`/`bayes`
  are additive and opt-in.
- **No test suite.** `wcpred backtest --tournament all` is the regression check
  after touching the model. Tune on RPS/log-loss (low variance); use points to
  break ties.
- **Generated files live under `data/`**, never the project root — inputs in
  `data/input/`, and `--out` routed to `PREDICTIONS_DIR`/`GROUPS_DIR`/`SIM_DIR`/
  `RANKINGS_DIR` by `cli.resolve_out`. Paths are set in `config.py`.
- **Team names** must match the martj42 dataset exactly (`United States`,
  `South Korea`, `Czech Republic`, `Ivory Coast`, `Turkey`).
- **Score matrices** are `P[home_goals, away_goals]` over a `0..MAX_GOALS` grid.
- **`--as-of`** controls the train/predict cutoff: training uses only matches
  *before* it; fixtures are every WC match dated on/after it (result ignored, so
  past snapshots regenerate without leakage). Odds are frozen per snapshot
  (`data.resolve_odds_path`, `ODDS_CUTOVER` 17:00 local).
- **`--extra-time`/`--shootout`** are off by default — Penka/Superbru score the 90'
  result, so leave them off.
- **xG is excluded for WC 2026** (FotMob coverage too partial; it doesn't improve
  points). Validate/tune/predict without it. See `docs/data-sources.md`.
- **Known modelling limitations** (weakly-connected confederations inflate
  schedule-easy teams; how to read cross-confederation comparisons):
  `docs/known-limitations.md`, `docs/connectivity.md`.

## Documentation map (`docs/`)

`models-explained.md` · `elo-engine.md` · `bayesian-engine.md` · `pick-strategy.md`
· `data-sources.md` · `known-limitations.md` · `connectivity.md` ·
`webapp-public-deploy-plan.md` · `next-steps.md` (July 2026 review; all six
proposals implemented 2026-07-03, outcomes inline).
