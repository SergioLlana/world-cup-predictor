# Elo engine (`--engine elo`)

A third, additive engine (`wcpred/model_elo.py`) alongside the default `dc`
(Dixon-Coles MLE) and `bayes` (Stan). It trains its **own Elo** on the match
history and calibrates a Dixon-Coles goal model on top. Opt-in via `--engine elo`;
`dc` stays the default everywhere and `dc`/`bayes` are byte-identical with or
without this engine present.

It is inspired by two references:

- **eloratings.net:** the update rule `Rn = Ro + K·(W − We)`, with K by tournament
  type (60/50/40/30/20), a goal-difference multiplier, home advantage `+100` to
  `dr`, and `We = 1/(10^(−dr/400)+1)`.
- **EL PAÍS model:** a *current* Elo plus a *long-term* (10-year median) Elo as a
  separate "historical trajectory" covariate, both feeding a GAM-Poisson +
  Dixon-Coles goal model.

## Data source

Single input: `data/input/results.csv` (martj42 dataset, refreshed by
`wcpred update-data`) — the same file the rest of the pipeline uses. **Nothing is
scraped.** The Elo iteration reads the raw `df` (tournament string → K tier,
`neutral` → home advantage, integer goals → `W` and the goal-diff multiplier); the
goal-model calibration uses `prepare_training(df, as_of)`; confederations come from
`infer_confederations` over the same file.

## How it integrates

A model must expose `self.idx` (team→index), `self.atk`, `self.dfn`, `self.home`,
`self.rho`, and `score_matrix(home, away, home_side)` → `P[home_goals, away_goals]`.
`EloDixonColes` subclasses `DixonColes` and overrides only `fit` + `rates` (setting
those attributes), so the whole pipeline (`predict`, `groups`, `simulate`, `odds`,
webapp `/api/matrix`) works unchanged — the same way `BayesianDixonColes`
integrates.

## How it works (`model_elo.py`)

The Elo iterates over the **full raw history** (from `ELO_TRAIN_START`, 2006) while
the goal model calibrates on the **decay-weighted** `prepare_training` frame.

**`tournament_k(tournament)`** — base K from the martj42 `tournament` string,
driven by config (`ELO_K_TIERS`, `ELO_K_FINALS`): `"Friendly"` → 20;
`"FIFA World Cup"` → 60; names ending `"qualification"` → 40;
continental/major-intercontinental finals (Euro, Copa América, AFCON, Asian Cup,
Gold Cup/CONCACAF Championship, OFC Nations Cup, Confederations Cup) → 50;
everything else → 30.

**`compute_elo(...)`** — chronological iteration over played matches dated
`< as_of`. Returns `ratings` (current), `longterm` (median post-match Elo over the
trailing `longterm_years`), `n_matches`. Per match:
`dr = (Rh − Ra) + (ha if not neutral else 0)`; `We = 1/(10^(−dr/400)+1)`;
`W ∈ {1,0.5,0}` from the integer-score sign; `g = gd_mult(|hg−ag|)`
(`1` if ≤1, `1.5` if 2, `1.75` if 3, `1.75+(N−3)/8` if ≥4); `K = tournament_k(t)`;
per-side update `R[s] += K·g·conf_k.get(conf[s],1.0)·(W_s − We_s)` (the two sides
may move by different amounts).

**`class EloDixonColes(DixonColes).fit`** —
1. Slice the raw history (`elo_train_start ≤ date < as_of`, played) and infer
   confederations on that causal slice.
2. `compute_elo(...)` → current + long-term Elo per team.
3. `self.idx` from the `MIN_MATCHES`-filtered calibration frame; store
   `self.elo_cur`, `self.elo_lt`, `self.elo_n` (fallback `ELO_BASE` for teams
   absent from the raw slice).
4. **Calibration** — a 4-parameter weighted Poisson MLE on the training frame:
   with normalised `de = (elo_cur[h]−elo_cur[a])/100` and
   `dl = (elo_lt[h]−elo_lt[a])/100`,
   `log λ = β0 + β_h·home + β_e·de + β_lt·dl`,
   `log μ = β0 − β_e·de − β_lt·dl`. Fit `β0,β_h,β_e,β_lt` (L-BFGS-B, analytic
   Jacobian), then the rho grid search exactly as `model.py`.
