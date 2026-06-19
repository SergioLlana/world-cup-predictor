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
scripts/generate_rankings.sh     # date-stamped model rankings (--as-of, --engines;
                                 # track how team ratings evolve)
wcpred predict --approach odds --odds data/input/odds.csv --days 3
wcpred groups --approach odds --odds data/input/odds.csv  # MC group standings
wcpred simulate --approach odds --odds data/input/odds.csv  # full bracket → champion
wcpred backtest --tournament all      # validation: ~594 Penka pts / 290 matches
                                      # (--scoring superbru: ~295 pts)
                                      # --bridge-audit: + inter-confederation
                                      # calibration table (regional-bias test)
wcpred tune                           # hyperparameter grid search (no xG)
wcpred tune --elo-engine              # coordinate-tune the Elo engine
                                      # (long-term window, HA, per-conf K)
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
- `anchor.py` — two-timescale confederation re-anchoring (robustness-plan
  Phase 2b; rejected as default, available via `CONF_ANCHOR_BETA` /
  `--anchor-beta` / `wcpred tune --anchor`).
- `model_bayes.py` + `stan/dixon_coles.stan` — `BayesianDixonColes`, a Stan
  (cmdstanpy) Dixon-Coles with a **hierarchical confederation-offset prior**:
  each team's attack/defence carries an additive per-confederation offset that
  only inter-confederation "bridge" matches can move, so intra-bloc games
  cannot shift a whole confederation (the robustness-plan Phase 4 attempt at
  the weak-anchoring limitation). Subclasses `DixonColes` — inherits
  `rates`/`matrix_from_rates`, overrides `fit` (MCMC, then adopts posterior-mean
  atk/dfn/home/rho — Phase A) and `score_matrix` (full posterior propagation by
  default since 2026-06-19 — averages the per-draw Dixon-Coles matrices; set
  `BAYES_PROPAGATE=False` to recover the "plug-in" mean = plug the single
  posterior-mean rating straight into one Dixon-Coles matrix — Phase B2).
  Opt-in via
  `--engine bayes` (default `dc`, the regenerable production model). Two time
  treatments: the static default (`stan/dixon_coles.stan`) where time enters as
  the MLE decay weights (Phase A), and the dynamic
  `stan/dixon_coles_dynamic.stan` (opt-in `--bayes-dynamic` / `BAYES_DYNAMIC`,
  Phase B1) where each team's strength evolves as a random walk over
  `--bayes-block` time blocks (year/halfyear/quarter, default halfyear) and the
  most recent block is adopted — the decay weighting is then dropped. Two
  posterior treatments of the score matrix: full posterior propagation
  (`--bayes-propagate` / `BAYES_PROPAGATE`, **default-on since 2026-06-19**,
  Phase B2) where `score_matrix` returns the posterior mean of the per-draw
  Dixon-Coles matrices, carrying cross-bloc rating uncertainty into the
  scorelines, or the plug-in posterior mean (`BAYES_PROPAGATE=False`). Propagation
  is accuracy-neutral vs plug-in (609 vs 604 Penka pts, RPS +0.0002, ll −0.0002 —
  a wash) and does NOT fix the confederation bias, but is the honest
  posterior-predictive scoreline. The between-confederation offset spread `sigma_conf` carries a
  half-normal prior whose scale is a tunable parameter (`--bayes-sigma-conf` /
  `BAYES_SIGMA_CONF_SCALE`, default 0.5 = today's model; the Phase 4
  tight-`sigma_conf` sensitivity — shrink toward 0 to pin the bloc offsets near
  0). Phase C (`--bayes-connect`, `BAYES_CONNECT_SHRINK/_REF/_MODE/_BY/_OPP_REF`,
  separate `stan/dixon_coles_connect{,_dev}.stan`) scales each team's
  confederation offset (`mode=offset`, A) or own deviation (`mode=deviation`, B)
  by a connectivity weight — driven by bridge-match share (`by=bridge`,
  `confederations.bridge_share`) or schedule difficulty (`by=opp`, Phase C',
  `confederations.opponent_rating` from a pre-fit dc). All REJECTED (2026-06-16):
  Australia is schedule-difficulty inflated, not connectivity-starved, and the
  per-team shrinkage can't reorder the (relative, sum-zero-gauged) ranking even
  with the right predictor (`opp`) — base 605 > C' 593 > B 581 Penka pts; kept
  default-off. Needs the `.[bayes]` extra + CmdStan. See `docs/
  bayesian-confederation-plan.md` and `docs/connectivity-shrinkage-experiment.md`.
