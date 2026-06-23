# How the model works

An end-to-end walkthrough of `wcpred`, showing where each of the three data
sources (results, xG, odds) enters the pipeline.

## The core: Dixon-Coles model (`model.py`)

A weighted bivariate Poisson model. Each team has two latent parameters:

- **`atk[i]`** — attacking strength
- **`dfn[i]`** — defensive weakness (higher = concedes more)

plus a global home-advantage term **`home`**. The expected goals of a match are:

```
λ (home) = exp(atk_home + dfn_away + home·hadv)
μ (away) = exp(atk_away + dfn_home)
```

`fit` maximises the weighted Poisson log-likelihood via L-BFGS-B (analytic
gradient, plus an identifiability penalty fixing the mean of `atk`). It then
estimates **`rho`** by grid search: the Dixon-Coles correction that re-weights
the probabilities of low scores (0-0, 1-0, 0-1, 1-1), where pure Poisson fails.
`_tau` applies that correction.

The output for a match is a **score matrix** `P[home_goals, away_goals]` over the
`0..8` grid (`score_matrix` / `matrix_from_rates`).

## How the three sources enter

### 1. Results — train the model (`data.prepare_training`)

The only source that **trains**. Downloaded from martj42 (`update-data`) and
filtered to matches played between `TRAIN_START` (2015) and the `as_of` cutoff.
Each match gets a weight `w`:

- **Time decay**: `w = exp(-ln2/730 · days)` → weight halves every 2 years
  (`HALF_LIFE_DAYS`).
- **Friendlies at full weight**: `FRIENDLY_WEIGHT = 1.0`. Down-weighting them
  hurt every metric in the June 2026 validation grid.
- Teams with fewer than `MIN_MATCHES` (10) matches are dropped.

That `w` multiplies the likelihood in `fit`.

### 2. xG — blended *inside* training (`prepare_training`, optional)

If you pass `--xg`, goals are replaced by **effective goals** before fitting:

```
g_eff = α·goals + (1-α)·xG     with α = XG_ALPHA = 0.6
```

i.e. 60% real goals / 40% xG, only on matches that have xG (`how="left"`; the
rest keep their real goals). This smooths finishing variance. It still feeds the
same Poisson `fit` — the model **never sees xG as a separate variable**, only
"corrected" goals. (xG does not improve Penka/Superbru points; see
[known-limitations.md](known-limitations.md).)

### 3. Odds — blended at *predict time*, never trained (`odds.py` + `predict.predict_match`)

Odds do not touch the trained model; they combine in when predicting each match:

1. `to_prob` converts American or decimal odds (autodetected by `|value|≥100`)
   to implied probability.
2. `devig` removes the bookmaker margin by normalising 1X2 to sum to 1.
3. `market_matrix` **recalibrates `λ` and `μ`**: it starts from the model's rates
   and optimises them (Nelder-Mead) until the Dixon-Coles matrix reproduces the
   market 1X2 probabilities. Key point: it inherits the *shape* (rho, scoreline
   spread) from the model but the *outcome* from the market.
4. The two matrices are mixed:

   ```python
   P = 1.0·P_market + 0.0·P_model     # ODDS_WEIGHT = 1.0 (default)
   ```

By default the 1X2 marginals are **100% market**, because odds carry information
the model lacks (injuries, suspensions and rotations, priced in by the minute).
The model only supplies the *shape* of the scoreline distribution within each
outcome (odds carry no scoreline info). With `--odds-weight < 1.0` the model's
1X2 is reintroduced (e.g. `0.80` ⇒ `0.80·market + 0.20·model`).

## The final step: the optimal pick (`scoring.best_prediction`)

This is the non-obvious part of the project. Given the matrix `P`, the model does
**not pick the most likely scoreline** — it picks the one that **maximises the
expected points of the game mode** (Penka by default; `--scoring superbru` for the
old one):

```
EP(scoreline) = Σ  P[th,ta] · points(scoreline, (th,ta))
```

Penka scale (exact / goal-difference-or-draw / winner), with points growing by
stage: 5/3/2 in the group stage, 8/5/3 in the R32 and R16, 11/7/5 from the
quarter-finals on (`config.PENKA_STAGE_POINTS`; each match's stage comes from its
date, `predict.wc2026_stage`). Superbru scale: 3 exact / 1.5 correct-sign-and-close
/ 1 correct-sign / 0, with "closeness" measured by the Closeness Index
(`|ΔGoalDiff| + |ΔTotalGoals|/2 ≤ 1.5`). In both cases the optimal pick leans
toward "safe" scorelines like 1-0 or 2-1: they cover the space of also-scoring
results better, even when individually less likely than the modal score.

