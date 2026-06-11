# Known modelling limitations

## Confederation isolation inflates ratings of teams with weak schedules

**Symptom.** The model ranks **Australia (24th, overall 1.98)** above the
**USA (43rd, overall 1.66)** and has Australia finishing ahead in Group C, even
though the USA is a host. This shows up in *every* variant (history-only, xG
blend, pure xG), so it is not an xG-data artefact — it is a rating-model effect.

**Root cause — strength of schedule the model can't fully discount.** Since
June 2024:

| Team | Record | Avg. opponent rating | Weakest opponents faced |
|---|---|---|---|
| USA | 15W-4D-14L, GD +4 | **1.66** (median 1.78) | Trinidad −0.0, Guatemala 0.5, Jamaica 0.6 |
| Australia | 12W-5D-5L, GD +19 | **1.12** (median 1.02) | **Bangladesh −1.3**, Indonesia 0.2, China 0.5 |

Australia built a +19 goal difference largely by beating AFC minnows; the USA
played (and often lost to) Brazil, Portugal, Germany, Belgium and Colombia.

Dixon-Coles *does* discount opponent strength (attack/defence are fit jointly,
so thrashing a weak team is worth less). But the discount is only as good as the
**connectivity between confederations**. Australia's schedule is almost entirely
intra-AFC, and the AFC pool has few recent "bridge" matches against Europe/South
America (the same gap seen in xG coverage — see `data-sources.md`). With the AFC
weakly anchored to the global scale, its teams — including the minnows Australia
beat — are over-rated in absolute terms, so the "weak opponent" discount falls
short. The result: Australia's easy wins are over-credited relative to the USA's
losses to elite sides.

A second, smaller factor used to be the friendly down-weight: 20 of the USA's
33 matches were friendlies — exactly the games where it tested itself against
top teams got half weight. Since the June 2026 tuning run,
`FRIENDLY_WEIGHT = 1.0` (friendlies count fully), which removes this factor and
slightly narrows the gap (see sensitivity below; it does not flip the ranking).

There is also a **genuine, non-artefact component**: the USA has simply been
poor — 14 losses in 33 games. A host losing 42% of its matches is real signal,
not just schedule.

**Sensitivity check (friendly weight).** Raising `FRIENDLY_WEIGHT` narrows the
gap but never flips it, confirming friendly weighting is not the main driver:

| `FRIENDLY_WEIGHT` | USA overall (rank) | Australia overall (rank) |
|---|---|---|
| 0.5 | 1.66 (43) | 1.98 (24) |
| 1.0 (default since Jun 2026) | 1.72 (40) | 1.93 (27) |
| 1.25 | 1.73 (39) | 1.91 (28) |

**Net verdict.** The Australia-over-USA gap is *half real, half artefact*: the
USA has genuinely lost a lot, but Australia's record is schedule-inflated and the
model under-discounts it because the AFC is weakly connected to the global pool.
Once home advantage is applied, the group-stage simulation already treats it as a
coin flip (qualify prob ≈ 0.498 vs 0.494), so the model is not "broken" — but
ratings of teams from poorly-connected confederations (AFC, and to a lesser
extent CONMEBOL/CONCACAF/CAF) should be read with this caveat.

**Mitigations — tested June 2026 (`wcpred tune`: six tournaments 2018-2024,
~290 matches, rolling re-fit confirmation, no xG):**

1. **Cap goal difference** in training (e.g. treat 5-0 as 3-0) — **tested and
   rejected**. Implemented as `GD_CAP` (`config.py`/`data.prepare_training`),
   but it worsened RPS, log-loss *and* Superbru points in every grid
   combination (`gd_cap=3` was the worst setting tried; `gd_cap=4` still below
   no cap). Blowout margins carry real signal that Dixon-Coles already
   discounts adequately. The knob stays available, default `GD_CAP = None`.
2. **Confederation-strength prior**, or anchor better with more history
   (extend `TRAIN_START` so there are more cross-confederation matches) — not
   yet implemented. Related evidence: the `HALF_LIFE_DAYS` grid
   (365/545/730/1095) showed 365 clearly worse and 545-1095 tied, so leaning
   on more history doesn't hurt.
