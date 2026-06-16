# Elo engine tuning — timing & decision

Hyperparameter search for the Elo engine (`--engine elo`,
`wcpred/model_elo.py`). Reproduce with:

```bash
wcpred tune --elo-engine     # static coordinate search + rolling re-validation
```

The full result tables (scalar grid over `ELO_LONGTERM_YEARS`×`ELO_HA`, the
per-confederation K coordinate sweep, and the rolling re-validation) live in
**[engine-tuning-2026-06.md](engine-tuning-2026-06.md) §Motor `elo`** — the
unified June-2026 run across all three engines. This note keeps only what is
specific to the Elo search: the timing breakdown and the decision rationale.

## Method (summary)

`backtest.tune_elo` does **coordinate search** on RPS (points as tiebreak):
(1) a scalar grid over `ELO_LONGTERM_YEARS ∈ {5,8,10,12,15}` ×
`ELO_HA ∈ {50,75,100,125}` at conf-K = 1.0, then (2) coordinate descent on the
per-confederation K `ELO_CONF_K` over `{0.5,…,2.0}`. Tuned on a **static** fit
(cheap), then re-validated with the **rolling per-matchday re-fit** (the live
`--as-of` protocol) over the six backtest tournaments.

## Timing

Measured on the dev container, single run of `wcpred tune --elo-engine`:

| phase | configs × tournaments | wall time |
|---|---|---|
| static coordinate search | 56 × 6 (static) | ~70 s |
| rolling re-validation (default + best) | 2 × 6 (per-matchday re-fit) | ~37 s |
| **total** | | **~107 s (1m47s)** |

One rolling `backtest --tournament all --engine elo` (one config) is ~18-19 s;
the static search is ~1.2 s per config.

## Interpretation & decision

The rolling winner is `longterm_years=15, ha=50,
conf_k={UEFA:2.0, CONMEBOL:1.5, CONCACAF:0.5, CAF:2.0, AFC:2.0, OFC:2.0}` —
607 pts / RPS 0.1934 (+20 pts, −0.0016 RPS vs the default). But the gain
decomposes into three parts:

- the scalar tweak (15y/HA=50): **+6 pts**;
- **CONCACAF K=0.5** alone: **+10 pts** — the one interpretable per-bloc result
  (damping a weakly-connected, schedule-inflated confederation, see
  `docs/known-limitations.md`);
- pushing the other five blocs to the grid **ceiling (2.0)**: only +4 pts and
  ~0 RPS — a global-K / boundary-overfit effect, not a robust per-bloc finding.

**Parsimonious pick** (if adopting anything): `longterm_years=15, ha=50,
CONCACAF=0.5, others=1.0` → 603 pts / RPS 0.1935 — essentially all the
generalising gain without the ceiling overfit.

**Default stays at the published eloratings rule** (`ELO_HA=100`,
`ELO_LONGTERM_YEARS=10`, all `ELO_CONF_K=1.0`) per the regenerability rule: the
gains are real but modest and partly at a grid boundary, so they do not warrant
changing the published defaults; a tuned config is opted into explicitly.

**Principled follow-up:** add an explicit *global* K-scale parameter (separate
from the *relative* per-confederation multipliers) and re-tune — that should
absorb the global-K effect cleanly and isolate the genuine per-bloc signal
(CONCACAF damping), instead of four blocs piling onto the grid ceiling.
