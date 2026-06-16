# Plan: robustness to weak confederation anchoring — LIVING DOCUMENT

> **Status: CLOSED. Phases 0-4 all implemented and rejected as defaults; their
> parameters remain available but off — except the Phase 3 external Elo prior,
> which was since removed from the codebase (2026-06-16).** No internal or
> external anchor tested corrects the diagnosed CONMEBOL/CONCACAF-vs-UEFA bridge
> bias without degrading calibration: the dataset's own bridges are too thin,
> and eloratings.net shares the same regional bias (the external Elo prior added
> +14..+22 Penka pts but grew both biases and worsened log-loss). The limitation
> stands as documented in [known-limitations.md](known-limitations.md), mitigated
> in practice by the market blend (`ODDS_WEIGHT = 1.0`). Created 2026-06-12 from
> the connectivity investigation ([connectivity.md](connectivity.md)) and the
> literature review (references at the bottom).
>
> **Phase 4 (Bayesian hierarchical confederation prior, Stan; opt-in
> `--engine bayes`, default off)** was the deepest attempt — a per-confederation
> offset in the prior that only bridge matches can move. **B1 (dynamic
> random-walk strengths) is the strongest bayes result**: static-validation RPS
> **0.1884** / log-loss **2.7683**, the first bayes variant to match dc — but the
> both-biases check still fails (CONMEBOL–UEFA shrinks +0.103→+0.095, CONCACAF–UEFA
> *grows* +0.120→+0.133). Phase A (static offset prior), the tight-`sigma_conf`
> sweep and B2 (posterior propagation) all hit the same wall: the bias lives in
> the team-rating *levels*, not the offset scale or the score-matrix uncertainty.
> Per-phase numbers are in the Decision log below; design notes in
> [bayesian-confederation-plan.md](bayesian-confederation-plan.md) and
> [bayesian-phase-b-plan.md](bayesian-phase-b-plan.md).
>
> **Maintenance rule — read this before touching the plan's code.** This file
> is the single source of truth for progress on this work. Any session that
> implements, validates or abandons part of it must, in the same session:
> tick/untick the checkboxes it affects, update the phase **Status** lines and
> the header line above, and append a dated row to the *Decision log* and (if
> numbers were produced) the *Results log*. Never re-plan from scratch:
> continue from the state recorded here.

## Problem statement

Dixon-Coles compares confederations only through "bridge" matches, and the
bridges are thin (UEFA spends 3% of its training weight on CONMEBOL — see
[connectivity.md](connectivity.md)). Cross-bloc rating offsets are therefore
weakly identified: AFC/CAF teams can shift in bloc (Australia-over-USA,
[known-limitations.md](known-limitations.md)) and elite cross-bloc claims
(Argentina over Spain, June 2026) carry more uncertainty than the point
ratings suggest. Prior attempts: `GD_CAP` rejected, `CROSS_CONF_WEIGHT`
rejected under rolling re-fit (both documented in known-limitations.md).

## Validation protocol (applies to every phase)

- Primary validation check: `wcpred backtest --tournament all` **rolling** (the live
  protocol). Tune on RPS / log-loss (low variance); points break ties.
- **Baselines to beat (2026-06 defaults, no xG):** ~594 Penka pts / 290
  matches (≈295.5 Superbru), RPS **0.1890**, log-loss **2.7702**.
- Secondary validation check (new, built in Phase 0): bridge-bias audit metric.
- Qualitative control cases: Australia–USA gap (should narrow), Argentina–Spain
  gap (should narrow or widen its stated uncertainty), no nonsense in
  `wcpred ratings --top 20`.
- Mid-tournament adoption: a default change mid-WC2026 makes the evolution
  charts jump on adoption day. Acceptable; note the date here and in the
  webapp note if it happens.

## Reproducibility constraint (hard requirement, all phases)

The current version's results must remain regenerable at all times:

1. **Every new behaviour ships behind a config parameter whose default reproduces
   today's model exactly** (`SHRINKAGE_MODE = None`, etc.). Verify with a
   before/after `backtest` run at defaults: identical numbers.
2. **Never overwrite the date-stamped outputs** in `data/predictions/`,
   `data/groups/`, `data/simulations/`. Experiment outputs go to a separate
   tree (`data/experiments/<variant>/...`) or carry a variant suffix — never
   the plain `picks_/groups_/sim_` names.
3. **Never regenerate past snapshots with a changed model.** If a new default
   is adopted, it applies from its adoption date forward only; historical
   CSVs stay as the model that produced them left them (same spirit as the
   frozen-in-time odds).
4. **Tag the baseline in git before adopting any default change**
   (e.g. `model-baseline-2026-06-12`) so `--as-of` regenerations of the
   pre-change era can be run from the exact code that produced them.

---

## Phase 0 — Bridge-bias audit (diagnostic; do first) ✓ COMPLETE 2026-06-12

**Goal.** Measure the bias before correcting it: per confederation-pair,
compare predicted vs actual outcomes on inter-confederation matches only
(the Elo community's regional-bias test). Decides whether Phases 2+ are
needed at all — if bridges show no systematic miscalibration, the problem is
variance, not bias, and the right response is wider uncertainty, not level
corrections.

**Status: complete (2026-06-12).** Tooling: `wcpred backtest --bridge-audit`
(any tournament selection; pooled table at the end). Re-run it after any
model change to refresh the audit metric.

- [x] In `backtest.py`, tag each backtested match with home/away
      confederation (`confederations.infer_confederations` on the training
      window — keep it causal). *(2026-06-12: `backtest(..., audit=list)`
      collects per-bridge-match records; confs re-inferred at each re-fit.)*
- [x] Aggregate over the six tournaments, bridges only: per conf-pair
      (n, mean predicted win prob vs realised win rate, mean goal residual
      per side, RPS). Print as a table under a `--bridge-audit` flag.
      *(2026-06-12: `backtest.bridge_audit(records)` + `wcpred backtest
      --bridge-audit`; share = win + draw/2 from the alphabetically-first
      conf's perspective. Default off — reproducibility rule 1 holds.
      Smoke-tested on copa2024 static: 18 bridges, bias −0.045.)*
- [x] Run on the full backtest; paste the table into the Results log below.
      *(2026-06-12: done, rolling, all six tournaments — 123 bridge matches.
      Total 594.0 pts / 290 = baseline exactly, confirming the audit changes
      nothing at defaults.)*
- [x] Decide and record in the Decision log: is there a systematic,
      direction-consistent bias (e.g. CONMEBOL overpredicted vs UEFA)?
      → gates Phase 2. *(2026-06-12: see Decision log — directional but
      heterogeneous; Phase 1 justified, Phase 2 conditionally gated.)*

**Acceptance.** Audit table produced over ≥6 tournaments; decision recorded.
No model change in this phase. **✓ Met (2026-06-12).**

**Findings.** On the pair that matters most (CONMEBOL–UEFA, n=22, the
largest sample), the model overrates CONMEBOL by **+8.8pp** of match share
(0.611 predicted vs 0.523 realised) — the Argentina-over-Spain direction,
though <1 SE (~0.107) so not individually significant. CONCACAF is also
overrated vs UEFA (+11.3pp, n=14; UEFA scored ~1.0 goal/match more than
expected against it) and AFC vs CONCACAF (+46.6pp, n=4 — the Australia–USA
pattern in miniature). But AFC–UEFA runs the *other* way (−9.7pp: the 2022
Asian upsets), and aggregating all pairs against UEFA nets out to ≈+1.4pp.
So: no uniform "everyone inflated vs UEFA" bias; pair-specific, moderate,
direction-consistent with the anchoring hypothesis on the two
best-sampled pairs.

## Phase 1 — Shrinkage via data augmentation (pseudo-games / phantom team) ✗ REJECTED 2026-06-12

**Goal.** Regularize the weakly-identified cross-bloc offsets with the
data-augmentation scheme of arXiv 2606.03805: synthetic fractional draws
connect the comparison graph and shrink offsets toward a common center,
without re-weighting real matches (the mistake that sank `CROSS_CONF_WEIGHT`)
and without touching the optimizer.

**Status: complete (2026-06-12) — implemented, validated, rejected as
default. Parameters remain available, default off.**

- [x] `config.py`: `SHRINKAGE_MODE = None | "phantom" | "pseudo"` and
      `SHRINKAGE_WEIGHT` (total pseudo-weight per team, in match-equivalents;
      default off). *(2026-06-12: done; default `None`/0.5.)*
- [x] `data.prepare_training`: append synthetic rows —
      *phantom*: one 1-1 draw per team vs a `__phantom__` team
      (atk=dfn=0 by construction; `neutral=True`, weight = ε);
      *pseudo*: fractional 1-1 draws between cross-confederation team pairs
      (vectorized; total weight ε per team spread over its cross-bloc pairs).
      Mind `MIN_MATCHES` filtering and make sure the phantom never leaks into
      predictions/ratings output.
      *(2026-06-12: `data._shrinkage_rows`, appended after the `MIN_MATCHES`
      filter; per-team pseudo weight ≈ε exactly (0.484-0.556 at ε=0.5).
      Deviation from spec: the phantom's atk/dfn are estimated freely (no
      optimizer surgery), settling at the population center (−0.41/−0.20),
      which preserves the shrink-to-center effect. `cmd_ratings` filters
      `PHANTOM_TEAM`; fixtures never name it. Default verified as a byte-
      identical no-op in `prepare_training` and exact baseline reproduction
      in the rolling backtest.)*
