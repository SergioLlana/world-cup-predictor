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
wcpred groups --approach odds --odds data/input/odds.csv  # MC group standings
wcpred simulate --approach odds --odds data/input/odds.csv  # full bracket → champion
wcpred backtest --tournament all      # validation: ~295 pts / 290 matches
wcpred tune                           # hyperparameter grid search (no xG)
wcpred ratings --top 20
scripts/run_webapp.sh                 # local dashboard on :8026 (needs `.[web]` extra)
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
- `odds.py` — odds → margin-free 1X2 probs → market-implied score matrix.
- `predict.py` — pipeline blending model + odds. `ODDS_WEIGHT = 1.0`: the 1X2
  comes fully from the market; the model only shapes scorelines within each
  outcome (`--odds-weight` reintroduces the model's 1X2).
- `groups.py` — Monte Carlo group standings (`groups`); played matches enter
  with their real result. Blends odds into each fixture like
  `predict`/`simulate` (`--approach odds`; model-only without it). The CLI
  passes `tournament.OFFICIAL_GROUPS` so labels match the real draw.
- `tournament.py` — full-tournament Monte Carlo (`simulate`): joint group sim,
  8 best thirds, official FIFA Round-of-32 bracket through the final, extra-time
  + penalty resolution. Uses real results (group *and* knockout) where played,
  so it also runs mid-tournament. Knockouts are neutral-venue (see
  `docs/known-limitations.md`). Group labels come from `OFFICIAL_GROUPS` (the
  real A..L draw), not `groups.derive_groups`' kick-off ordering.
- `thirds_table.py` — auto-generated FIFA Annex-C allocation of the 8 best
  thirds to Round-of-32 slots (495 combinations); regenerate with
  `scripts/build_thirds_table.py`.
- `backtest.py` — six past tournaments, rolling re-fit, Superbru/RPS/log-loss
  metrics, and the `tune` hyperparameter grid search.
- `cli.py` — argparse entry point (`main`); subcommands map to `cmd_*`.

## Web app (`webapp/`)

- `server.py` — FastAPI (install `.[web]`; run `scripts/run_webapp.sh`, port
  8026). JSON API over the date-stamped CSVs in `data/` (re-read per request,
  no cache) plus `POST /api/refresh` which runs `generate_predictions.sh
  --refresh` for both approaches in a background thread. Owns the team →
  flag-code/Spanish-name map (`TEAMS`); odds↔fixture matching reuses
  `predict._norm_team` and tolerates swapped home/away (host MD3 quirk).
  `GET /api/matrix` re-fits Dixon-Coles as of the snapshot in force on the
  match date (lru_cached per as-of + results.csv mtime) to serve the full
  score matrix behind a pick.
- `static/` — vanilla JS frontend (`app.js`), no external deps; charts are
  hand-rolled SVG; `flags/` holds the 48 country SVGs (flagcdn). The odds
  toggle switches between the `odds`/`history` CSV variants; the calendar
  shows each match the prediction from the latest snapshot ≤ its date.

## Conventions

- Generated files live under `data/`, never the project root:
  inputs in `data/input/` (`results.csv`/`odds.csv`/`xg.csv`),
  `predict --out` in `data/predictions/`, `groups --out` in `data/groups/`,
  `simulate --out` in `data/simulations/`.
  Paths are set in `config.py` (`INPUT_DIR`/`PREDICTIONS_DIR`/`GROUPS_DIR`/
  `SIM_DIR`, `RESULTS_PATH`); writers `os.makedirs` their target, and
  `cli.resolve_out` routes a bare `--out` filename into the right folder.
- Team names must match the martj42 dataset exactly (e.g. `United States`,
  `South Korea`, `Czech Republic`, `Ivory Coast`, `Turkey`).
- Score matrices are `P[home_goals, away_goals]` over a `0..MAX_GOALS` grid.
- `--as-of` controls the train/predict cutoff — training uses only matches
  *before* it, so past results inform future picks.
- `predict --extra-time`/`--shootout` resolve knockout ties (extra time at
  `EXTRA_TIME_FRACTION` of the scoring rate, then a penalty win). Both are
  **off by default** — Superbru scores the 90' result, so leave them off for it.
- xG source is `scripts/fetch_xg.py` (FotMob public JSON API). It writes
  `xg.csv` in the `date,home_team,away_team,home_xg,away_xg` format `data.py`
  expects. FotMob has NO xG for friendlies and only ~28% of qualifiers.
- `scripts/fetch_sofascore.py` (needs `curl_cffi` to pass Cloudflare) scrapes
  SofaScore for historical 1X2 odds (`data/input/odds_history.csv`, back to
  ≥2018, single book) and supplemental xG. See `docs/sofascore.md`.
- Data-source landscape, coverage cutoffs and gotchas: `docs/data-sources.md`.
- Known modelling limitations (e.g. ratings of teams from weakly-connected
  confederations like the AFC are schedule-inflated): `docs/known-limitations.md`.
  Key facts: FotMob xG only goes back to ~mid-2022 and never covers friendlies;
  free historical odds exist only via SofaScore (single book); the model trains
  on goals/xG but never on odds (odds are a predict-time blend only).

Full usage, data sources and tuning notes live in `README.md`.
