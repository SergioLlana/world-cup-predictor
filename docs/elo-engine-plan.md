# Plan: in-house Elo engine (`--engine elo`)

## Context

`wcpred` predicts WC2026 scorelines with two interchangeable engines selected by
`--engine`: `dc` (Dixon-Coles MLE, the regenerable default) and `bayes`
(Stan hierarchical model). This adds a **third, additive engine** that trains its
**own Elo in-house** (no scraping — the existing `--elo-tau` path scrapes
eloratings.net and was rejected as a default), inspired by two references:

- **eloratings.net:** the Elo update rule `Rn = Ro + K·(W − We)`, with K by
  tournament type (60/50/40/30/20), a goal-difference multiplier, home advantage
  `+100` to `dr`, and `We = 1/(10^(−dr/400)+1)`.
- **EL PAÍS model:** a *current* Elo plus a *long-term* (10-year median) Elo as a
  separate "pedigree" covariate, both feeding a GAM-Poisson + Dixon-Coles goal
  model.

Decisions: long-term Elo is a **separate covariate** (not a shrinkage blend);
window **10 years** (configurable). Per-confederation K: **per-team
own-confederation multiplier × tournament-type K**, defaulting all multipliers to
`1.0` so the engine reduces *exactly* to eloratings.net (the methodology EL PAÍS
itself consumes). The per-conf K is an extension — a tunable lever against the
documented confederation-bias problem (`docs/known-limitations.md`).

Hard constraint (regenerability rule): the current `dc`/`bayes` engines stay
byte-identical; this is purely additive, default-off, and `dc` remains the
default everywhere.

## Data source

Single input: `data/input/results.csv` (martj42 dataset, refreshed by
`wcpred update-data`) — the same file the rest of the pipeline uses. **Nothing is
scraped**; `data/input/elo.csv` (the external `--elo-tau` snapshots) is NOT used
and that path stays untouched. The Elo iteration reads the raw `df` from
`data.load_results` (tournament string → K tier, `neutral` → home advantage,
integer goals → `W` and the goal-diff multiplier); the goal-model calibration
uses `prepare_training(df, as_of)`; confederations come from
`infer_confederations` over the same file. In-house Elo, not downloaded.

## Engine contract (verified)

A model must expose `self.idx` (team→index), `self.atk`, `self.dfn`,
`self.home`, `self.rho`, and `score_matrix(home, away, home_side)` →
`P[home_goals, away_goals]`. `DixonColes.score_matrix` calls
`matrix_from_rates(*self.rates(...))`. So subclassing `DixonColes` and overriding
only `fit` + `rates` (and setting the attributes) makes the whole pipeline
(`predict`, `groups`, `simulate`, `odds`, webapp `/api/matrix`) work unchanged —
exactly how `BayesianDixonColes` integrates (`wcpred/model_bayes.py`).

## 1. New file `wcpred/model_elo.py`

Drop-in `DixonColes` subclass; only `fit`/`rates` overridden; defaults reproduce
eloratings.net; the per-conf K and long-term covariate are the two extensions;
Elo iterates over the **full raw history** while the goal model calibrates on the
**decay-weighted** `prepare_training` frame.

**`tournament_k(tournament: str) -> float`** — base K from the martj42
`tournament` string, driven by config (`ELO_K_TIERS`, `ELO_K_FINALS`):
`"Friendly"` → 20; `"FIFA World Cup"` → 60; any name ending `"qualification"` →
40; continental/major-intercontinental finals (Euro, Copa América, AFCON, Asian
Cup, Gold Cup/CONCACAF Championship, OFC Nations Cup, Confederations Cup) → 50;
everything else → 30.

**`compute_elo(matches, as_of, ha, conf_k, base, longterm_years)`** —
chronological eloratings iteration over played matches dated `< as_of`. Returns
`ratings` (current), `longterm` (median post-match Elo over trailing
`longterm_years`), `n_matches`. Per match:
`dr = (Rh − Ra) + (ha if not neutral else 0)`; `We = 1/(10^(−dr/400)+1)`;
`W ∈ {1,0.5,0}` from the integer score sign;
`g = gd_mult(|hg−ag|)` (`1` if ≤1, `1.5` if 2, `1.75` if 3, `1.75+(N−3)/8` if ≥4);
`K = tournament_k(t)`; per-side update
`R[s] += K·g·conf_k.get(conf[s],1.0)·(W_s − We_s)` (the two sides may move by
different amounts). `conf` from `infer_confederations(matches)` on the same slice.