- [x] Wire both parameters into `tune` (grid: ε ∈ {0.25, 0.5, 1, 2} per mode).
      *(2026-06-12: `tune(shrinkages=[(mode, ε), ...])` +
      `wcpred tune --shrinkage` for the Phase 1 grid.)*
- [x] Rolling-backtest grid; paste numbers into the Results log.
      *(2026-06-12: done — RPS and log-loss degrade monotonically in ε for
      both modes; see Results log.)*
- [x] Check control cases (Australia–USA, Argentina–Spain, top-20 sanity) and the
      Phase 0 audit metric at the winning ε. *(2026-06-12: no winning ε —
      checked at ε ∈ {0.25, 0.5} both modes. All move the WRONG way: gaps
      widen (AUS−USA 0.222→0.288 phantom:2; ARG−ESP 0.174→0.380 pseudo:2,
      wider even in population-SD units) and the audit bias grows
      (CONMEBOL–UEFA +0.088→+0.104, CONCACAF–UEFA +0.113→+0.176 at
      pseudo:0.5). See Findings.)*
- [x] Decision log: adopt as default / keep available but off / reject.
      *(2026-06-12: keep available but off.)*
- [ ] ~~If adopted~~: N/A — not adopted; no baseline tag, no regeneration,
      `known-limitations.md` updated with the rejection (mitigation #3).

**Acceptance.** Grid run under rolling re-fit; adopt only if RPS/log-loss do
not degrade and either points improve or the audit bias shrinks.
**✗ Not met:** RPS/log-loss degrade at every ε (pseudo:0.25's +20 pts is
noise by protocol — points only break ties the probabilistic metrics can't).

**Findings.** Uniform shrinkage toward a global center is the wrong *shape*
of fix for this problem. The augmentation does compress the population
(rating SD 1.77 → ~1.25 at ε=1) but the compression hits UEFA's elite harder
than CONMEBOL's — Spain drops more than Argentina, USA more than Australia —
so the cross-bloc *levels* move opposite to the Phase 0 bias on the
best-sampled pairs, and the bridge-audit bias grows monotonically with ε.
This sharpens the Phase 2 design requirement: correct per-confederation
levels (2a hierarchical prior / 2b two-timescale anchoring), not global
spread. Same lesson as `CROSS_CONF_WEIGHT`, from the opposite direction:
blunt global interventions fail; the miscalibration is pair-specific.

## Phase 2 — Level re-anchoring (GATED on Phase 0 finding bias) ✗ REJECTED 2026-06-12

Two designs; implement at most one, chosen with Phase 0/1 numbers in hand:

**2a. Hierarchical confederation prior via MAP penalty** (Baio & Blangiardo
2010, adapted to penalized likelihood). Add to `model.DixonColes` NLL:
`τ·Σ ρ(atk_i − ā_conf(i))` + same for defence + a soft top-level pull of
conf means toward 0, with **robust ρ** (Huber or t-like) against
overshrinkage of legitimate outliers (don't squash Argentina into the
CONMEBOL mean). Gradients by hand like the existing code.

**2b. Two-timescale anchoring.** Confederation offsets evolve slowly;
team form fast. Stage 1: fit per-confederation offsets on bridge matches
only with a long window (all data since `TRAIN_START`, or half-life 6-8y).
Stage 2: fix those offsets as per-team intercepts and fit the usual
short-window atk/dfn. Cheap, interpretable, no optimizer surgery in stage 2.
(Supported by the `HALF_LIFE_DAYS` grid finding that long windows don't hurt.)

**Status: complete (2026-06-12) — design 2b implemented, validated, rejected
as default. Parameters remain available, default off (`CONF_ANCHOR_BETA = 0.0`).**

- [x] Record here which design was picked and why. *(2026-06-12: **2b.**
      2a shrinks teams toward their confederation mean — an intra-bloc
      *spread* intervention that would compress Spain toward a UEFA mean full
      of minnows harder than Argentina toward CONMEBOL's, exactly the Phase 1
      failure mode. 2b touches only the *levels between* confederations (the
      quantity Phase 0 diagnosed), leaves intra-conf spread/rho/home
      advantage untouched, and needs no optimizer surgery.)*
- [x] Implement; rolling-backtest vs the Phase 1 winner; Results log.
      *(2026-06-12: `wcpred/anchor.py` — `conf_deltas` fits a slow-timescale
      DC (same window, `CONF_ANCHOR_HALF_LIFE_DAYS` = 8y decay) and takes
      per-confederation mean-strength differences over the shared teams,
      centred; `anchor_model` shifts each team ±β·Δ/2 on atk/dfn post-fit, so
      intra-confederation predictions are exactly invariant — confirmed:
      euro2021/euro2024/copa2021 backtest rows are byte-identical at every β.
      Parameters: `CONF_ANCHOR_BETA`/`CONF_ANCHOR_HALF_LIFE_DAYS`, CLI
      `--anchor-beta`, grid via `wcpred tune --anchor`. Repro rule 1
      verified: defaults reproduce the baseline and Phase 0 audit table
      exactly. Phase 1 had no winner, so the comparison is against baseline.)*
- [x] Decision log: adopt / reject. *(2026-06-12: rejected as default.)*

**Acceptance.** `bias_a(CONMEBOL–UEFA)` (+0.088 baseline) and
`bias_a(CONCACAF–UEFA)` (+0.113 baseline) must shrink without degrading
RPS/log-loss. **✗ Not met:** RPS/log-loss *improve* (first intervention in
this plan to do so) but CONMEBOL–UEFA shrinks only +0.088 → +0.086 and
CONCACAF–UEFA *grows* +0.113 → +0.120 (β=0.75).

**Findings.** The mechanism works but finds almost nothing to correct: the
long- and short-window fits assign nearly identical confederation levels
(deltas ±0.02 log-goals at as-of 2026-06-12, OFC +0.105 aside), and the
result is insensitive to the slow-window length (half-life 16y ≈ 8y to three
decimals; even the no-decay limit — every bridge since the window start
weighted equally — only moves C–U to +0.084 while CONCACAF–UEFA still grows
to +0.125) — both timescales are anchored by the *same* thin bridges, so
re-weighting history cannot manufacture anchoring information the dataset
doesn't contain. The β-grid improves RPS/log-loss monotonically
(0.1890/2.7702 → 0.1886/2.7688 at β=1) with points 597 vs 594 at β=0.5-0.75,
and 7 of 10 audit pairs improve slightly — but the effect on the diagnosed
bias is ~3% of its size. Not adopted because the validation check failed, the
gain is far below what would justify a mid-tournament default change, and
with `ODDS_WEIGHT = 1.0` the live 1X2 comes from the market anyway, making
the real-pick benefit second-order. Control cases at β=0.75: AUS−USA narrows
0.222 → 0.216 ✓, ARG−ESP widens slightly 0.173 → 0.180 ✗, top-20 sane.
**Conclusion: internal-data avenues (Phases 1-2) are exhausted; only an
external anchor (Phase 3, historical Elo) can add cross-bloc information.**

## Phase 3 — External anchor: historical Elo prior ✗ REJECTED 2026-06-12

**Goal.** Center each team's prior on an affine transform of its
[eloratings.net](https://eloratings.net/) rating — decades of accumulated
bridges anchor the cross-bloc offsets far better than our 2y half-life
window. The hybrid literature (Groll/Ley/Van Eetvelde et al.) consistently
finds external ratings the single most valuable covariate.

**Status: complete (2026-06-12) — implemented, validated, rejected as
default. Parameters remain available, default off (`ELO_PRIOR_TAU = 0.0`,
`--elo-tau`, `wcpred tune --elo`).** The design call (relaxing
train-on-goals-only for external Elo, user-directed) is in the Decision log.
`anchor.anchor_model`'s delta-applier was not needed: the prior enters the
fit directly as a penalty, which lets the data overrule it per team.

- [x] Scraper for historical Elo snapshots (pattern: `fetch_sofascore.py`)
      → `data/input/elo.csv` (`date,team,elo`), team names mapped to martj42.
      *(2026-06-12: `scripts/fetch_elo.py` — eloratings.net's per-year TSVs
      (year-end snapshots, stamped `<year>-12-31`, completed years only) plus
      `World.tsv` (stamped fetch day). 2010-2025 + 2026-06-12 fetched: 4102
      rows, 243 teams/snapshot, every name verified against results.csv.)*
- [x] Leak-free resolution: backtest re-fits use the snapshot ≤ as-of
      (pattern: `data.resolve_odds_path`). *(2026-06-12: `data.load_elo` —
      latest snapshot dated ≤ as-of; a snapshot dated D reflects matches
      through D, so this matches the training cutoff's information set.
      Re-resolved at every rolling re-fit.)*
- [x] Prior: penalty pulling `atk_i − dfn_i` toward `a + b·elo_i` with
      `a, b` profiled on the training window; strength tunable.
      *(2026-06-12: in `DixonColes.fit(elo, elo_tau)` — `τ·Σ(s_i − a −
      b·elo_i)²` over teams with an Elo value, `a, b` re-profiled by OLS at
      every evaluation (gradient = 2τ·residual via the projection identity),
      so only Elo's *relative* levels pull the model. Verified: τ=0 is
      byte-identical to baseline; residual SD vs Elo 0.48 → 0.001 as
      τ → 1000.)*
- [x] Rolling backtest all six tournaments; Results log; Decision log.
      *(2026-06-12: done — grid τ ∈ {0.5, 1, 2, 5, 10}; see both logs.)*

**Acceptance** (validation check inherited from Phase 2): `bias_a(CONMEBOL–UEFA)`
(+0.088 baseline) and `bias_a(CONCACAF–UEFA)` (+0.113 baseline) must shrink
without degrading RPS/log-loss. **✗ Not met:** log-loss degrades
monotonically in τ (2.7702 → 2.7824 at τ=10), RPS flat-to-worse, and both
validation check biases *grow* at every τ (CONMEBOL–UEFA → +0.095..+0.098,
CONCACAF–UEFA → +0.130..+0.146).

**Findings.** The external anchor does add information the dataset lacks —
Penka points jump +14..+22 (594 → 608-616) with exact picks 37 → 39-40, the
AFC pairs improve (AFC–UEFA −0.097 → −0.084, AFC–CAF −0.116 → −0.064 at
τ=5), AUS−USA narrows monotonically (0.222 → 0.150 at τ=5) and the top-10 is
sane. But on the two *diagnosed* pairs the prior pulls the wrong way:
eloratings.net itself overrates CONMEBOL/CONCACAF vs UEFA relative to
2018-2024 bridge outcomes — the regional bias documented by
football-rankings.info (see References) — so anchoring to it amplifies
exactly the bias Phase 0 measured. With the probabilistic metrics degrading,
the points gain is, per protocol, not adoptable evidence. **Conclusion: the
anchoring problem is not fixable by any tested means, internal or external;
close the plan, keep the limitation documented, and let the market blend
(`ODDS_WEIGHT = 1.0`) carry the correction in practice.**

## Phase 4 — Bayesian hierarchical confederation prior (Stan) — A: ✗ REJECTED 2026-06-13

**Goal.** A structurally different attack on the weak anchoring: a Bayesian
Dixon-Coles where each team's attack/defence carries an *additive
confederation-level offset* (`atk_conf`/`dfn_conf`). Intra-confederation
matches only inform the team-level deviations — the shared offset cancels in
the comparison — so they cannot shift a whole bloc; only the rare bridges move
the offset, and with `sigma_conf` small it shrinks toward 0 (no bloc shift).
User-directed; "use Stan if you train the Bayesian model"; the user also flags
**better time treatment** as the biggest parameter (deferred to Phase B). This is
*not* the rejected design 2a (shrink teams toward their conf mean — a spread
intervention): here the offset is a level the team deviations sit *on top of*,
with Student-t deviations so legitimate outliers (Argentina) are not squashed.

**Status: Phases A and B1 complete (2026-06-13) — both implemented, validated,
rejected as default. Engine remains available, off (`--engine dc` is the
default); B1 is opt-in within it via `--bayes-dynamic`.**

Design split (entrevista):
- **A:** offset prior + posterior **mean** plug-in + the existing exponential
  time-decay **weights** as the likelihood weighting. Validated **static**
  (per-tournament single MCMC fit — rolling per-matchday MCMC over six
  tournaments is prohibitive).
- **B (deferred, same branch, only if A convinced):** dynamic random-walk team
  strengths (replace the decay weights), and full **posterior propagation**
  into the score matrix (honest cross-bloc uncertainty).

- [x] `pyproject.toml`: `bayes` extra (cmdstanpy) + `stan/*.stan` package-data.
- [x] `stan/dixon_coles.stan`: weighted DC likelihood (Poisson + four-cell tau,
      matching `DixonColes._tau`); non-centred Student-t team deviations on a
      `normal(0, sigma_conf)` confederation offset; sum-to-zero gauge fixes;
      half-normal `sigma_*`, bounded `nu`, `rho∈[-0.2,0.2]`.
- [x] `model_bayes.BayesianDixonColes(DixonColes)`: overrides only `fit`
      (cmdstanpy sample → posterior-mean atk/dfn/home/rho); inherits the score
      matrix path. Compiled model cached per process.
- [x] `--engine {dc,bayes}` on every subcommand + `backtest(engine=...)`
      (bayes static-only, guarded). Repro rule 1 held: `--engine dc` is the
      untouched MLE path.
- [x] Static validation check (six tournaments) + bridge audit + control cases. See logs.

**Acceptance** (validation check inherited from Phase 2/3): `bias_a(CONMEBOL–UEFA)` and
`bias_a(CONCACAF–UEFA)` must shrink without degrading RPS/log-loss.
**✗ Not met:** vs the dc **static** baseline (601.0 pts / RPS 0.1887 / ll
2.7679), bayes scores 605.0 / **0.1905** / **2.7732** — RPS/log-loss degrade.
CONMEBOL–UEFA shrinks only +0.103 → +0.099; CONCACAF–UEFA *grows* +0.120 →
+0.124.

**Findings.** The user's structural insight is correct — the offset *is*
identified only by bridges — but that is exactly why it fails: the bridges
carry the diagnosed regional bias, so a *free* `sigma_conf` (posterior mean
0.547, 95% CI 0.36–0.83) lets the data set the bloc offsets to **CONMEBOL
+1.58 > UEFA +0.83 > CAF +0.25 > AFC −0.46 > CONCACAF −0.77 > OFC −1.46**
(atk_conf − dfn_conf, as-of 2026-06-13). The hierarchical prior thus *encodes*
the CONMEBOL-over-UEFA bias instead of correcting it: control case ARG−ESP widens
0.162 → 0.222, AUS−USA is flat (0.187 → 0.189). Top-10 order preserved (overall
scale compressed by the Student-t shrinkage). Same root cause as Phases 1-3:
the dataset's internal anchoring information *is* the bias; no amount of
re-structuring the within-data prior can manufacture unbiased cross-bloc signal
(MCMC R-hat > 1.01 on the offset params confirms they are weakly identified —
the diagnosis itself). The mechanism would only correct the bias if
`sigma_conf` were *externally* constrained toward 0 (a strong "no bloc is
systematically stronger" prior), which removes bloc structure rather than
fixing it — the open sensitivity below.

### Phase 4 — B1: dynamic random-walk strengths ✗ REJECTED as default 2026-06-13 (strongest bayes result)

**Goal.** The user's stated main parameter: replace the exponential time-decay
weighting with an explicit latent evolution of each team's attack/defence —
`u[i,t] ~ normal(u[i,t-1], sigma_rw)` over discrete time blocks (default
**half-yearly**, `--bayes-block year|halfyear|quarter`) — and predict from the
most recent block. The confederation offset of Phase A rides unchanged on top
of the time-varying deviation; the random walk *is* the time model, so matches
enter unweighted (the decay weights are dropped). New model
`stan/dixon_coles_dynamic.stan` (non-centred RW, Student-t block-1 column,
per-block sum-to-zero gauge, loosely upper-bounded RW scales to keep the
non-centred cumulative sum finite during warmup). Opt-in `--bayes-dynamic` /
`BAYES_DYNAMIC` (default off); static validation only (per-matchday MCMC
infeasible), as Phase A.

- [x] `stan/dixon_coles_dynamic.stan` + `model_bayes` dynamic branch
      (block index from match dates, adopt the last block's posterior-mean
      atk/dfn). Per-file compile cache. `--engine dc` / static bayes untouched.
- [x] `--bayes-dynamic` / `--bayes-block` on every subcommand;
      `backtest(dynamic=, time_block=)`; guards (dynamic ⇒ bayes ⇒ static).
- [x] Static validation check (six tournaments) + bridge audit + control cases + MCMC diagnose.

**Acceptance** (validation check inherited from Phase 2/3): `bias_a(CONMEBOL–UEFA)` and
`bias_a(CONCACAF–UEFA)` must shrink without degrading RPS/log-loss.
**✗ Not met:** vs dc-static (601.0 / 0.1887 / 2.7679), bayes-dyn scores
**604.0 / RPS 0.1884 / ll 2.7683** — RPS improves, log-loss ties (+0.0004).
CONMEBOL–UEFA shrinks +0.103→**+0.095**, but CONCACAF–UEFA *grows*
+0.120→**+0.133**. Both biases must shrink; one grows ⇒ validation check fails.

**Findings.** Dynamic time is the right parameter for *prediction*: it recovers
everything static Phase A lost (RPS 0.1905→0.1884, ll 2.7732→2.7683) and is the
**first bayes variant to match dc-static on the probabilistic metrics** (RPS
even a hair better). The learned random-walk step is small and smooth
(`sigma_rw_atk`≈0.05, `sigma_rw_dfn`≈0.06 log-goals per half-year), so the gain
is genuine temporal structure, not overfitting. But it is *orthogonal* to the
anchoring problem: `sigma_conf` stays free (≈0.66) and the bloc offsets still
encode the bridge bias, so CONCACAF–UEFA does not improve. Same wall as Phases
1-4A — better time helps accuracy but cannot manufacture unbiased cross-bloc
signal the dataset lacks. Not adopted: the both-biases validation check fails, log-loss is
at best a tie, and the standing rule bars a mid-WC2026 default change without a
clean validation check pass (live 1X2 is market-driven at `ODDS_WEIGHT = 1.0` regardless).
Kept available, off, via `--bayes-dynamic`. Control cases (as-of 2026-06-13): see
the Results log row.

### Phase 4 — tight-`sigma_conf` sensitivity ✗ REJECTED 2026-06-14 (mechanism works; hypothesis refuted)

**Goal.** Test the user's hypothesis in its strongest form — externally
constrain the between-confederation offset scale toward 0 ("no bloc is
systematically stronger") and see whether pinning the offsets near 0 corrects
the diagnosed CONMEBOL/CONCACAF-vs-UEFA bias (Phase 4A/B1 found a *free*
`sigma_conf` ≈ 0.55-0.67 *encodes* the bias). Most interesting combined with
B1's dynamic time (the strongest predictive base).

**Mechanism.** The half-normal prior scale on `sigma_conf` is now a Stan
*data* input (`sigma_conf_scale`, both `stan/dixon_coles.stan` and
`stan/dixon_coles_dynamic.stan`) rather than the hardcoded 0.5, exposed end to
end: `config.BAYES_SIGMA_CONF_SCALE = 0.5` (default reproduces today's bayes
model exactly), `--bayes-sigma-conf`, `BayesianDixonColes.fit(sigma_conf_scale=)`,
`backtest(sigma_conf_scale=)`. Shrinking the scale toward 0 pulls `sigma_conf`
toward 0, collapsing the bloc offsets `atk_conf`/`dfn_conf ~ normal(0,
sigma_conf)` to ≈0 (the "strong prior toward 0" the 4A findings flagged as the
only mechanism that *could* correct the bias — at the cost of removing bloc
structure).

- [x] `sigma_conf_scale` data input in both Stan files; prior line reads it.
- [x] Wire `config.BAYES_SIGMA_CONF_SCALE` / `--bayes-sigma-conf` /
      `fit(sigma_conf_scale=)` / `backtest(sigma_conf_scale=)`. Default 0.5;
      no effect under `--engine dc`.
- [x] Smoke test (copa2024 static): scale=0.5 → 76.0 / 0.1653 / 2.5090;
      scale=0.05 → 71.0 / 0.1632 / 2.5126 (parameter moves the model). B1 dynamic +
      scale=0.05 → 76.0 / 0.1640 / 2.4967 (both Stan files recompile with the
      new data field; works in both time treatments).
- [x] Sensitivity sweep (six tournaments, static, B1 dynamic on): scale ∈
      {0.5, 0.25, 0.1, 0.05, 0.01} + bridge audit + control cases (2026-06-14, driver
      `data/experiments/sigma_conf_sweep/`). Results log below.
- [x] Decision log: does tightening shrink *both* validation check biases without degrading
      RPS/log-loss? **No** — exactly the 4A expectation.

**Acceptance** (validation check inherited from Phase 2/3): `bias_a(CONMEBOL–UEFA)` and
`bias_a(CONCACAF–UEFA)` must shrink without degrading RPS/log-loss.
**✗ Not met:** tightening grows *both* biases (C–U +0.095→+0.106, CONCACAF–U
+0.133→+0.160 at scale 0.01) and degrades RPS/log-loss (0.1884/2.7683 →
0.1888/2.7751).

**Findings.** The mechanism works exactly as designed — shrinking the prior
scale collapses `sigma_conf` (post. mean 0.657 → 0.568 → 0.396 → 0.275 → **0.051**
across 0.5→0.01) and the bloc offsets toward 0; at scale 0.01 the offsets are
near-zero and the order even *flips* to UEFA +0.24 > CONMEBOL +0.10 (no bloc
structure left). **But pinning the offsets near 0 makes the diagnosed bias
worse, not better:** the cross-bloc level the offset used to carry is forced
back into the team-level ratings, which the (now unregularised by a bloc prior)
bridges fit even more directly — so both validation check biases grow, RPS/log-loss degrade,
and the control cases widen monotonically (ARG−ESP +0.087→+0.162, AUS−USA
+0.145→+0.234 as scale 0.5→0.01). This is the decisive confirmation of the 4A
diagnosis: **the CONMEBOL/CONCACAF-vs-UEFA bias does not live in the
confederation offset — it lives in the team ratings the thin bridges drive.**
Neither a free `sigma_conf` (4A/B1: encodes the bias) nor one externally
constrained toward 0 (here: pushes it into team strengths and grows it) corrects
the asymmetry. The offset-scale parameter is real and works; it is simply not the
parameter for this problem. Parameter kept available, default 0.5.

### Phase 4 — B2: full posterior propagation ✗ REJECTED as default 2026-06-14 (clean, but a wash)

**Goal.** Phases A/B1 plug in the posterior *means* of atk/dfn/home/rho and
build one Dixon-Coles score matrix from them. B2 instead returns the posterior
mean of the *per-draw* score matrices — the honest posterior predictive — so the
rating uncertainty (largest on the weakly-anchored cross-bloc bridges) widens
the scoreline distribution. The question: does carrying that uncertainty into
the scorelines improve calibration and/or shrink the diagnosed bias?

**Mechanism.** `BayesianDixonColes.fit` keeps the MCMC draws
(`atk_draws`/`dfn_draws`/`home_draws`/`rho_draws`; the most-recent block under
B1) and `score_matrix` is overridden to average the per-draw DC matrices when
propagation is on. Opt-in `--bayes-propagate` / `BAYES_PROPAGATE` (default off →
the inherited plug-in path, byte-identical). Composes with A or B1; validated on
the B1 base (the strongest predictive variant). No effect under `--engine dc`.

- [x] Store posterior draws in `fit`; override `score_matrix` (vectorised over
      draws: per-draw lam/mu/rho, four-cell tau, clip, normalise, then mean).
- [x] Wire `config.BAYES_PROPAGATE` / `--bayes-propagate` /
      `fit(propagate=)` / `backtest(propagate=)` + guards (bayes-only).
- [x] Smoke test (ARG−ESP, B1 static fit): propagation widens the matrix
      (entropy 2.58→2.62), both matrices normalise, max|ΔP| 0.0056.
- [x] Paired validation check (six tournaments, static, B1 dynamic): one MCMC fit per
      tournament scored twice — plug-in mean vs propagation — so the comparison
      is exact, no sampling drift (driver `scripts/gate_b2.py`). Results +
      bridge audit below. The plug-in arm reproduces the B1 row exactly (604.0 /
      0.1884 / 2.7683, identical per-tournament rows) ✓.
- [x] Decision log: adopt / reject.

**Acceptance** (validation check inherited from Phase 2/3): `bias_a(CONMEBOL–UEFA)` and
`bias_a(CONCACAF–UEFA)` must shrink without degrading RPS/log-loss.
**✗ Not met:** vs the B1 plug-in arm (604.0 / 0.1884 / 2.7683), propagation
scores 609.0 / **0.1886** / **2.7681** — RPS a hair worse, log-loss a hair
better (a wash). CONMEBOL–UEFA shrinks +0.0950→+0.0932 but CONCACAF–UEFA *grows*
+0.1330→+0.1352; both must shrink ⇒ validation check fails.

**Findings.** B2 is a clean, well-behaved addition that does exactly what it is
designed to do and nothing more. It does **not** touch the rating means, so the
1X2 *level* — and therefore the diagnosed bias direction — is essentially fixed:
the bridge biases move by ≤0.002 (noise), because propagation only changes the
*spread* of the scoreline distribution, not its centre. The aggregate
probabilistic metrics are a wash (RPS +0.0002, log-loss −0.0002): the honest
widening neither clearly helps nor hurts calibration on 290 matches. There are
faint signs it does the *scoreline* job — exact picks 39→40, and the bridge
goal-residuals edge toward 0 (CONMEBOL–UEFA goal_res_b 0.326→0.306, CONCACAF–UEFA
1.071→1.043) — consistent with a more honest spread, but all within noise. Same
wall as every Phase 1-4 avenue: the cross-bloc bias lives in the team-rating
*levels* the thin bridges drive, and no re-treatment of the *uncertainty* around
those levels can move it. Not adopted: validation check fails (one bias grows), RPS is
hair-worse, and the standing rule bars a mid-WC2026 default change without a
clean pass (live 1X2 is market-driven at `ODDS_WEIGHT = 1.0` regardless). Kept
available, off, via `--bayes-propagate` — the honest posterior-predictive score
matrix is there for anyone who wants cross-bloc uncertainty reflected in the
scorelines rather than point picks.

**Plan status: CLOSED again (2026-06-14).** Every Phase 0-4 avenue (MLE
shrinkage/anchoring/Elo + Bayesian offset-prior / dynamic time / tight-sigma_conf
/ posterior propagation) is implemented and decided; all rejected as default,
all kept available behind default-off parameters. The weak-anchoring limitation
stands as documented in [known-limitations.md](known-limitations.md), corrected
in practice by the market blend.

## Out of scope (noted, not planned)

- Odds-implied outright (champion) market to correct synthetic knockout
  pairings in `simulate` — attacks the symptom, not the model; revisit only
  if all phases above fail to move the audit metric.

---

## Decision log

| Date | Decision |
|---|---|
| 2026-06-12 | Plan created. Order A(audit)→B(augmentation)→validation check→C/D, Elo last, per the literature review. |
| 2026-06-12 | Hard requirement added (user): current version must stay regenerable — parameters default-off, experiment outputs in a separate tree, past snapshots never regenerated with a changed model, git tag before any default change. |
| 2026-06-12 | **Phase 0 verdict:** directional anchoring bias confirmed on the two best-sampled pairs (CONMEBOL +8.8pp and CONCACAF +11.3pp overrated vs UEFA) but heterogeneous (AFC−UEFA opposite sign) and individually <1 SE — more *uncertainty* than uniform bias. **Phase 1 (soft shrinkage) justified and is the right shape of fix; Phase 2 (aggressive level correction) conditionally gated — revisit with Phase 1 results using `bias_a(CONMEBOL–UEFA)` and `bias_a(CONCACAF–UEFA)` as the audit metric.** |
| 2026-06-12 | **Phase 1 verdict: rejected as default; parameters kept available but off** (`SHRINKAGE_MODE = None`). Rolling grid: RPS/log-loss degrade monotonically in ε for both modes; pseudo:0.25's +20 pts dismissed as noise per protocol. Control cases widen and the bridge-audit bias *grows* with ε — uniform shrinkage to a global center compresses UEFA's elite more than CONMEBOL's, the opposite of the Phase 0 correction. Phase 0's "Phase 1 is the right shape of fix" assessment was wrong. **Phase 2 validation check: evidence now favours per-confederation level correction (2a or 2b); decide design there with these numbers in hand.** Reproducibility rule 1 verified: defaults are a byte-identical no-op and the rolling backtest reproduces the baseline exactly. |
| 2026-06-12 | **Phase 2 design call: 2b (two-timescale anchoring), 2a not implemented.** 2a is an intra-confederation spread intervention (teams shrink toward their conf mean) and would reproduce the Phase 1 failure mode — compressing UEFA's elite toward a minnow-heavy mean harder than CONMEBOL's; 2b corrects only the between-confederation levels Phase 0 diagnosed, with no optimizer surgery. |
| 2026-06-12 | **Phase 2 verdict: rejected as default; parameter kept available but off** (`CONF_ANCHOR_BETA = 0.0`, `wcpred tune --anchor`). First intervention to *improve* rolling RPS/log-loss (0.1890/2.7702 → 0.1887/2.7691 at β=0.75, points 597 vs 594), but the validation check failed: CONMEBOL–UEFA bias shrinks only +0.088 → +0.086 and CONCACAF–UEFA grows +0.113 → +0.120. Root cause: long- and short-window confederation levels are nearly identical (deltas ±0.02; insensitive to slow-window length 8y vs 16y) — both timescales are anchored by the same thin bridges, so **the dataset's internal anchoring information is exhausted**. Gain too small to justify a mid-WC2026 default change (and live 1X2 is market-driven at `ODDS_WEIGHT = 1.0`). Reproducibility rule 1 verified: defaults reproduce the baseline and the Phase 0 audit table exactly. **Next: Phase 3 (external Elo anchor) is the only remaining avenue; its train-on-goals-only design call must be recorded here first.** |
| 2026-06-12 | **Phase 3 design call (user-directed: "implement Phase 3"): the train-on-goals-only rule is relaxed for external Elo.** eloratings.net ratings may enter the *fit* as a prior center — a penalty pulling each team's strength (atk − dfn) toward `a + b·elo`, with `a, b` profiled on the training window so only Elo's *relative* levels (decades of accumulated bridges) anchor the model, never its absolute scale. Odds remain predict-time-only. Guardrails: the prior ships behind `ELO_PRIOR_TAU = 0.0` (default off, repro rule 1); Elo snapshots are dated rows in `data/input/elo.csv` and resolved causally (latest snapshot ≤ as-of) at every rolling re-fit, the frozen-in-time-odds pattern. |
| 2026-06-12 | **Phase 3 verdict: rejected as default; parameters kept available but off** (`ELO_PRIOR_TAU = 0.0`, `--elo-tau`, `wcpred tune --elo`). Rolling grid τ ∈ {0.5, 1, 2, 5, 10}: log-loss degrades monotonically (2.7702 → 2.7824), RPS flat-to-worse, and the validation check failed in *both* pairs — CONMEBOL–UEFA bias grows +0.088 → +0.095..+0.098 and CONCACAF–UEFA +0.113 → +0.130..+0.146 at every τ. Root cause: eloratings.net shares the regional bias on those pairs (the football-rankings.info finding), so an external Elo anchor amplifies rather than corrects it. The +14..+22 Penka points (exact 37 → 39-40) are real but inadmissible per protocol while RPS/log-loss degrade. AFC pairs and AUS−USA do improve — Elo helps where the model *under*rates. **Plan closed: Phases 0-3 exhausted; the limitation stays documented in known-limitations.md (mitigation #5/#6), corrected in practice by the market blend.** Repro rule 1 verified: post-code defaults reproduce the baseline exactly (594.0 / 0.1890 / 2.7702, identical per-tournament rows). |
| 2026-06-12 | **Phase 2b log-closure review (after the Phase 3 session):** the leftover `/tmp/p2_flat.log` run was identified by exact reproduction as the β=0.75 / slow-half-life-5840d variant already recorded above — nothing was missing from the record. The sensitivity check was additionally extended to the slow window's no-decay limit (every historical bridge weighted equally): 596.0 pts / RPS 0.1886 / ll 2.7690, C–U +0.084, CONCACAF–UEFA +0.125. **Validation check verdict re-confirmed and final: Phase 2b stays rejected** — even unlimited use of the window's bridge history cannot shrink the diagnosed biases. The plan remains closed. |
| 2026-06-13 | **Plan REOPENED (user-directed new approach): Phase 4 — Bayesian Dixon-Coles in Stan with a hierarchical confederation-offset prior.** New module `model_bayes.BayesianDixonColes` + `stan/dixon_coles.stan`, opt-in `--engine bayes` (default `dc`, regenerable). Split A (offset prior, posterior mean, MLE time-weights, static validation) / B (dynamic time + posterior propagation, deferred behind A's validation check). Design notes in `docs/bayesian-confederation-plan.md`. Repro rule 1 held: `--engine dc` is the untouched MLE path. |
| 2026-06-13 | **Phase 4A verdict: rejected as default; engine kept available but off** (`--engine dc` default). Static validation check (six tournaments): bayes 605.0 pts / RPS 0.1905 / ll 2.7732 vs dc-static 601.0 / 0.1887 / 2.7679 — RPS/log-loss degrade; CONMEBOL–UEFA +0.103→+0.099 (barely), CONCACAF–UEFA +0.120→+0.124 (grows). Root cause: with `sigma_conf` free (post. mean 0.547) the offset prior is set by the *biased* bridges and lands CONMEBOL +1.58 > UEFA +0.83, **encoding** the regional bias (ARG−ESP control case widens 0.162→0.222). Confirms Phases 1-3: internal-data anchoring is exhausted. **Open: tight-`sigma_conf` sensitivity, and Phase B (dynamic time — the user's stated main parameter).** |
| 2026-06-13 | **Phase 4 B1 verdict (user-directed "implementa la fase B"): rejected as default; opt-in `--bayes-dynamic` (default off).** Dynamic random-walk strengths over half-year blocks replace the decay weighting (new `stan/dixon_coles_dynamic.stan`; `--bayes-block` granularity; static-only like A). Scope per user: **B1 only** (dynamic time), keep the current implementation intact as a flag; B2 (posterior propagation) deferred. Static validation check: **604.0 pts / RPS 0.1884 / ll 2.7683** vs dc-static 601.0 / 0.1887 / 2.7679 — **the first bayes variant to match dc on RPS/log-loss** (RPS a hair better, ll tied), recovering all that static A lost. But the both-biases validation check still fails: CONMEBOL–UEFA shrinks +0.103→+0.095, CONCACAF–UEFA grows +0.120→+0.133. Dynamic time is the right parameter for *accuracy* but is orthogonal to anchoring (`sigma_conf` still free ≈0.66, offsets still encode the bridge bias). `sigma_rw`≈0.05-0.06 log-goals/half-year (small, smooth — genuine temporal structure, not overfit). Not adopted: validation check fails, ll at best a tie, no mid-WC2026 default change without a clean pass (live 1X2 is market-driven anyway). Repro: `--engine dc` and static `--engine bayes` byte-identical. Stan numerics: loosely upper-bounded RW scales fix a non-centred warmup `inf+(-inf)=nan`; MCMC clean on treedepth/divergences/E-BFMI, R-hat>1.01 persists on the weakly-identified offset/raw-innovation params (the diagnosis itself, as in 4A). **Open: tight-`sigma_conf` × B1; Phase B2.** |
| 2026-06-13 | **Phase 4 tight-`sigma_conf` sensitivity — IMPLEMENTED.** The half-normal prior scale on `sigma_conf` (between-confederation offset spread) is now a Stan *data* input `sigma_conf_scale` in both `stan/dixon_coles.stan` and `stan/dixon_coles_dynamic.stan` (was hardcoded 0.5), wired end to end: `config.BAYES_SIGMA_CONF_SCALE = 0.5` (default reproduces today's bayes model), `--bayes-sigma-conf`, `fit(sigma_conf_scale=)`, `backtest(sigma_conf_scale=)`. Shrinking it toward 0 pins the bloc offsets near 0 — the strong "no bloc is systematically stronger" prior the 4A findings flagged as the only mechanism that *could* correct the bias. Repro rule 1: default 0.5 unchanged; no effect under `--engine dc`. Smoke test (copa2024 static): scale 0.5 → 76.0/0.1653/2.5090, scale 0.05 → 71.0/0.1632/2.5126; B1 dynamic + 0.05 → 76.0/0.1640/2.4967 (parameter moves the model in both time treatments; both Stan files recompile). |
| 2026-06-14 | **Phase 4 tight-`sigma_conf` verdict (user-directed "ejecuta el experimento"): rejected; parameter kept available, default `BAYES_SIGMA_CONF_SCALE = 0.5`.** Six-tournament sweep, B1 dynamic, scale ∈ {0.5,0.25,0.1,0.05,0.01} (driver `data/experiments/sigma_conf_sweep/`). The mechanism works as designed — `sigma_conf` post. mean collapses 0.657→0.568→0.396→0.275→**0.051** and the bloc offsets shrink to ≈0 (at 0.01 the order even flips to UEFA +0.24 > CONMEBOL +0.10, no bloc structure). **But the validation check fails harder, not softer:** both diagnosed biases *grow* (C–U +0.095→+0.106, CONCACAF–U +0.133→+0.160 at 0.01) and RPS/log-loss degrade (0.1884/2.7683 → 0.1888/2.7751); control cases widen monotonically (ARG−ESP +0.087→+0.162, AUS−USA +0.145→+0.234). Pinning the offset to 0 just forces the cross-bloc level back into the team ratings the thin bridges drive — decisive confirmation of the 4A diagnosis that **the bias lives in the team ratings, not the offset scale.** Neither a free nor a constrained-toward-0 `sigma_conf` corrects it. Repro rule 1 verified: scale 0.5 reproduces the B1 row exactly (604.0 / 0.1884 / 2.7683, identical per-tournament rows + bridge audit). **This closes the open tight-`sigma_conf` item; Phase B2 (posterior propagation) remains the only Phase 4 avenue not yet decided.** |
| 2026-06-14 | **Phase 4 B2 verdict (user-directed "valida la Fase B2"): rejected as default; opt-in `--bayes-propagate` (default off).** Full posterior propagation — `score_matrix` returns the posterior mean of the per-draw Dixon-Coles matrices instead of one matrix from the posterior-mean ratings. Paired six-tournament validation check on the B1 dynamic base (one MCMC fit per tournament scored twice, plug-in vs propagation, so the comparison is exact; driver `scripts/gate_b2.py`). vs the B1 plug-in arm (604.0 / 0.1884 / 2.7683): propagation 609.0 / **0.1886** / **2.7681** — RPS a hair worse, ll a hair better (a wash). CONMEBOL–UEFA shrinks +0.0950→+0.0932 but CONCACAF–UEFA grows +0.1330→+0.1352 (both must shrink ⇒ validation check fails). Root cause: B2 does not touch the rating means, so the 1X2 *level* and the bias direction are fixed; it only widens the scoreline *spread* (smoke test entropy 2.58→2.62; bridge goal-residuals edge toward 0; exact picks 39→40 — all within noise). Same wall as Phases 1-4: the cross-bloc bias lives in the team-rating levels, and re-treating the *uncertainty* around them cannot move it. Repro rule 1 verified: the plug-in arm reproduces the B1 row exactly (604.0 / 0.1884 / 2.7683). **Plan CLOSED again — every Phase 0-4 avenue implemented and decided, all default-off.** |

## Results log

*(append `backtest --tournament all` rolling numbers here; always alongside
the baseline row)*

| Date | Variant | Penka pts | RPS | log-loss | Bridge audit | Notes |
|---|---|---|---|---|---|---|
| baseline | defaults 2026-06, no xG | ~594 | 0.1890 | 2.7702 | (Phase 0) | from CLAUDE.md / known-limitations.md |
| 2026-06-12 | defaults + `--bridge-audit` (rolling, all) | **594.0** | 0.1890* | 2.7702* | CONMEBOL–UEFA **+0.088** | identical to baseline ✓ (audit is read-only); *pooled from per-tournament rows below |
| 2026-06-12 | shrinkage grid baseline (None:0, rolling, all) | **594.0** | 0.1890 | 2.7702 | — | post-Phase-1-code defaults = baseline exactly ✓ (repro rule 1) |
| 2026-06-12 | phantom ε=0.25 / 0.5 / 1 / 2 (rolling, all) | 586 / 572 / 560 / 548 | 0.1891 / 0.1894 / 0.1902 / 0.1914 | 2.7716 / 2.7745 / 2.7803 / 2.7851 | C–U +0.093 / +0.096 / – / – | monotone degradation in ε |
| 2026-06-12 | pseudo ε=0.25 / 0.5 / 1 / 2 (rolling, all) | 614 / 574 / 541 / 526 | 0.1895 / 0.1901 / 0.1914 / 0.1936 | 2.7767 / 2.7820 / 2.7906 / 2.8039 | C–U +0.099 / +0.104 / – / – | ε=0.25's +20 pts = noise (RPS/ll worse); CONCACAF–UEFA bias +0.113→+0.176 at ε=0.5 |
| 2026-06-12 | anchor-code defaults (β=0, rolling, all) | **594.0** | 0.1890 | 2.7702 | C–U +0.088 | post-Phase-2-code defaults = baseline + Phase 0 audit table exactly ✓ (repro rule 1) |
| 2026-06-12 | anchor β=0.25 / 0.5 / 0.75 / 1 (rolling, all) | 594 / 597 / 597 / 591 | 0.1889 / 0.1888 / 0.1887 / 0.1886 | 2.7698 / 2.7694 / 2.7691 / 2.7688 | C–U – / – / +0.086 / +0.085 | RPS+ll improve monotonically in β (first time); CONCACAF–UEFA grows +0.113→+0.120 / +0.123; euro2021/euro2024/copa2021 invariant (intra-conf) ✓ |
| 2026-06-12 | anchor β=0.75, slow half-life 5840d (rolling, all) | 597.0 | 0.1887 | 2.7690 | C–U +0.085 | ≈ identical to 2920d — slow-window length irrelevant: same bridges anchor both timescales |
| 2026-06-12 | anchor β=0.75, slow window FLAT (no decay; rolling, all) | 596.0 | 0.1886 | 2.7690 | C–U +0.084 | no-decay limit of the slow window (validation check re-check while closing the Phase 2 logs): even weighting every historical bridge equally, C–U shrinks only +0.088 → +0.084 and CONCACAF–UEFA still grows +0.113 → +0.125 — validation check verdict confirmed |
| 2026-06-12 | elo-code defaults (τ=0, rolling, all) | **594.0** | 0.18896 | 2.77019 | — | post-Phase-3-code defaults = baseline exactly ✓ (repro rule 1); per-tournament rows identical |
| 2026-06-12 | elo τ=0.5 / 1 / 2 / 5 / 10 (rolling, all) | 616 / 611 / 615 / 608 / 611 | 0.1892 / 0.1892 / 0.1891 / 0.1890 / 0.1891 | 2.7736 / 2.7750 / 2.7765 / 2.7791 / 2.7824 | C–U +0.095 / – / +0.098 / +0.095 / – | log-loss degrades monotonically in τ; points +14..+22 and exact 37→39/40 (inadmissible per protocol); CONCACAF–UEFA +0.113 → +0.130 / – / +0.142 / +0.146 / – |
| 2026-06-13 | **dc baseline (STATIC, all)** — Phase 4 apples-to-apples | **601.0** | 0.1887 | 2.7679 | C–U +0.103 | static, not the rolling baseline (594/0.1890/2.7702); bayes is static-only so the comparison is static-vs-static. CONCACAF–UEFA +0.120 |
| 2026-06-13 | **Phase 4A** bayes `--engine bayes` (STATIC, all) | 605.0 | **0.1905** | **2.7732** | C–U **+0.099** | RPS/ll degrade vs dc-static; CONCACAF–UEFA grows +0.120→+0.124, AFC–UEFA −0.093→−0.081. Control cases (as-of 2026-06-13): AUS−USA 0.187→0.189 (flat), ARG−ESP 0.162→0.222 (widens ✗); sigma_conf 0.547 (CI 0.36-0.83); bloc offsets CONMEBOL +1.58 > UEFA +0.83 > CAF +0.25 > AFC −0.46 > CONCACAF −0.77 > OFC −1.46; top-10 order preserved, scale compressed; MCMC R-hat>1.01 on offset params |
| 2026-06-13 | **Phase 4 B1** bayes `--bayes-dynamic` halfyear (STATIC, all) | **604.0** | **0.1884** | **2.7683** | C–U **+0.095** | **first bayes to match dc-static** (601.0/0.1887/2.7679): RPS a hair better, ll tied (+0.0004); recovers all of static A's loss (0.1905/2.7732→0.1884/2.7683). CONMEBOL–UEFA shrinks +0.103→+0.095 but CONCACAF–UEFA grows +0.120→**+0.133** (validation check fails). Per-tournament: wc2018 132/0.1989/2.8209 · euro2021 100/0.1820/2.8567 · copa2021 67/0.1545/2.5855 · wc2022 108/0.2118/3.0245 · euro2024 121/0.1862/2.5653 · copa2024 76/0.1639/2.4937. sigma_rw_atk 0.049 (CI 0.038-0.059), sigma_rw_dfn 0.058 (smooth, well-identified). Control cases (as-of 2026-06-13): AUS−USA 0.222→**0.157** (narrows ✓), ARG−ESP 0.222(static-A)→**0.092** (does NOT widen ✓); top-10 sane (ARG 2.91, ESP 2.82, BRA, ENG, POR…); sigma_conf 0.667 (CI 0.46-0.98); bloc offsets CONMEBOL +1.76 > UEFA +1.16 > CAF +0.43 > AFC −0.45 > CONCACAF −0.77 > OFC −2.12 (still encodes CONMEBOL>UEFA → CONCACAF–UEFA grows). MCMC (4×500): no divergences, treedepth/E-BFMI/ESS satisfactory; R-hat>1.01 only on composite atk/dfn + sigma_dfn (sparse team-block states; raw innovations converged) |
| 2026-06-14 | **Phase 4 tight-`sigma_conf` sweep** B1 dynamic, scale 0.5/0.25/0.1/0.05/0.01 (STATIC, all) | 604 / 600 / 591 / 599 / 592 | 0.1884 / 0.1885 / 0.1884 / 0.1884 / **0.1888** | 2.7683 / 2.7685 / 2.7679 / 2.7688 / **2.7751** | C–U +0.095 / +0.095 / +0.095 / +0.096 / **+0.106** | scale 0.5 reproduces the B1 row exactly ✓ (repro rule 1). CONCACAF–U +0.133 / +0.133 / +0.134 / +0.135 / **+0.160** — both biases *grow* as the offset is pinned. sigma_conf post. mean 0.657 / 0.568 / 0.396 / 0.275 / **0.051** (collapses as designed); bloc offsets shrink to ≈0 and at 0.01 flip to UEFA +0.24 > CONMEBOL +0.10 (no bloc structure). Control cases (as-of 2026-06-14) ARG−ESP +0.087 / +0.087 / +0.086 / +0.079 / **+0.162**, AUS−USA +0.190 / +0.145 / +0.155 / +0.166 / **+0.234** (widen at the tight end). Driver: `data/experiments/sigma_conf_sweep/`. **Validation check fails (both biases grow, RPS/ll degrade) — mechanism works, hypothesis refuted: the bias is in the team ratings, not the offset scale.** |
| 2026-06-14 | **Phase 4 B2** propagation `--bayes-propagate` on B1 dynamic (STATIC, all, paired) | 609.0 | **0.1886** | **2.7681** | C–U **+0.0932** | paired validation check (`scripts/gate_b2.py`): same MCMC fit scored twice. Plug-in arm reproduces B1 exactly (604.0/0.1884/2.7683) ✓; propagation 609.0/0.1886/2.7681 — RPS +0.0002, ll −0.0002 (wash). CONMEBOL–UEFA +0.0950→+0.0932, CONCACAF–UEFA +0.1330→**+0.1352** (grows → validation check fails). exact 39→40. Per-tournament (plug-in→prop): wc2018 132→132 / 0.1989→0.1990 / 2.8209→2.8198 · euro2021 100→108 / 0.1820→0.1822 / 2.8567→2.8571 · copa2021 67→60 / 0.1545→0.1552 / 2.5855→2.5972 · wc2022 108→105 / 0.2118→0.2117 / 3.0245→3.0061 · euro2024 121→117 / 0.1862→0.1864 / 2.5653→2.5784 · copa2024 76→87 / 0.1639→0.1642 / 2.4937→2.4991. Bridge goal-residuals edge toward 0 (honest spread); means unchanged so the bias direction is fixed. Smoke test (ARG−ESP B1 static): entropy 2.58→2.62, max\|ΔP\| 0.0056. |

Phase 3 control cases (overall rating gaps at as-of 2026-06-12; baseline →
elo τ=0.5/2/5): AUS−USA 0.222 → 0.199/0.169/0.150 (narrows monotonically ✓);
ARG−ESP 0.174 → 0.189/0.175/0.113 (widens at low τ, narrows from τ≈2 ✗/✓ —
current Elo has Spain above Argentina, so large τ flips the sign); top-10
sane at every τ (ARG, ESP, ENG, BRA order preserved). Residual SD of
strength vs Elo: 0.48 baseline → 0.21 (τ=1) → 0.11 (τ=5).

Phase 2 control cases (overall rating gaps at as-of 2026-06-12; baseline →
anchor β=0.5/0.75/1): AUS−USA 0.222 → 0.218/0.216/0.213 (narrows ✓);
ARG−ESP 0.173 → 0.178/0.180/0.183 (widens slightly ✗); top-20 order sane at
β=1. Conf deltas at β=1: AFC +0.006, CAF −0.016, CONCACAF +0.015,
CONMEBOL −0.012, OFC +0.105, UEFA −0.021.

Phase 1 control cases (overall rating gaps at as-of 2026-06-12; baseline →
phantom:0.25/0.5/1/2 → pseudo:0.25/0.5/1/2): AUS−USA 0.222 →
0.242/0.255/0.271/0.288 → 0.264/0.286/0.313/0.341; ARG−ESP 0.174 →
0.208/0.236/0.277/0.318 → 0.259/0.306/0.356/0.380. Both widen in every
variant — also after rescaling by the population SD (1.77 baseline → ~1.25
at ε=1).

Phase 0 audit table (2026-06-12, rolling, six tournaments, 123 bridge
matches; share = win + draw/2 from `conf_a`'s perspective, `bias_a` > 0 =
model overrates `conf_a`; `goal_res` = actual − expected goals per side):

```
  conf_a   conf_b  n  exp_share_a  real_share_a  bias_a  goal_res_a  goal_res_b   rps
CONMEBOL     UEFA 22        0.611         0.523   0.088       0.093       0.311 0.193
     CAF     UEFA 21        0.328         0.357  -0.029       0.253       0.116 0.204
CONCACAF CONMEBOL 21        0.299         0.310  -0.011      -0.113      -0.050 0.136
     AFC     UEFA 19        0.298         0.395  -0.097       0.299       0.084 0.238
CONCACAF     UEFA 14        0.328         0.214   0.113      -0.112       0.999 0.142
     AFC CONMEBOL  8        0.233         0.312  -0.079       0.151      -0.178 0.234
     CAF CONMEBOL  6        0.281         0.333  -0.053       0.089      -0.363 0.279
     AFC      CAF  6        0.468         0.583  -0.116       0.595       0.464 0.301
     AFC CONCACAF  4        0.466         0.000   0.466      -0.403       0.468 0.260
     CAF CONCACAF  2        0.604         1.000  -0.396       0.808       0.206 0.182
```

Per-tournament baseline rows (defaults, rolling — for future comparisons):
wc2018 133.0 pts / rps 0.1978 / ll 2.8144 · euro2021 113.0 / 0.1814 / 2.8602
· copa2021 67.0 / 0.1560 / 2.5750 · wc2022 98.0 / 0.2159 / 3.0408 ·
euro2024 107.0 / 0.1887 / 2.5750 · copa2024 76.0 / 0.1589 / 2.4793.

## References

- [Regularization in Paired Comparison Models via Pseudo-Games and Phantom Players (arXiv 2606.03805)](https://arxiv.org/abs/2606.03805)
- [Ranking in generalized Bradley-Terry when strong connection fails (arXiv 1411.1168)](https://arxiv.org/pdf/1411.1168)
- [Baio & Blangiardo (2010) — Bayesian hierarchical model for football results](https://discovery.ucl.ac.uk/16040/1/16040.pdf)
- [Groll et al. (2018) — FIFA World Cup prediction, hybrid abilities (arXiv 1806.03208)](https://arxiv.org/pdf/1806.03208)
- [Hybrid ML forecasts for UEFA EURO 2020 (arXiv 2106.05799)](https://arxiv.org/pdf/2106.05799)
- [football-rankings.info — regional bias test for Elo](http://www.football-rankings.info/2022/10/is-there-regional-bias-in-elo-rating.html)
- [opisthokonta.net — Dixon-Coles, disconnected clusters](https://opisthokonta.net/?p=1685)
