# Next steps — proposals from the July 2026 code review

*2026-07-02. Output of a full review of the three engines (`dc`/`elo`/`bayes`),
the surrounding pipeline, the web app and the docs, run mid-Round-of-32. The
review verified the engines' math directly (numeric gradient checks on the `dc`
and `elo` MLEs, Stan likelihood vs `model._tau` equivalence, `EloHistory`
causality, thirds-table clash analysis) and reproduced the documented backtest
baseline exactly: 594.0 Penka pts / 290 matches, RPS 0.1890, log-loss 2.7702.*

## Already fixed in this review

- **`wcpred backtest` was broken for `dc`/`elo`** since `--bayes-propagate`
  became default-on: the CLI stopped erroring (commit 32637b5) but
  `backtest()` itself still rejected `propagate=True` for non-bayes engines.
  The function-level guard now exempts `propagate` (`backtest.py`), and the
  regression command works again.
- **Same-group knockout rematches were misclassified.** `tournament._split_played`
  decided group-vs-knockout by group membership, but from the quarter-finals on
  a knockout tie can pair two teams of the same group (runner-up vs its own
  group's third; winner vs runner-up in the final). Such a result would have
  been tallied as a *fourth group match* in the standings and hidden from the
  bracket forcing. Both `simulate` (`_split_played`) and `groups`
  (`cli.cmd_groups`) now classify by date against the official calendar
  (`config.WC2026_KNOCKOUT_ROUNDS`). Verified: R32/R16 same-group meetings are
  impossible under the Annex-C thirds table; QF onward they are not.
- Doc corrections: the Australia/USA case study said "Group C" (it is Group D);
  `pick-strategy.md` referenced a `generate_predictions.sh --pick-strategy`
  flag that does not exist; the "knockouts never have odds" premise in
  `known-limitations.md`/`connectivity.md` is outdated (see proposal 1).

## 1. Odds- and venue-aware knockout bracket (highest value now)

**Problem.** `tournament._pairwise_winprob` builds the knockout win-probability
matrix `W` model-only and at a neutral venue. Both justifications have expired
for the ties the bracket has already resolved: scheduled knockout fixtures are
real rows in `results.csv` with a `country` column, and the odds feed covers
them (20 of 21 scheduled knockout fixtures had odds on 2026-07-02).
`connectivity.md`'s Argentina-vs-Spain case study shows why this matters: the
market corrects the model exactly where the cross-confederation scale is
weakest, and "R32 onward" is where that correction was missing.

**Proposal.** In `simulate_tournament`, before falling back to the model-only
`W[i, j]`:

- for every *scheduled* knockout fixture (present in `fixtures`, i.e. dated on/
  after `--as-of`), build the tie's matrix via `predict_match` with the odds
  lookup and `home_side(home, away, r.country)` — the same path `predict`
  already uses — then resolve ET+penalties as today and overwrite that pair's
  entries in `W`;
- unresolved future pairings keep the neutral model-only `W` (nothing better
  exists for them).

**Validation.** No backtest signal exists (no historical odds), so validate by
construction: regenerate today's simulation with and without the change and
check the moved probabilities against the market's outright prices; keep the
default behaviour under `--approach history` byte-identical. Update
`known-limitations.md` §"Knockout matches are simulated at a neutral venue"
when done.

## 2. Decide the bayes-propagation × odds semantics

With `ODDS_WEIGHT = 1.0`, `predict_match` replaces the engine's matrix with
`market_matrix(...)`, which rebuilds it from `matrix_from_rates` — the plug-in
posterior-mean path. So the bayes engine's default-on posterior propagation
(`BAYES_PROPAGATE`, "the honest posterior predictive") has **no effect on any
`--approach odds` output**, which is what the webapp serves. Not a numerical
bug, but it contradicts the documented intent in `config.py`.

Options, cheapest first:

- **Document it** in `bayesian-engine.md` (propagation shapes `history`
  outputs only) — probably sufficient, given propagation is accuracy-neutral.
- Propagate through the market recalibration: recalibrate per posterior draw
  (D Nelder-Mead runs per match — expensive) or recalibrate the propagated
  matrix's rates once (approximate, cheap).

## 3. Harden `odds.to_prob` against high decimal odds

The American-vs-decimal heuristic (`|v| ≥ 100` → American) misreads a decimal
price of 100+ (an extreme longshot: decimal +250 would become implied p ≈ 0.29
instead of ≈ 0.004). Current `odds.csv` maxes at 41.0, so this is latent — but
a WC group-stage minnow vs an elite side can plausibly exceed 100. Cheap fix:
treat any value with a fractional part as decimal, and/or have
`scripts/fetch_odds.py` guarantee decimal format so `to_prob` can require it.

## 4. A minimal smoke script

The project deliberately has no test suite (`backtest --tournament all` is the
regression check) — but that command itself was broken on `main` for ~2 weeks
without anything noticing. A `scripts/smoke.sh` that runs in ~1 min would have
caught it without violating the no-test-suite stance:

```bash
wcpred backtest --tournament wc2022 --static            # dc CLI path
wcpred backtest --tournament wc2022 --static --engine elo
wcpred predict  --approach history --days 2             # fixture pipeline
wcpred groups   --approach history --sims 2000
wcpred simulate --approach history --sims 2000
```

Run it after touching `cli.py`/`backtest.py`/the engines, before committing.

## 5. Pin `/api/connectivity` to the `dc` engine

`webapp/server.py:_connectivity` calls `_model_for(as_of, mtime)` without an
engine, so it inherits `DEFAULT_ENGINE` (`elo` since the webapp default
changed). The Conectividad tab's ratings/opp-rating scatter therefore no longer
matches the `dc`-based analysis in `connectivity.md`, and the elo engine's
`atk`/`dfn` are display-only quantities. Pass `engine="dc"` explicitly (one
line), or add an engine picker to the tab if the elo view is wanted.

## 6. Elo engine: global K-scale parameter (carried over from elo-engine.md)

The June tuning saw four confederation-K multipliers pile onto the grid ceiling
(2.0) for a ~0 RPS gain — a global-K effect leaking through the per-bloc
parameters. Adding an explicit global K scale (one scalar multiplying every
tournament-tier K) and re-tuning would absorb it cleanly and isolate the one
interpretable per-bloc finding (CONCACAF damping, +10 pts). Low urgency: the
defaults deliberately stay at the published eloratings.net rule.

## Smaller observations (no action planned)

- `EloDixonColes`'s display `atk`/`dfn` (`b0/2 ± s/2`) are for `ratings` output
  only; `exp(atk_i + dfn_j)` does **not** equal the engine's `rates()` (factor-2
  difference in the Elo diff). Anything needing rates must call `rates()`.
- `scoring.resolve_extra_time` truncates the ET distribution at the grid edge
  and renormalises globally (slight mass distortion near 8 goals) — negligible.
- `groups.derive_groups` would merge groups if ever fed knockout fixtures with
  `groups=None`; all current callers pass the official draw.
- The webapp calendar already classifies rounds by date (`server.py`), which is
  what motivated the `_split_played` fix above.
