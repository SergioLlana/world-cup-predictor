# Data sources for national-team modelling

Reference for where each input comes from, what it covers, and the gotchas.
Findings here were verified empirically against the live APIs in June 2026 —
re-check before assuming they still hold, sports-data feeds change often.

| Input | Source | Pipeline | Coverage | Status |
|---|---|---|---|---|
| Results | martj42/international_results | `wcpred update-data` → `data.load_results` | Every international since 1872, all teams, daily | ✅ Complete |
| xG | FotMob public JSON API | `scripts/fetch_xg.py` → `data/input/xg.csv` → `prepare_training` | From **~mid-2022**; **no friendlies at all**, ~28% of qualifiers | 🟡 Partial |
| Odds (live) | The Odds API | `scripts/fetch_odds.py` → `data/input/odds.csv` → `predict.py` | Upcoming fixtures only | ✅ For prediction |
| Odds (historical) | SofaScore | `scripts/fetch_sofascore.py` → `data/input/odds_history.csv` | 1X2 closing, single book, back to ≥2018 | 🟡 Not consumed by pipeline yet |
| Elo (historical) | eloratings.net | `scripts/fetch_elo.py` → `data/input/elo.csv` → `data.load_elo` | Year-end snapshots 2010-2025 + fetch-day, all national teams | 🟡 Optional training prior, off by default |

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
2018" or all-matches xG dataset is **not possible** from free sources —
SofaScore doesn't fix this either (see `docs/sofascore.md`).

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

Every fetch also writes a time-capsule snapshot
(`data/input/odds/odds_<YYYY-MM-DDTHHMM>.csv`). `odds.csv` is mutable — each
refresh overwrites prices and drops played fixtures — so the snapshots are the
only record of what the market said at a given moment; regenerating a past
`--as-of` run resolves them via `wcpred.data.resolve_odds_path` (latest stamp
≤ as-of + `config.ODDS_CUTOVER`). Seeded June 2026 by backfilling every
version of `odds.csv` in git history.

### Historical (SofaScore — implemented June 2026)

`scripts/fetch_sofascore.py` (needs `pip install curl_cffi` to get past
Cloudflare) backfills closing 1X2 odds into `data/input/odds_history.csv`
(`date,home_team,away_team,odds_1,odds_X,odds_2`, decimal). Verified back to
WC2018, friendlies included. Single featured book — not a multi-book median —
so it complements rather than replaces The Odds API. Details and caveats:
`docs/sofascore.md`.

Nothing consumes it yet (the model never trains on odds); it exists to enable
backtesting/calibrating the market blend (`--odds-weight`).

Rejected alternatives: The Odds API history is paid only (~25k–35k credits for
a 2020+ backfill); football-data.co.uk/Kaggle are club leagues only; OddsPortal
has no API and scraping it violates its terms.

## Elo — eloratings.net (implemented June 2026)

`scripts/fetch_elo.py` downloads the plain-TSV data behind
[eloratings.net](https://eloratings.net/): one file per **completed** year
(ratings after that year's final match, stamped `<year>-12-31`) plus
`World.tsv` (current list, stamped with the fetch date) into
`data/input/elo.csv` (`date,team,elo`). Names are mapped to martj42 and
verified against `results.csv`; re-runs are idempotent (rows keyed by
date+team). Don't fetch the current year's `<year>.tsv` mid-year — it mirrors
`World.tsv` and would be mislabelled as a year-end snapshot.

Consumed only by the optional Phase 3 external Elo prior
(`docs/model-robustness-plan.md`; `ELO_PRIOR_TAU`, default off — tested and
rejected as default June 2026): `data.load_elo` resolves the latest snapshot
≤ as-of at every (re-)fit, so backtests stay causal at yearly granularity.