3. **Accept as a known limitation** and let home advantage + market odds (for
   imminent fixtures) correct it in practice — the current stance. Since June
   2026 this also covers the group simulation: `groups --approach odds` blends
   the market exactly like `predict`/`simulate` (previously `groups` was
   model-only and silently ignored the odds flags). The effect is large where
   the artefact bites: in Group D the model-only sim had Australia qualifying
   at 0.49 (above Paraguay's 0.46), while the market-blended sim drops
   Australia to 0.26 with Paraguay at 0.42.

The same tuning run *did* find one improvement: `FRIENDLY_WEIGHT` 0.5 → 1.0
improved RPS monotonically across the grid and won on all three metrics under
rolling re-fit validation (295.5 vs 289.0 points over 290 matches, RPS 0.1890
vs 0.1897, log-loss 2.770 vs 2.781). Now the default — and it also slightly
narrows the USA gap above.

**How to reproduce.** Compare strength of schedule and re-fit at different
friendly weights:

```python
from wcpred.data import load_results, prepare_training
from wcpred.model import DixonColes
import wcpred.data as data

df = load_results()  # defaults to data/input/results.csv
model = DixonColes().fit(prepare_training(df, as_of="2026-06-11"))
ov = {t: model.atk[i] - model.dfn[i] for t, i in model.idx.items()}
# inspect ov["United States"] vs ov["Australia"] and each side's opponents;
# pass friendly_weight=... to prepare_training to test sensitivity.
```

## Blending xG into training (`XG_ALPHA`) does not help Superbru points

**Symptom.** The `xg`/`full` approaches blend xG into the training goals
(`XG_ALPHA = α·goals + (1−α)·xG`, default **0.6**), but no value of α beats
plain goals (α=1.0) on the metric that matters — expected Superbru points.

**Experiment — June 2026 (`backtest`, rolling re-fit).** FotMob xG only covers
~mid-2022 onward, so only **euro2024** and **copa2024** (83 of the 290 matches)
are affected; the other four tournaments are identical to history-only at every
α. Sweeping α from 1.0 (pure goals) to 0.0 (pure xG):

Pooled, all six tournaments (n=290):

| α | points | pts/match | RPS | log-loss | exact |
|-----|--------|-----------|--------|----------|-------|
| 1.0 | 295.5 | 1.019 | 0.1890 | 2.7702 | 44 |
| 0.8 | 295.5 | 1.019 | 0.1889 | 2.7695 | 44 |
| 0.6 (default) | 293.0 | 1.010 | 0.1889 | 2.7689 | 43 |
| 0.4 | 293.0 | 1.010 | 0.1889 | 2.7684 | 43 |
| 0.2 | 293.0 | 1.010 | 0.1890 | 2.7681 | 43 |
| 0.0 | 290.0 | 1.000 | 0.1890 | 2.7678 | 42 |

**Finding — a clean monotone tension.** More xG weight (lower α) improves
log-loss monotonically (2.7702 → 2.7678) but *worsens* Superbru points
monotonically (295.5 → 290.0); RPS is flat. So xG calibrates the score matrix
fractionally better while costing exact/close picks. The log-loss gain is
~0.1% and rests entirely on 83 matches; the points loss is consistent.

**Net verdict.** The default `XG_ALPHA = 0.6` is **not justified**: it already
gives up 2.5 pooled points vs α=0.8 with no measurable RPS gain. No α beats
pure goals on points, so for Superbru the right call is to leave xG out
(α≈0.8–1.0). This confirms the standing decision to validate, tune and predict
**without xG** for WC 2026 — coverage is too partial (only 2 of 6 backtest
tournaments move) and the blend buys nothing where it matters.

**How to reproduce.**

```python
from wcpred.data import load_results
from wcpred.backtest import backtest, TOURNAMENTS

df = load_results()
for a in (1.0, 0.8, 0.6, 0.4, 0.2, 0.0):
    res = [backtest(df, t, rolling=True, xg_path="data/input/xg.csv", xg_alpha=a)
           for t in TOURNAMENTS]
    n = sum(r["matches"] for r in res)
    pts = sum(r["points"] for r in res)
    rps = sum(r["rps"] * r["matches"] for r in res) / n
    print(f"alpha={a}: {pts:.1f} pts ({pts/n:.3f}/match), rps {rps:.4f}")
```

## Knockout matches are simulated at a neutral venue

**Scope.** `wcpred simulate` (full-tournament Monte Carlo, `tournament.py`) plays
the knockout bracket — Round of 32 through the final — with **no home
advantage**. Host-nation advantage is modelled *only* in the group stage.

**Why.** Home advantage is applied via `predict.home_side`, which keys off the
fixture's `country` column. Group fixtures carry that column, so the hosts
(USA, Mexico, Canada) correctly get the boost when playing at home. The knockout
bracket, by contrast, is **synthetic**: slots are "Winner of Group E", "best
third assigned to match 80", etc., with no venue attached, and there is no
stadium→slot mapping in the data. All knockout venues sit in USA/MEX/CAN, so in
principle a host playing a knockout in its own country would have an edge, but
without a per-slot venue we cannot know which side that is — so every knockout
tie is played at a neutral venue (`home_side=None` when building the pairwise
win-probability matrix `W`).

**Related.** Odds feeds cover scheduled group fixtures only, so synthetic
knockout pairings never have odds; `W` is model-only in the knockouts even under
`--approach odds`. The group stage still blends odds where available.

**Net effect.** A small, systematic under-rating of the three hosts' deep-run
probabilities (semi-final onward) relative to a venue-aware model. Acceptable
for v1; a future `host_boost` hook could apply `home_side="home"` in `W` rows
where a host meets a non-host, if desired.