- `model_elo.py` — `EloDixonColes`, an Elo engine (opt-in
  `--engine elo`; default stays `dc`). Trains its OWN Elo on `results.csv` via
  the eloratings.net rule (`Rn = Ro + K·(W − We)`, K by tournament tier
  60/50/40/30/20 × goal-difference multiplier, home advantage `ELO_HA`=100,
  `We = 1/(10^(−dr/400)+1)`). Two extensions (default-off-
  equivalent): a per-confederation K multiplier (`ELO_CONF_K`, each team updates
  by its own bloc's K — a parameter on the weak-connectivity bias) and a long-term
  (median over `ELO_LONGTERM_YEARS`=10) Elo covariate (EL PAÍS "trayectoria histórica"
  regression-to-the-mean). Subclasses `DixonColes` — overrides `fit` (Elo
  iteration over the raw history from `ELO_TRAIN_START`=2006, then a 4-parameter
  GAM-Poisson + Dixon-Coles calibration `log λ = β0 + β_h·home + β_e·Δelo +
  β_lt·Δelo_lt` on the decay-weighted training frame) and `rates`; inherits
  `matrix_from_rates`/`score_matrix`. Ratings ~594 dc / ~587 elo Penka pts on
  `backtest --tournament all`. Single data source (`results.csv`), nothing
  scraped. Tunable via `wcpred tune --elo-engine` (`backtest.tune_elo`:
  RPS-driven coordinate search over `ELO_LONGTERM_YEARS`/`ELO_HA` then the
  per-confederation K). Defaults stay at the published-rule values (1.0 K) per
  the regenerability rule — adopt a tuned config only after a rolling
  re-validation. See `docs/elo-engine-plan.md`, the tuning run results in
  `docs/engine-tuning-2026-06.md` (§Motor `elo`) and the timing + decision
  rationale in `docs/elo-engine-tuning.md`.
- `scoring.py` — Penka and Superbru points, Closeness Index, and the scoreline
  pick step (`select_prediction(P, mode, stage, strategy)`, `PICK_STRATEGIES`).
  Two strategies: `ev` (default, `best_prediction` — `argmax E[pts]`, the
  regenerable production pick) and `outcome` (strategy C, `best_prediction_outcome`
  — most likely 1X2 outcome then most likely scoreline within it; +8% Penka on
  the backtest, opt-in via `--pick-strategy outcome`). It's a post-probability
  step, independent of the model/tuning. See `docs/pick-strategy.md`.
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
  `scripts/experiments/build_thirds_table.py`.
- `backtest.py` — six past tournaments, rolling re-fit, Superbru/RPS/log-loss
  metrics, and the `tune` hyperparameter grid search.
- `cli.py` — argparse entry point (`main`); subcommands map to `cmd_*`.

## Web app (`webapp/`)

- `server.py` — FastAPI (install `.[web]`; run `scripts/run_webapp.sh`, port
  8026). JSON API over the date-stamped CSVs in `data/` (re-read per request,
  no cache) plus `POST /api/refresh` which runs `generate_predictions.sh
  --refresh` for both approaches (and the requested `--engines`), then
  `generate_rankings.sh` once for those engines, in a background thread (a
  multi-step run keeps `running` true until the last step — `_run_proc` no
  longer flips it). Every data endpoint takes `approach` (odds/history) **and** `engine`
  (dc/elo/bayes, **default elo** — `DEFAULT_ENGINE`) query params — the CSV
  filename carries an `_<engine>` segment (`_FILE_RE`), so the UI's engine picker
  selects which engine's snapshots the dashboard shows. The scoreline pick
  strategy (`ev`/`outcome`, default `outcome` — `DEFAULT_STRATEGY`/`STRATEGIES`,
  exposed in `/api/meta`) is **not** a filename segment: every predictions CSV
  carries both `pick`/`expected_points` (ev) and `pick_outcome`/
  `expected_points_outcome` (strategy C) columns, so the UI's strategy toggle
  just selects the column client-side (no reload). Owns the team →
  flag-code/Spanish-name map (`TEAMS`); odds↔fixture matching reuses
  `predict._norm_team` and tolerates swapped home/away (host MD3 quirk).
  `GET /api/matrix` re-fits the requested engine as of the snapshot in force on
  the match date (lru_cached per as-of + results.csv mtime + engine) to serve
  the full score matrix behind a pick (its `strategy` param picks which scoreline
  to highlight; bayes needs CmdStan and is slow). `GET /api/connectivity` (Conectividad tab)
  exposes the inter-confederation anchoring evidence behind
  `docs/known-limitations.md`: the conf×conf training-weight matrix (via
  `confederations.infer_confederations`) plus per-WC-team bridge share and
  weighted mean opponent rating. The Rankings tab is fed by two endpoints:
  `GET /api/rankings/history?engine=` reads the date-stamped
  `data/rankings/ratings_<engine>_<date>.csv` snapshots (from
  `generate_rankings.sh`; `_RANK_RE`, no approach segment) so the tab can show
  the latest table plus an evolution chart; `GET /api/rankings?engine=` is the
  live fallback used only when no snapshot exists yet (re-fits the engine as of
  today, lru_cached per as-of + results.csv mtime + engine) and returns the 48
  WC teams' attack/defence coefficients, overall rating (atk − dfn),
  confederation, weighted mean opponent rating (schedule difficulty) and — for
  the Elo engine only — its current Elo (`has_elo`). Both rank by Elo for `elo`,
  by overall rating otherwise. (`_records` makes the snapshot CSV NaN-safe —
  Starlette's encoder rejects NaN.)
- `static/` — vanilla JS frontend (`app.js`), no external deps; charts are
  hand-rolled SVG; `flags/` holds the 48 country SVGs (flagcdn). The odds
  toggle switches between the `odds`/`history` CSV variants and the engine
  picker (header `<select>`) between `dc`/`elo`/`bayes` (default `elo`); the
  in-memory cache is keyed by `<approach>|<engine>`. A second toggle ("Marcador
  más probable", default on = strategy C) flips `state.strategy` between
  `ev`/`outcome`; it only re-renders (no reload) because `pickOf` just reads the
  `pick` vs `pick_outcome` column already in the loaded picks (old snapshots
  without the outcome column fall back to `pick`). The calendar shows each match
  the prediction from the latest snapshot ≤ its date. The Rankings tab (cached per engine) is
  snapshot-driven: it shows the latest `ratings` snapshot's table plus a
  hand-rolled SVG evolution chart (metric picker: rating / Elo / rank / opponent
  difficulty; rank uses an inverted axis) over all snapshots — independent of
  the odds toggle and the global day picker.

## Conventions

- Generated files live under `data/`, never the project root:
  inputs in `data/input/` (`results.csv`/`odds.csv`/`xg.csv`),
  `predict --out` in `data/predictions/`, `groups --out` in `data/groups/`,
  `simulate --out` in `data/simulations/`, `ratings --out` in `data/rankings/`.
  Paths are set in `config.py` (`INPUT_DIR`/`PREDICTIONS_DIR`/`GROUPS_DIR`/
  `SIM_DIR`/`RANKINGS_DIR`, `RESULTS_PATH`); writers `os.makedirs` their target, and
  `cli.resolve_out` routes a bare `--out` filename into the right folder.
- Team names must match the martj42 dataset exactly (e.g. `United States`,
  `South Korea`, `Czech Republic`, `Ivory Coast`, `Turkey`).
- Score matrices are `P[home_goals, away_goals]` over a `0..MAX_GOALS` grid.
- `--as-of` controls the train/predict cutoff — training uses only matches
  *before* it, so past results inform future picks. Fixtures are every WC
  match dated on/after it **even if since played** (the result is ignored),
  so past snapshots regenerate without leakage.
- Frozen-in-time odds: every `fetch_odds.py` run also writes
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
- Data-source landscape, coverage cutoffs and gotchas: `docs/data-sources.md`.
- Known modelling limitations (e.g. ratings of teams from weakly-connected
  confederations like the AFC are schedule-inflated): `docs/known-limitations.md`.
  The connectivity evidence and how to read cross-confederation comparisons
  (Argentina-vs-Spain case study): `docs/connectivity.md`.
- Robustness work on the confederation-anchoring problem is tracked in
  `docs/model-robustness-plan.md` — a LIVING document: read it before touching
  that work and update its checkboxes/status/decision-log in the same session.
  Hard rule there: the current model must stay regenerable (new parameters
  default-off, experiment outputs outside `data/predictions|groups|simulations`,
  never regenerate past snapshots with a changed model).
  The plan is CLOSED (June 2026): Phases 0-3 all rejected as defaults — even
  the external Elo anchor shares the diagnosed CONMEBOL/CONCACAF-vs-UEFA bias.
  Key facts: FotMob xG only goes back to ~mid-2022 and never covers friendlies;
  the model trains on goals/xG only — odds are a predict-time blend, never a
  training input.

Full usage, data sources and tuning notes live in `README.md`.
