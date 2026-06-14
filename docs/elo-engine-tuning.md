# Elo engine tuning results

Hyperparameter search for the in-house Elo engine (`--engine elo`,
`wcpred/model_elo.py`). Reproduce with:

```bash
wcpred tune --elo-engine     # static coordinate search + rolling re-validation
```

## Method

The Elo engine has three tunable knobs (`config.py`): the long-term covariate
window `ELO_LONGTERM_YEARS`, the home advantage `ELO_HA`, and the
per-confederation K multiplier `ELO_CONF_K` (a 6-entry dict). A full grid over
the conf-K is infeasible, so `backtest.tune_elo` does **coordinate search**,
optimising pooled **RPS** (low variance; points are too noisy on ~290 matches),
points as the tiebreak — the same protocol as the main `tune`:

1. **scalar grid** over `ELO_LONGTERM_YEARS ∈ {5,8,10,12,15}` ×
   `ELO_HA ∈ {50,75,100,125}`, all conf-K = 1.0;
2. **coordinate descent** on the conf-K: holding the best scalar config, sweep
   each confederation's K over `{0.5,0.75,1.0,1.25,1.5,2.0}` one at a time.

The search is a **static** fit (one fit per tournament) to stay cheap; the
winner is then **re-validated with the rolling per-matchday re-fit** (the live
`--as-of` protocol, the gold standard) against the default config.

**Validation set:** the six backtest tournaments (`backtest.TOURNAMENTS`) —
wc2018, euro2021, copa2021, wc2022, euro2024, copa2024 (290 matches).

## Timing

Measured on the dev container, single run of `wcpred tune --elo-engine`:

| phase | configs × tournaments | wall time |
|---|---|---|
| static coordinate search | 56 × 6 (static) | ~70 s |
| rolling re-validation (default + best) | 2 × 6 (per-matchday re-fit) | ~37 s |
| **total** | | **~107 s (1m47s)** |

One rolling `backtest --tournament all --engine elo` (one config) is ~18-19 s;
the static search is ~1.2 s per config.

## Results

### Step 1 — scalar grid (conf-K = 1.0), top rows by pooled RPS (static)

| longterm_years | ha | points | rps | log_loss |
|---:|---:|---:|---:|---:|
| 15 | 50 | 609 | 0.19277 | 2.7966 |
| 12 | 50 | 609 | 0.19285 | 2.7971 |
| 10 | 50 | 599 | 0.19295 | 2.7974 |
| … | | | | |
| 10 | 100 (default) | 601 | 0.19380 | 2.8021 |

Lower HA (50) and a longer window (12-15y) help marginally; everything is within
a narrow RPS band (0.1928-0.1944).

### Step 2 — per-confederation K coordinate sweep (static, from 15y/HA=50)

Winning multiplier per confederation: **UEFA 2.0, CONMEBOL 1.5, CONCACAF 0.5,
CAF 2.0, AFC 2.0, OFC 2.0** → pooled static RPS 0.1896.

Caveat: four of six blocs land on the grid **ceiling (2.0)**. That is largely a
*global* K-scale effect (faster-moving ratings overall — the eloratings K tiers
are a touch low for our 2-feature goal calibration), not six independent
per-bloc findings. The one clearly bloc-specific, interpretable lever is
**CONCACAF = 0.5** (damping a weakly-connected, schedule-inflated confederation —
see `docs/known-limitations.md`).

### Rolling re-validation (per-matchday re-fit — the decisive numbers)

| config | points | rps | log_loss |
|---|---:|---:|---:|
| default (10y, HA=100, K=1.0) | 587 | 0.1950 | 2.8089 |
| scalar-only (15y, HA=50, K=1.0) | 593 | 0.1943 | 2.8047 |
| + **CONCACAF K=0.5** (others 1.0) | 603 | 0.1935 | 2.7971 |
| full best (others → 2.0) | 607 | 0.1934 | 2.7915 |

All three metrics improve over the default, and the improvement holds under the
rolling protocol (not just the static search it was tuned on).

## Interpretation & decision

- **Best by the validation metric:** `longterm_years=15, ha=50,
  conf_k={UEFA:2.0, CONMEBOL:1.5, CONCACAF:0.5, CAF:2.0, AFC:2.0, OFC:2.0}` —
  607 pts / RPS 0.1934 rolling (+20 pts, −0.0016 RPS vs default).
- **But the decomposition shows the signal is mostly two things:** the scalar
  tweak (+6 pts) and **CONCACAF K=0.5** (+10 pts). Pushing the other five blocs
  to the 2.0 ceiling adds only +4 pts and ~0 RPS — a boundary-overfit global-K
  effect, not a robust per-bloc result.
- **Parsimonious pick (recommended if adopting anything):** `longterm_years=15,
  ha=50, CONCACAF=0.5, others=1.0` → 603 pts / RPS 0.1935 — captures essentially
  all the generalising gain without the grid-ceiling overfit.

**Default stays at the published eloratings rule** (`ELO_HA=100`,
`ELO_LONGTERM_YEARS=10`, all `ELO_CONF_K=1.0`) per the regenerability rule: the
engine reproduces standard eloratings out of the box, and a tuned config is
opted into explicitly. The gains are real but modest and partly at a grid
boundary, so they do not warrant changing the published defaults.

**Principled follow-up:** add an explicit *global* K-scale knob (separate from
the *relative* per-confederation multipliers) and re-tune — that should absorb
the global-K effect cleanly and isolate the genuine per-bloc signal (CONCACAF
damping), instead of having four blocs pile onto the grid ceiling.
