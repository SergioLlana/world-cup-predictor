# Bayesian engine (`--engine bayes`)

A Stan (cmdstanpy) Dixon-Coles with a **hierarchical confederation-offset prior**
(`wcpred/model_bayes.py` + `wcpred/stan/dixon_coles.stan`). Opt-in via
`--engine bayes`; `dc` stays the default. Needs the `.[bayes]` extra and a one-off
CmdStan install, and is much slower than `dc`/`elo` (see runtimes in
[models-explained.md](models-explained.md)).

## The limitation it targets

The model's central weakness (see [known-limitations.md](known-limitations.md) and
[connectivity.md](connectivity.md)) is that **strength offsets between
confederations are weakly identified**: only the scarce "bridge" matches connect
the blocs, so AFC/CAF can drift (Australia above the USA) and cross-bloc elite
comparisons (Argentina vs Spain) carry more uncertainty than the point ratings
suggest. Five post-hoc mitigations on the MLE model were tried and rejected; they
failed because they were global post-hoc interventions or external anchors with the
same regional bias.

The Bayesian engine attacks it structurally with a **confederation offset inside
the prior**. The key property: if every South American team shifts equally relative
to Europe in the prior, *intra*-confederation matches cannot undo that shift (they
only inform relative differences within the bloc); **only the rarer bridges move the
offset.** That is exactly what the MLE fit cannot do.

## How it integrates

`BayesianDixonColes(DixonColes)` **subclasses** the production model to inherit
`rates`, `matrix_from_rates`, `_tau` and `score_matrix` without duplication. It
overrides `fit` (run MCMC, then adopt the posterior-mean atk/dfn/home/rho — a
transparent drop-in) and `score_matrix` (see *Posterior treatment* below). The
whole downstream pipeline (`predict`, `groups`, `simulate`, `--bridge-audit`,
webapp) works unchanged. The compiled `CmdStanModel` is module-cached so backtest
re-fits don't recompile.

## The Stan model

Weighted Dixon-Coles likelihood, identical in form to `model.py`: per match,
`target += w · (poisson_lpmf(hg | λ) + poisson_lpmf(ag | μ) + log(τ))`, with
`λ = exp(atk[h] + dfn[a] + home·hadv)`, `μ = exp(atk[a] + dfn[h])` and the same
four-cell low-score correction `τ`.

Non-centred hierarchical prior:

- `atk[i] = atk_conf[c(i)] + sigma_atk · atk_raw[i]`, with
  `atk_raw ~ student_t(ν, 0, 1)` — the robust t keeps legitimate outliers (e.g.
  Argentina) from being flattened. Same for `dfn`.
- **`atk_conf[C]`, `dfn_conf[C]`: the confederation offsets** —
  `~ normal(0, sigma_conf)`. This is the new piece: identified almost entirely by
  bridge matches, so with a moderate `sigma_conf` the blocs cannot shift without
  bridge evidence. Teams with no inferred confederation get a fixed-0 offset.
- `home`, `rho` (with `τ > 0` enforced), and weakly-informative hyperpriors on
  `sigma_atk, sigma_dfn, sigma_conf` (half-normal) and `ν` (gamma).
- Identifiability: sum-to-zero gauge over `atk` (replicating the MLE `atk.mean()=0`
  penalty) and over the confederation offsets.

The offset-spread prior scale is tunable: `--bayes-sigma-conf` /
`BAYES_SIGMA_CONF_SCALE` (default `0.5`). Shrinking it toward 0 pins the bloc
offsets near 0 — tested and found neutral (see *Tuning* below).

## Time treatment

Two options, selected by `--bayes-dynamic` / `BAYES_DYNAMIC`:

- **Static (default)** — `stan/dixon_coles.stan`. Time enters as the MLE decay
  weights `w`, exactly as in `dc`.
- **Dynamic random-walk** (`--bayes-dynamic`) — `stan/dixon_coles_dynamic.stan`.
  Each team's strength evolves as a random walk over time blocks
  (`atk[i,t] ~ normal(atk[i,t-1], sigma_rw)`; `--bayes-block year|halfyear|quarter`,
  default `halfyear`) and the most recent block is adopted. The random walk *is* the
  time model, so matches enter unweighted (decay weighting is dropped). Non-centred
  per team, robust Student-t initial column, per-block sum-to-zero gauge; the
  confederation offset is preserved. This is the best-performing Bayesian variant.

## Posterior treatment of the score matrix