**`class EloDixonColes(DixonColes)`** —
`fit(self, m, df=None, as_of=None, ha=None, conf_k=None, longterm_years=None, elo_train_start=None, elo=None, elo_tau=0.0)`:
1. `raw = df[(date >= elo_train_start) & (date < as_of)]` (played);
   `confs = infer_confederations(raw)`.
2. `ratings, longterm, n_matches = compute_elo(raw, as_of, ...)`.
3. `self.idx` from the calibration frame `m` (MIN_MATCHES-filtered universe).
   Store `self.elo_cur`, `self.elo_lt`, `self.elo_n` (fallback `ELO_BASE`/current
   for teams absent from `raw`).
4. **Calibration** (4-param weighted Poisson MLE on `m`): with normalised
   `de = (elo_cur[h]−elo_cur[a])/100`, `dl = (elo_lt[h]−elo_lt[a])/100`,
   `log lam = β0 + β_h·hh + β_e·de + β_lt·dl`,
   `log mu = β0 − β_e·de − β_lt·dl`. Fit `β0,β_h,β_e,β_lt` via
   `scipy.optimize.minimize(L-BFGS-B, jac analytic)`, then the rho grid search
   exactly as `model.py:66-75`.
5. Display ratings for `wcpred ratings`: `self.home = β_h`;
   `s_i = β_e·(elo_cur−1500)/100 + β_lt·(elo_lt−1500)/100`;
   `self.atk = β0/2 + s/2`, `self.dfn = β0/2 − s/2` (so `atk−dfn = s`).
   `elo`/`elo_tau` accepted but ignored (this engine *is* the Elo anchor).

`rates()` override computes `lam`/`mu` from the stored Elo arrays + betas (home
boost honours `home_side ∈ {"home","away",None}`); inherited
`matrix_from_rates`/`_tau`/`score_matrix` unchanged. Raise the same `KeyError`
message as `DixonColes.rates`.

## 2. Config block in `wcpred/config.py`

New `# --- Elo engine (--engine elo) ---` block: `ELO_HA=100.0`,
`ELO_BASE=1500.0`, `ELO_TRAIN_START="2006-01-01"`, `ELO_LONGTERM_YEARS=10`,
`ELO_CONF_K={UEFA..OFC: 1.0}`, `ELO_K_TIERS` (60/50/40/30/20), `ELO_K_FINALS`.
All default to the published rule. No change to `tune()` (stays `dc`-only).

## 3. Wiring

- `cli.common()`: add `"elo"` to `--engine` choices + help.
- `cli.build_model()`: `elif engine=="elo"` → `EloDixonColes().fit(train, df=df,
  as_of=args.as_of)` + status print; reject bayes-only and
  `--elo-tau`/`--anchor-beta` flags under `elo`.
- `backtest.backtest()`: `elif engine=="elo": EloDixonColes().fit(tm, df=df,
  as_of=cutoff)` (no `rolling=False` constraint); early guard rejecting
  `dynamic/propagate/elo_tau/anchor_beta` under `elo`. `cmd_backtest` already
  forwards `engine=args.engine`.

Causality: Elo slice is `df.date < as_of/cutoff`; conf inference and the 10y
median window both use that causal slice.

## Risks
- **xG floats**: Elo iteration uses raw integer scores (clean `W`); only the rho
  grid sees the (optionally xG-blended) calibration frame — same no-op behaviour
  as `DixonColes`. Recommend `--engine elo` without xG, as in prod.
- **Provisional (<30-match) teams** sit near the 1500 seed; `self.elo_n` exposed.
- **Non-unit per-conf K breaks Elo zero-sum** — expected when enabled; defaults
  (1.0) preserve it.
- **Teams absent from the raw Elo slice**: `.get(..., ELO_BASE)` fallbacks.

## Verification
```bash
pip install -e .
wcpred ratings --engine elo --top 20
wcpred predict --engine elo --as-of 2026-06-14 --days 3
wcpred predict --engine elo --approach odds --odds data/input/odds.csv --days 3
wcpred backtest --tournament all --engine elo        # pooled Penka vs dc ~594
wcpred backtest --tournament all                     # dc baseline (unchanged)
wcpred backtest --tournament all --engine elo --bridge-audit
```
Pass: engine runs end-to-end through every subcommand; `dc`/`bayes` numbers
byte-identical; RPS/log-loss/Penka in the `dc` ballpark.
