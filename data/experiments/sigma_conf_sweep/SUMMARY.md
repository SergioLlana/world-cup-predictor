# Tight-`sigma_conf` sensitivity sweep — 2026-06-14

Driver: `run.sh` (six-tournament static backtest of the dynamic Bayesian
Dixon-Coles at a grid of confederation-offset prior scales) + `control_cases.py`
(ARG−ESP / AUS−USA gaps, `sigma_conf` posterior, bloc offsets at the live
as-of). Full verdict in `docs/bayesian-engine.md`.

`--engine bayes --bayes-dynamic --bayes-block halfyear --static --tournament all
--bayes-sigma-conf <scale> --bridge-audit`

| scale | pts | pooled RPS | pooled ll | CONMEBOL–UEFA | CONCACAF–UEFA | σ_conf post. | ARG−ESP | AUS−USA |
|------:|----:|-----------:|----------:|:-------------:|:-------------:|:------------:|:-------:|:-------:|
| 0.5   | 604 | 0.1884 | 2.7683 | +0.095 | +0.133 | 0.657 | +0.087 | +0.190 |
| 0.25  | 600 | 0.1885 | 2.7685 | +0.095 | +0.133 | 0.568 | +0.087 | +0.145 |
| 0.1   | 591 | 0.1884 | 2.7679 | +0.095 | +0.134 | 0.396 | +0.086 | +0.155 |
| 0.05  | 599 | 0.1884 | 2.7688 | +0.096 | +0.135 | 0.275 | +0.079 | +0.166 |
| 0.01  | 592 | 0.1888 | 2.7751 | +0.106 | +0.160 | 0.051 | +0.162 | +0.234 |

Bloc offsets (atk_conf − dfn_conf), as-of 2026-06-14:
- scale 0.5:  CONMEBOL +1.73 > UEFA +1.15 > CAF +0.44 > AFC −0.46 > CONCACAF −0.76 > OFC −2.09
- scale 0.01: UEFA +0.24 > CONMEBOL +0.10 > CAF +0.07 > AFC −0.12 > OFC −0.12 > CONCACAF −0.16 (≈0, order flips)

**Verdict: rejected.** The mechanism works — tightening the prior collapses
`sigma_conf` and the bloc offsets toward 0 — but pinning the offsets near 0
makes *both* diagnosed biases grow and degrades RPS/log-loss, because the
cross-bloc level is forced back into the team ratings the thin bridges drive.
The bias lives in the team ratings, not the offset scale. Parameter kept available,
default `BAYES_SIGMA_CONF_SCALE = 0.5`. Scale 0.5 reproduces the recorded
dynamic-strengths row exactly (repro rule 1).
