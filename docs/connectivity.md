# Confederation connectivity — reading the model's cross-bloc comparisons

*June 2026. Companion to the **Conectividad** tab in the web app
(`GET /api/connectivity`, `webapp/server.py`) and to the schedule-inflation
caveat in [known-limitations.md](known-limitations.md). Numbers below are from
the 2026-06-12 training set (10 834 matches, no xG).*

Dixon-Coles can only compare teams from different confederations through the
"bridge" matches between them. Where bridges are thin, the *relative scale* of
two confederations is weakly identified: a handful of results can shift entire
blocs up or down, and the model's discount of weak opposition falls short. The
Conectividad tab quantifies exactly how thin each bridge is, using the same
time-decayed weights the model fits on.

## The connectivity matrix (rows normalised, training weight)

| | UEFA | CONMEBOL | CONCACAF | CAF | AFC | OFC |
|---|---|---|---|---|---|---|
| **UEFA** | **82%** | 3% | 5% | 5% | 5% | 1% |
| **CONMEBOL** | 12% | **42%** | 25% | 8% | 12% | 1% |
| **CONCACAF** | 8% | 10% | **70%** | 4% | 7% | 1% |
| **CAF** | 6% | 2% | 3% | **79%** | 10% | 0% |
| **AFC** | 7% | 4% | 6% | 11% | **70%** | 2% |
| **OFC** | 9% | 3% | 7% | 4% | 15% | **61%** |

Key readings:

1. **UEFA–CONMEBOL is the thinnest meaningful bridge.** Only 3% of UEFA's
   training weight (effective weight ~27 vs ~749 intra-UEFA — on the order of
   25-30 match-equivalents, further shrunk by time decay) connects Europe's
   elite to South America's. Any model claim about *which bloc's* elite is
   stronger rests on that thread (Finalissima, a few friendlies).
2. **CONMEBOL is well-bridged, but anchored "from below".** It is the most
   externally connected confederation (58% of its weight is bridges) — only
   10 teams, so lots of outside friendlies — but its biggest bridges are
   CONCACAF (25%) and AFC (12%), not UEFA (12%). Its scale is calibrated
   mostly against weaker, themselves poorly-anchored pools.
3. **AFC and CAF are the most isolated in useful terms** (70% / 79% intra,
   and their main mutual bridge is each other). This is the Australia-over-USA
   mechanism documented in known-limitations.md, and it applies to the high
   ratings of Morocco (#8, weighted mean opponent **1.05** — by far the
   weakest schedule in the model's top ranks) and Japan (#12, 1.19).
4. **Within-bloc rankings are trustworthy; cross-bloc offsets are not.**
   Where match density is high (intra-UEFA, intra-CONMEBOL) the opponent
   discount works as intended — e.g. England's soft schedule (mean opponent
   1.55 vs Spain's 1.86) is properly discounted *within* UEFA. It is the
   *offset between scales* that is fragile.

## Case study: why the model has Argentina above Spain (June 2026)

The model ranks Argentina #1 (overall 3.15) over Spain (2.98) while outright
betting markets have Spain first. The full chain:

- **The edge is defensive.** Over the 3-year half-life window Argentina
  conceded 0.38 goals/match (14 in 37; 30W-3D-4L) vs Spain's 0.82 (32 in 39;
  29W-9D-1L). Spain attacks more (2.69 vs 2.05 GF/match), but in Dixon-Coles
  defence counts as much as attack; head-to-head on neutral ground the model
  gives ARG 38% / draw 33% / ESP 29%.
- **The schedules are not comparable, and the comparison runs over the thin
  bridge.** Argentina's weighted mean opponent is 1.63 vs Spain's 1.86; its
  bridge share looks healthy (42%) but splits 19% CONCACAF + 8% CAF + 5% AFC
  and only **9% UEFA** (Spain: 84% intra-UEFA). Argentina's clean-sheet record
  is built 77% against CONMEBOL+CONCACAF and is compared to Spain's through
  point 1 above.
- **The market only corrects where it exists.** With `--approach odds` the
  group stage moves toward Spain (win-group 77% vs Argentina's 68%), but
  synthetic knockout pairings carry no odds, so R32 onward is model-only —
  and that is precisely where Argentina overtakes. Its champion probability
  is identical with and without odds (16.6% vs 16.6%; Spain 13.6% / 13.4%).
- **Verdict.** The Argentina-over-Spain gap (+0.17 overall) is smaller than
  the reasonable uncertainty of the UEFA↔CONMEBOL scale offset it depends on.
  Read 16.6% vs 13.6% as a statistical tie with nominal edge to Argentina;
  the market's ordering (Spain first) is at least as credible. There is real
  signal too — reigning champion, 4 losses in 37 — so this is an *uncertainty*
  caveat, not a known bias direction.

## A rejected fix: connectivity-weighted shrinkage

A natural-looking fix is to weight what each team inherits from its bloc by its
*connectivity*, anchoring the isolated teams without touching the well-bridged
ones. It was implemented on the Bayesian engine as three opt-in variants
(`--bayes-connect`, `BAYES_CONNECT_*`): scale the confederation **offset** or the
team's own **deviation**, driven by **bridge share** or by **schedule difficulty**
(weighted mean opponent rating). All were **rejected** (June 2026):

| config | points | RPS | log-loss | Australia |
|---|---:|---:|---:|---:|
| base bayes | **605** | **0.1905** | **2.7732** | #28 |
| deviation × bridge share | 581 | 0.1932 | 2.7950 | #21 ⬆ |
| deviation × schedule difficulty | 593 | 0.1910 | 2.7855 | #28 |

**Root cause — bridge share is the wrong predictor.** Australia is **not** poorly
connected (bridge share 0.47); it is inflated by the *difficulty* of its bridges.
And moving the *order* would require acting on the between-bloc scale
(offset / `sigma_conf`), which is itself flat (see [bayesian-engine.md](bayesian-engine.md)),
not on a per-team shrinkage — the sum-to-zero gauge re-centres any per-team scaling,
so it cannot reorder the ranking even with the right predictor. Bias share down a
bloc, and a *negative* offset shrinks toward 0, which *raises* the weak bloc — the
opposite of the intent.

## How to explore / reproduce

- Web app → **Conectividad** tab: conf×conf heatmap, bridge-share vs rating
  scatter (click a flag for a team's per-confederation breakdown), and the
  48-team table with bridge share and weighted mean opponent rating.
- API: `GET /api/connectivity` (model-only; cached per day + results.csv
  mtime). Confederation membership is inferred from continental-competition
  appearances by `wcpred/confederations.py`.
- Mitigations tried and rejected (`GD_CAP`, `CROSS_CONF_WEIGHT`, and more), plus
  the structural attempt — the hierarchical confederation prior of the Bayesian
  engine: see [known-limitations.md](known-limitations.md) and
  [bayesian-engine.md](bayesian-engine.md).