5. Display ratings for `wcpred ratings`: `self.home = β_h`;
   `s = β_e·(elo_cur−1500)/100 + β_lt·(elo_lt−1500)/100`;
   `self.atk = β0/2 + s/2`, `self.dfn = β0/2 − s/2` (so `atk−dfn = s`).

`rates()` computes `λ`/`μ` from the stored Elo arrays + betas (the home boost
honours `home_side ∈ {"home","away",None}`); inherited `matrix_from_rates`/`_tau`/
`score_matrix` are unchanged.

## Two extensions (default-off-equivalent)

Both default to the published rule, so the engine reduces *exactly* to
eloratings.net out of the box:

- **Long-term Elo covariate** (`ELO_LONGTERM_YEARS`, 10) — a separate
  regression-to-the-mean term, not a shrinkage blend.
- **Per-confederation K** (`ELO_CONF_K`, all `1.0`) — each team updates by its own
  bloc's K. A direct parameter on the documented confederation-bias problem (see
  [known-limitations.md](known-limitations.md)); non-unit K breaks Elo's zero-sum
  property, which is the intended effect.

## Config (`config.py`)

The `# --- Elo engine ---` block: `ELO_HA=100.0`, `ELO_BASE=1500.0`,
`ELO_TRAIN_START="2006-01-01"`, `ELO_LONGTERM_YEARS=10`,
`ELO_CONF_K={UEFA..OFC: 1.0}`, `ELO_K_TIERS` (60/50/40/30/20), `ELO_K_FINALS`. All
default to the published rule; `tune()` stays `dc`-only (Elo tuning is
`wcpred tune --elo-engine`).

## Tuning (June 2026) and the decision

`backtest.tune_elo` (run via `wcpred tune --elo-engine`, ~107 s) does coordinate
search on RPS (points as tiebreak): a scalar grid over
`ELO_LONGTERM_YEARS ∈ {5,8,10,12,15}` × `ELO_HA ∈ {50,75,100,125}` at K = 1.0,
then coordinate descent on the per-confederation K over `{0.5,…,2.0}`. Tuned
static, then re-validated with the rolling per-matchday re-fit (the live `--as-of`
protocol) over the six backtest tournaments.

Rolling winner: `longterm_years=15, ha=50,
conf_k={UEFA:2.0, CONMEBOL:1.5, CONCACAF:0.5, CAF:2.0, AFC:2.0, OFC:2.0}` —
607 pts / RPS 0.1934 (+20 pts, −0.0016 RPS vs the default). The gain decomposes:

- scalar tweak (15y / HA=50): **+6 pts**;
- **CONCACAF K=0.5** alone: **+10 pts** — the one interpretable per-bloc result
  (damping a weakly-connected, schedule-inflated confederation);
- pushing the other five blocs to the grid **ceiling (2.0)**: only +4 pts and
  ~0 RPS — a global-K / boundary-overfit effect, not a robust finding.

A **parsimonious pick** (`15y, HA=50, CONCACAF=0.5, others=1.0` → 603 pts /
RPS 0.1935) captures almost all the generalising gain without the ceiling overfit.

**Decision — the default stays at the published eloratings rule** (`ELO_HA=100`,
`ELO_LONGTERM_YEARS=10`, all `ELO_CONF_K=1.0`): the gains are real but modest and
partly at a grid boundary, so they do not warrant changing the published defaults
(regenerability rule). A tuned config is opted into explicitly. The tuned Elo still
lands **behind the `dc` default** in rolling RPS (0.1934 vs dc's 0.1890), so it is
additive, not a replacement.

A principled follow-up would add an explicit *global* K-scale parameter (separate
from the *relative* per-confederation multipliers) and re-tune, to absorb the
global-K effect cleanly and isolate the genuine per-bloc signal (CONCACAF damping)
instead of four blocs piling onto the grid ceiling.

## Verification

```bash
pip install -e .
wcpred ratings --engine elo --top 20
wcpred predict --engine elo --approach odds --odds data/input/odds.csv --days 3
wcpred backtest --tournament all --engine elo              # pooled Penka vs dc ~594
wcpred backtest --tournament all                           # dc baseline (unchanged)
wcpred backtest --tournament all --engine elo --bridge-audit
```
