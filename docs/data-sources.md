# Data sources for national-team modelling

Reference for where each input comes from, what it covers, and the gotchas.
Findings here were verified empirically against the live APIs in June 2026 —
re-check before assuming they still hold, sports-data feeds change often.

| Input | Source | Pipeline | Coverage | Status |
|---|---|---|---|---|
| Results | martj42/international_results | `wcpred update-data` → `data.load_results` | Every international since 1872, all teams, daily | ✅ Complete |
| 90' scores | same repo: goalscorers.csv + shootouts.csv | `wcpred update-data` → `data._ninety_minute_scores` | Goal minutes for the big tournaments (~46% of matches since 2015, skewed to WC/Euro/Copa) | ✅ For what matters |
| xG | FotMob public JSON API | `scripts/fetch_xg.py` → `data/input/xg.csv` → `prepare_training` | From **~mid-2022**; **no friendlies at all**, ~28% of qualifiers | 🟡 Partial |
| Odds (live) | The Odds API | `scripts/fetch_odds.py` → `data/input/odds.csv` → `predict.py` | Upcoming fixtures only | ✅ For prediction |

xG and goals feed **training** (the team ratings). Odds are applied only at
**predict time** as a market blend — the model never trains on them, so a
historical-odds dataset is not consumed by anything today.

`scripts/update_data.sh` refreshes all three at once: it re-downloads results,
tops up xG incrementally (re-fetching a trailing window so matches that finished
after the last run are caught — it trims those days from the `xg.csv.done`
checkpoint), and upserts odds with `--merge` when `ODDS_API_KEY` is set.

## Results

