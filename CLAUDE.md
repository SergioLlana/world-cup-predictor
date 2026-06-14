# CLAUDE.md

`wcpred`: predicts FIFA World Cup 2026 scorelines, picking the score that
maximises **expected Penka points** — exact / goal-difference-or-draw / winner,
paying 5/3/2 in the group stage, 8/5/3 in the R32+R16 and 11/7/5 from the QF
(`config.PENKA_STAGE_POINTS`; each fixture's tier comes from its date via
`predict.wc2026_stage`). The old Superbru mode (3 / 1.5 outcome+close / 1)
remains available everywhere via `--scoring superbru`; the default is
`config.SCORING_MODE`. The optimal pick is *not* the most likely score — see
`scoring.best_prediction`.

## Commands

```bash
pip install -e .                 # installs the `wcpred` console script
wcpred update-data               # download/refresh data/input/results.csv (run first)
scripts/update_data.sh           # refresh ALL sources (results+xG+odds) incrementally
scripts/generate_predictions.sh  # date-stamped picks + group standings (track evolution)
wcpred predict --approach odds --odds data/input/odds.csv --days 3
wcpred groups --approach odds --odds data/input/odds.csv  # MC group standings
wcpred simulate --approach odds --odds data/input/odds.csv  # full bracket → champion
wcpred backtest --tournament all      # validation: ~594 Penka pts / 290 matches
                                      # (--scoring superbru: ~295 pts)
                                      # --bridge-audit: + inter-confederation
                                      # calibration table (regional-bias test)
wcpred tune                           # hyperparameter grid search (no xG)
wcpred ratings --top 20
wcpred backtest --tournament all --static --engine bayes --bridge-audit
                                      # Bayesian Dixon-Coles (Stan); needs the
                                      # `.[bayes]` extra + a one-off CmdStan
                                      # install. static only. --engine works on
                                      # every subcommand (default `dc`). Add
                                      # --bayes-dynamic [--bayes-block halfyear]
                                      # for Phase B1 random-walk strengths;
                                      # --bayes-propagate for Phase B2 full
                                      # posterior propagation.
scripts/run_webapp.sh                 # local dashboard on :8026 (needs `.[web]` extra)
```

No test suite — `backtest --tournament all` is the regression check after
touching the model. It covers six tournaments (wc2018, euro2021, copa2021,
wc2022, euro2024, copa2024) with a rolling per-matchday re-fit (the live
`--as-of` protocol; `--static` for a single pre-tournament fit) and reports
Penka points (stage tiers mapped from each tournament's format in
`backtest.TOURNAMENTS`) plus 1X2 RPS and exact-score log-loss. Tune on
RPS/log-loss
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
  `fit` takes an optional external Elo prior (robustness-plan Phase 3;
  rejected as default, available via `ELO_PRIOR_TAU` / `--elo-tau` /
  `wcpred tune --elo`; snapshots from `scripts/fetch_elo.py` →
  `data/input/elo.csv`, resolved causally by `data.load_elo`).
- `anchor.py` — two-timescale confederation re-anchoring (robustness-plan
  Phase 2b; rejected as default, available via `CONF_ANCHOR_BETA` /
  `--anchor-beta` / `wcpred tune --anchor`).