`best_prediction` is vectorised: the scale's points matrix is built once
(`points_matrix`, cached by (grid, mode, stage)) and the computation reduces to
`points · P` for all matches. Turning the matrix into a single pick is a separate
step — see [pick-strategy.md](pick-strategy.md) for the `ev` vs `outcome`
strategies.

## Optional: extra time and penalties (knockouts)

Penka and Superbru score the 90' result, so **by default** the model ignores extra
time. For pools that score the *final* knockout result there are two options (both
off by default):

- `--extra-time` (`scoring.resolve_extra_time`): each regulation draw is split by
  the extra-time goal distribution, a Dixon-Coles matrix with rates at
  `EXTRA_TIME_FRACTION = 1/3` (30' vs 90').
- `--shootout` (`scoring.resolve_shootout`, implies `--extra-time`): mass still
  level after extra time is resolved as a penalty shootout, turning it into a
  one-goal win (50/50 home/away).

Do not use either with the Penka or Superbru scales.

## Monte Carlo simulations: `groups` and `simulate`

Both use the same per-match matrix `P`, but the opposite way to `predict`: instead
of choosing the scoreline that maximises pool points, they **sample** scorelines
from `P`, so simulated outcomes follow the realistic distribution. Matches already
played enter with their real result, so both commands also run mid-tournament.

- `groups` (`groups.py`): simulates each group many times and reports the
  probability of each final position. Ranking is by points, goal difference and
  goals for; remaining ties are sampled (head-to-head is not modelled). Group
  labels come from the official draw (`tournament.OFFICIAL_GROUPS`).
- `simulate` (`tournament.py`): extends that to the full tournament — the 8 best
  thirds (official FIFA table in `thirds_table.py`), the Round-of-32 bracket
  through the final, and extra-time/penalty tie-breaks. Knockouts are played at a
  neutral venue (see [known-limitations.md](known-limitations.md)). Returns, per
  team, the probability of winning the group, clearing each round, and being
  champion.

## Flow summary

```
results.csv ─┐
xG (α blend)─┴─→ prepare_training ──→ DixonColes.fit ──→ matrix P_model
                                                              │
odds ──→ devig ──→ market_matrix ──→ P_market ──┐             │
                                                └─ 1.0·mkt (def.; --odds-weight)
                                                              │
                                                  best_prediction (max EP Penka)
                                                              │
                                                          pick + EP
```

## Engines

The pipeline above describes the default **`dc`** engine (Dixon-Coles MLE, the
regenerable production model). Two further engines are selectable with `--engine`
and plug into the exact same pipeline by subclassing `DixonColes`:

- **`elo`** — trains its own Elo (eloratings.net rule) and calibrates a
  Dixon-Coles goal model on top. See [elo-engine.md](elo-engine.md).
- **`bayes`** — a Stan hierarchical Dixon-Coles with a per-confederation offset
  prior. Needs the `.[bayes]` extra + CmdStan and is much slower. See
  [bayesian-engine.md](bayesian-engine.md).

`dc` is the CLI default; the web app defaults to `elo`. On the six-tournament
backtest the three engines land in the same ballpark (~594 dc / ~587 elo Penka
points; dynamic bayes ties dc without beating it).

## Engine runtimes

How long each `scripts/generate_predictions.sh --engines …` run takes, per engine
and per sub-command, on the dev machine (`--approach odds`, default Monte-Carlo
counts: `groups` 1,000,000 sims, `simulate` 100,000 sims):

| sub-command | dc | elo | bayes |
|---|---:|---:|---:|
| `predict`  | 3 | 3 | 152 |
| `groups`   | 9 | 8 | 156 |
| `simulate` | 3 | 3 | 147 |
| **total (3 outputs)** | **15 s** | **14 s** | **455 s (~7.6 min)** |

- **`dc` and `elo` cost the same** (seconds); the model fit is instant, and the
  priciest sub-command is `groups` (1M-sim Monte Carlo).
- **`bayes` dominates the clock**: ~150 s per sub-command, driven by the **MCMC
  fit** (4 chains via CmdStan), redone independently for each sub-command. Limit
  it to the outputs you need (e.g. `--predict-only`) to scale it down.
- **Adding `dc` to `elo,bayes` is effectively free** (+15 s over ~8 min).

A full daily run with `--engines dc,elo,bayes` and all three outputs is ~8 min per
approach/date pair (~16 min if you run both `odds` and `history`).