`wcpred update-data` downloads
[martj42/international_results](https://github.com/martj42/international_results)
(updated daily, includes the WC2026 schedule). Nothing missing. The 48 WC2026
participants are derivable from the dataset itself — the rows with
`tournament == "FIFA World Cup"` and no score yet are the upcoming fixtures.

### 90-minute scores — the extra-time convention

The dataset's `home_score`/`away_score` are the scores **after extra time**
(pens excluded) — but Penka/Superbru and the 1X2 odds market settle on the
**90-minute** result, so a knockout decided in extra time (Croatia 2-1 England
2018: 1-1 at 90') was training *and* being scored against the wrong result.
Rather than switching source, `data.load_results` rebuilds the 90' score from
two sibling files of the same repo, downloaded by `update-data`:

- **goalscorers.csv** — one row per goal with the minute. Convention audited
  2026-07 (all goals dated 2006+): stoppage-time goals carry the *base* minute
  (Kroos 90+5 → `90`, Weghorst 90+11 → `90`), so `minute >= 91` unambiguously
  means extra time. All 26 goals at minutes 91-99 since 2006 belong to genuine
  extra-time matches; minute counts collapse from ~2,000/min in the late 80s
  to single digits at 91+.
- **shootouts.csv** — matches decided on penalties, with the `winner`.

A match is a correction candidate if it has a goal at minute ≥ 91 or appears
in shootouts.csv; it is corrected only when its scorer rows are complete and
consistent (per-team totals equal the recorded score — held for **all** 31
ET/pens knockouts of the six backtest tournaments, and for the 178 corrected
matches overall). `home_score`/`away_score` become the 90' score everywhere
(training, backtest truth, webapp pick evaluation); the original after-ET
score survives in `home_score_ft`/`away_score_ft` and the pens winner in
`shootout_winner`, which `tournament._ko_played_pairs` and the webapp use for
real bracket advancement and result display. Switching the backtest truth to
90' moved the anchor from ~594 to ~566 Penka pts (8 more knockouts are
officially draws) while slightly *improving* RPS — the probabilities were
always better calibrated against 90' than the old truth could show.

Residual gaps, all judged harmless:

- Coverage of goalscorers.csv is ~46% of matches since 2015, skewed to the
  big tournaments. An ET-decided match *without* scorer rows is undetectable
  (its recorded win stands, though the 90' result was a draw) — the cases live
  in minor tournaments (COSAFA Cup, early AFCON rounds) and only dilute
  training marginally; the six backtest tournaments are fully covered.
- A pens match without scorer rows keeps its recorded scoreline. It is a draw
  either way; the exact line is off only if both sides scored equally in ET
  (rare — e.g. Cameroon–Ivory Coast 2006, 0-0 → 1-1 aet).
- **Two-legged ties** can play ET/pens with the single-match score *not*
  level (aggregate rules): France–Ireland 2009 (1-1, 0-1 at 90'),
  Australia–Uruguay 2005 (1-0 + pens). The reconstruction handles them
  naturally — goals at minute ≤ 90 — they just look odd in invariant checks.
- shootouts.csv has the occasional missing row (Spain–Netherlands NL 2025):
  scores stay correct, only forced advancement would miss — irrelevant
  outside the World Cup bracket.

## xG — FotMob

`scripts/fetch_xg.py` pulls FotMob's own xG model via two unauthenticated JSON
endpoints (no API key, no `x-fm-req` token needed for these specific paths):

- `https://www.fotmob.com/api/data/matches?date=YYYYMMDD` — fixtures per day.
- `https://www.fotmob.com/api/data/matchDetails?matchId=ID` — team xG lives at
  `content.stats.Periods.All.stats[*].stats[*]` where `key == "expected_goals"`;
  the value is `["home_xg", "away_xg"]` as strings.

National-team competitions are selected by a whitelist of FotMob `primaryId`s
(World Cup, Friendlies, the five WCQ confederations, EURO, Copa América, the
Nations Leagues, AFCON, Asian Cup, Gold Cup). Youth competitions (U21, etc.)
are deliberately excluded. Use `fetch_xg.py --discover` to find ids to add.

### Coverage cutoff — important

FotMob did **not** model international xG before ~mid-2022, and even after
that the coverage is far narrower than the docstrings used to claim. Verified
by sampling matchDetails and crossing `xg.csv` with `results.csv` (June 2026):

| Period / competition | xG present? |
|---|---|
| WC 2018, friendlies 2018, Euro Q 2019, WCQ 2021 | ❌ None |
| **Friendlies, any date** | ❌ **None** (0 of 1,103 since jul-2022) |
| Qualifiers since jul-2022 | 🟡 ~28% (essentially UEFA only) |
| Nations League June 2022 → | ✅ Yes (UEFA ~72%) |
| World Cup 2022 (Nov) | 🟡 Partial (some matches missing) |
| Euro/AFCON 2023 → today | ✅ Mostly complete |

Overall only ~19% of internationals since jul-2022 carry FotMob xG. A "since
2018" or all-matches xG dataset is **not possible** from free sources.

### Gotchas

- **Date convention:** the CSV date is the UTC kickoff day. A few late-night
  matches may land one day off the dataset's date and fail to merge (the merge
  in `prepare_training` is a left join, so a mismatch silently drops that xG row
  — harmless, just lost coverage).
- **Team names:** mapped to the martj42 dataset via `NAME_MAP` in the script
  (`Ireland`→`Republic of Ireland`, `China`→`China PR`, etc.). Unmapped names
  pass through; if a WC team is being dropped, extend the map.
- **rho correction bypassed with xG:** `model._tau` only fires on scores that
  are exactly 0 or 1. With xG-blended (non-integer) scores it never triggers, so
  the Dixon-Coles low-score correction is effectively disabled for those
  matches. Minor, but relevant when comparing pure-xG (`--xg-alpha 0`) vs goals.

### Using xG in training

`prepare_training` blends `g_eff = α·goals + (1-α)·xG` where xG exists. The blend
is exposed on the CLI via `--xg-alpha` (`0` = pure xG, `1` = pure goals, default
`0.6` from `config.XG_ALPHA`):

```bash
python scripts/fetch_xg.py --from 2022-06-01 --to <today>            # build data/input/xg.csv
wcpred predict  --approach xg --xg data/input/xg.csv --xg-alpha 0    # ratings from xG
wcpred backtest --approach xg --xg data/input/xg.csv --xg-alpha 0    # validate vs goals
```

## Odds

### Live (implemented)

`scripts/fetch_odds.py` uses [The Odds API](https://the-odds-api.com) live
endpoint (free tier, 500 req/month) for **upcoming** fixtures only. `predict.py`
strips the bookmaker margin from the 1X2 prices and builds a market-implied
score matrix. By default the
1X2 marginals come 100% from the market (`ODDS_WEIGHT = 1.0`); the model only
shapes the scoreline distribution within each outcome. `--odds-weight` blends
the model's 1X2 back in (e.g. `0.80` ⇒ `0.80·market + 0.20·model`).

Every fetch also writes a frozen-in-time snapshot
(`data/input/odds/odds_<YYYY-MM-DDTHHMM>.csv`). `odds.csv` is mutable — each
refresh overwrites prices and drops played fixtures — so the snapshots are the
only record of what the market said at a given moment; regenerating a past
`--as-of` run resolves them via `wcpred.data.resolve_odds_path` (latest stamp
≤ as-of + `config.ODDS_CUTOVER`). Seeded June 2026 by backfilling every
version of `odds.csv` in git history.

### Historical odds — none consumed

There is no historical-odds source in the pipeline (the model never trains on
odds, so backtests run model-only in the knockouts). Free options were
surveyed and rejected: The Odds API history is paid only (~25k–35k credits for
a 2020+ backfill); football-data.co.uk/Kaggle are club leagues only; OddsPortal
has no API and scraping it violates its terms; a SofaScore scraper worked but
was dropped (single-book, Cloudflare-gated, not runnable continuously).