Two options, selected by `--bayes-propagate` / `BAYES_PROPAGATE`:

- **Posterior propagation (default-on)** — `score_matrix` returns the posterior
  **mean of the per-draw Dixon-Coles matrices**: `BayesianDixonColes` keeps the
  posterior draws (`atk_draws`/`dfn_draws`/`home_draws`/`rho_draws`; in dynamic
  mode, the adopted block) and averages the matrices they produce. This carries the
  cross-bloc rating uncertainty — largest exactly on the weakly-identified bridges —
  into the scorelines, widening the distribution. It is the honest
  posterior-predictive scoreline.
- **Plug-in posterior mean** (`--no-bayes-propagate`) — plug the single
  posterior-mean rating straight into one Dixon-Coles matrix. Byte-identical to the
  inherited path.

Propagation is accuracy-neutral vs plug-in (609 vs 604 Penka pts, RPS +0.0002,
ll −0.0002 — a wash) and does **not** fix the confederation bias, but is the honest
choice, hence default-on. Because it defaults on, `--bayes-propagate` is a
`BooleanOptionalAction` and a no-op for the non-bayes engines (they ignore it). It
composes with either time treatment.

## Tuning (June 2026) — what moves the metric

Validated **static-only** (a per-matchday MCMC re-fit over six tournaments is
infeasible; `backtest()` forbids rolling for `bayes`), compared against the static
`dc`. Grid: `dynamic`, `time_block`, `sigma_conf_scale`, `propagate`.

- **The confederation prior scale and propagation are flat.** All 8 static configs
  land at RPS 0.1905–0.1907; neither `sigma_conf` (0.1→1.0) nor propagation moves
  the metric.
- **The dynamic time treatment is what helps.** Dynamic `year` configs drop to
  0.1887–0.1890 (~0.0017 better than static). Finer granularity helps with
  diminishing returns: `year` 0.18875 → `halfyear` 0.18842 → `quarter` 0.18839.

Winner: **dynamic, `halfyear`, sigma_conf 0.5, propagate off** — RPS 0.18842,
604 pts (`halfyear` over `quarter`: tied RPS, but it is the default with a more
stable prediction window and half the cost). **Bayes effectively ties `dc`** (static
`dc` winner 0.18820) — the dynamic mode is the best of the Bayesian side and matches
Dixon-Coles without beating it, at a large compute cost.

## Why it does not fix the Australia bias

An experiment with an **informative** (non-zero-mean) confederation prior — forcing
an order OFC ≪ CONCACAF/CAF ≪ UEFA from each bloc's mean Elo — was tried to beat the
Australia (AFC) inflation. It was **neutral** (RPS differences in the 4th decimal)
and moved the Australia-vs-USA head-to-head by <0.3 pp.

The mechanism: the baseline zero-mean prior already places AFC and CONCACAF low
(−0.45 / −0.76) and at nearly the same Elo, so any prior lowers them *equally* and
their relative comparison doesn't change. More importantly, **Australia's bias lives
in its individual deviation, not the bloc offset**: its total strength (+1.24) is the
AFC offset (−0.45) plus an individual deviation ≈ +1.7 (the heavy-tailed `atk_raw`
absorbing its thrashing of weak AFC opponents), which a confederation prior does not
touch. Taming it would need a *per-team* prior pulling each side toward its Elo — the
`--elo-tau` idea, already tried and rejected for sharing the same regional bias.

## Rejected variant: connectivity-weighted shrinkage

`--bayes-connect` (`BAYES_CONNECT_*`, separate `stan/dixon_coles_connect{,_dev}.stan`)
scales each team's confederation offset or own deviation by a connectivity weight
(bridge-match share, or schedule difficulty). **All variants rejected** — bridge
share is the wrong predictor and per-team shrinkage cannot reorder the gauged
ranking. Full diagnostics in [connectivity.md](connectivity.md).

## Regenerability and verification

`--engine dc` reproduces the production model byte-for-byte; the Bayesian engine is
opt-in, default-off, and never regenerates past snapshots. Experiment outputs live
outside `data/predictions|groups|simulations`.

```bash
pip install -e ".[bayes]"          # + install_cmdstan once
wcpred backtest --tournament all --static                      # dc baseline
wcpred backtest --tournament all --static --engine bayes --bridge-audit
wcpred backtest --tournament all --static --engine bayes --bayes-dynamic
wcpred ratings --top 20 --engine bayes
wcpred predict --approach odds --odds data/input/odds.csv --days 3 --engine bayes
```