- `model_bayes.py` + `stan/dixon_coles.stan` — `BayesianDixonColes`, a Stan
  (cmdstanpy) Dixon-Coles with a **hierarchical confederation-offset prior**:
  each team's attack/defence carries an additive per-confederation offset that
  only inter-confederation "bridge" matches can move, so intra-bloc games
  cannot drift a whole confederation (the robustness-plan Phase 4 attempt at
  the weak-anchoring limitation). Subclasses `DixonColes` — inherits
  `rates`/`matrix_from_rates`, overrides `fit` (MCMC, then adopts posterior-mean
  atk/dfn/home/rho — Phase A) and `score_matrix` (plug-in mean by default;
  full posterior propagation when opted in — Phase B2). Opt-in via
  `--engine bayes` (default `dc`, the regenerable production model). Two time
  treatments: the static default (`stan/dixon_coles.stan`) where time enters as
  the MLE decay weights (Phase A), and the dynamic
  `stan/dixon_coles_dynamic.stan` (opt-in `--bayes-dynamic` / `BAYES_DYNAMIC`,
  Phase B1) where each team's strength evolves as a random walk over
  `--bayes-block` time blocks (year/halfyear/quarter, default halfyear) and the
  most recent block is adopted — the decay weighting is then dropped. Two
  posterior treatments of the score matrix: plug-in posterior means (default)
  or full posterior propagation (opt-in `--bayes-propagate` / `BAYES_PROPAGATE`,
  Phase B2) where `score_matrix` returns the posterior mean of the per-draw
  Dixon-Coles matrices, carrying cross-bloc rating uncertainty into the
  scorelines. The between-confederation offset spread `sigma_conf` carries a
  half-normal prior whose scale is a tunable knob (`--bayes-sigma-conf` /
  `BAYES_SIGMA_CONF_SCALE`, default 0.5 = today's model; the Phase 4
  tight-`sigma_conf` sensitivity — shrink toward 0 to pin the bloc offsets near
  0). Needs the `.[bayes]` extra + CmdStan. See `docs/
  bayesian-confederation-plan.md`.
- `scoring.py` — Penka and Superbru points, Closeness Index, expected-points
  optimiser (`best_prediction(P, mode, stage)`).
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
  score matrix behind a pick. `GET /api/connectivity` (Conectividad tab)
  exposes the inter-confederation anchoring evidence behind
  `docs/known-limitations.md`: the conf×conf training-weight matrix (via
  `confederations.infer_confederations`) plus per-WC-team bridge share and
  weighted mean opponent rating.
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
  *before* it, so past results inform future picks. Fixtures are every WC
  match dated on/after it **even if since played** (the result is ignored),
  so past snapshots regenerate without leakage.
- Time-capsule odds: every `fetch_odds.py` run also writes
  `data/input/odds/odds_<YYYY-MM-DDTHHMM>.csv`. For a past `--as-of`,
  `generate_predictions.sh` (via `data.resolve_odds_path`) uses the latest
  snapshot stamped ≤ as-of + `ODDS_CUTOVER` (17:00 local — the earliest
  WC2026 kickoff is 18:00 CEST, so later same-day quotes could already
  reflect that day's matches); for today it uses the live `odds.csv`.
- `predict --extra-time`/`--shootout` resolve knockout ties (extra time at
  `EXTRA_TIME_FRACTION` of the scoring rate, then a penalty win). Both are
  **off by default** — Penka and Superbru score the 90' result, so leave them
  off for both.
- xG source is `scripts/fetch_xg.py` (FotMob public JSON API). It writes
  `xg.csv` in the `date,home_team,away_team,home_xg,away_xg` format `data.py`
  expects. FotMob has NO xG for friendlies and only ~28% of qualifiers.
- `scripts/fetch_sofascore.py` (needs `curl_cffi` to pass Cloudflare) scrapes
  SofaScore for historical 1X2 odds (`data/input/odds_history.csv`, back to
  ≥2018, single book) and supplemental xG. See `docs/sofascore.md`.
- Data-source landscape, coverage cutoffs and gotchas: `docs/data-sources.md`.
- Known modelling limitations (e.g. ratings of teams from weakly-connected
  confederations like the AFC are schedule-inflated): `docs/known-limitations.md`.
  The connectivity evidence and how to read cross-confederation comparisons
  (Argentina-vs-Spain case study): `docs/connectivity.md`.
- Robustness work on the confederation-anchoring problem is tracked in
  `docs/model-robustness-plan.md` — a LIVING document: read it before touching
  that work and update its checkboxes/status/decision-log in the same session.
  Hard rule there: the current model must stay regenerable (new knobs
  default-off, experiment outputs outside `data/predictions|groups|simulations`,
  never regenerate past snapshots with a changed model).
  The plan is CLOSED (June 2026): Phases 0-3 all rejected as defaults — even
  the external Elo anchor shares the diagnosed CONMEBOL/CONCACAF-vs-UEFA bias.
  Key facts: FotMob xG only goes back to ~mid-2022 and never covers friendlies;
  free historical odds exist only via SofaScore (single book); the model trains
  on goals/xG but never on odds (odds are a predict-time blend only — the one
  exception is the optional, default-off Elo training prior above).

Full usage, data sources and tuning notes live in `README.md`.
