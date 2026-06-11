# Data sources for national-team modelling

Reference for where each input comes from, what it covers, and the gotchas.
Findings here were verified empirically against the live APIs in June 2026 —
re-check before assuming they still hold, sports-data feeds change often.

| Input | Source | Pipeline | Coverage | Status |
|---|---|---|---|---|
| Results | martj42/international_results | `wcpred update-data` → `data.load_results` | Every international since 1872, all teams, daily | ✅ Complete |
| xG | FotMob public JSON API | `scripts/fetch_xg.py` → `data/input/xg.csv` → `prepare_training` | Internationals from **~mid-2022** only | 🟡 Recent only |
| Odds (live) | The Odds API | `scripts/fetch_odds.py` → `data/input/odds.csv` → `predict.py` | Upcoming fixtures only | ✅ For prediction |
| Odds (historical) | — | not implemented | — | 🔴 Paid / no free source |

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

**Why not FBref:** FBref was the standard free xG source, but StatsPerform/Opta
terminated its data feed on **20 January 2026**, removing xG *including all
history*. FBref is no longer usable for xG. Understat (the other classic
scrapeable source) only covers club leagues, never national teams.

**What we use instead:** `scripts/fetch_xg.py` pulls FotMob's own xG model via
two unauthenticated JSON endpoints (no API key, no `x-fm-req` token needed for
these specific paths):

- `https://www.fotmob.com/api/data/matches?date=YYYYMMDD` — fixtures per day.
- `https://www.fotmob.com/api/data/matchDetails?matchId=ID` — team xG lives at
  `content.stats.Periods.All.stats[*].stats[*]` where `key == "expected_goals"`;
  the value is `["home_xg", "away_xg"]` as strings.

National-team competitions are selected by a whitelist of FotMob `primaryId`s
(World Cup, Friendlies, the five WCQ confederations, EURO, Copa América, the
Nations Leagues, AFCON, Asian Cup, Gold Cup). Youth competitions (U21, etc.)
are deliberately excluded. Use `fetch_xg.py --discover` to find ids to add.

### Coverage cutoff — important

FotMob did **not** model international xG before ~mid-2022. Verified by sampling
matchDetails directly:

| Period | xG present? |
|---|---|
| WC 2018, friendlies 2018, Euro Q 2019, WCQ 2021 | ❌ None |
| Nations League June 2022 | ✅ Yes |
| World Cup 2022 (Nov) | 🟡 Partial (some matches missing) |
| 2023 → today | ✅ Complete |

So a "since 2018" xG dataset is **not possible** from free sources. The usable
window is ~2022→now. The model's 2-year half-life means this still carries most
of the relevant training weight. StatsBomb open data has xG for a few isolated
tournaments (e.g. WC 2022) but not friendlies/qualifiers, so it is not a general
backfill.

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
de-vigs the 1X2 prices and blends a market-implied score matrix with the model
(`0.80·market + 0.20·model`, `--odds-weight`).

### Historical (not implemented — paid / no free source)

There is no free, clean source of historical **international** odds:

- The Odds API has history from **6 June 2020**, but it is **paid only**
  (Starter ≈ $30/mo, 20k credits) and the historical endpoint costs **10 credits
  per region × market × snapshot**. Backfilling all WCQ-team matches since 2020
  (~2,500–3,500 games) ≈ 25k–35k credits, i.e. more than one Starter month.
  Endpoints: `/v4/historical/sports/{sport}/events?date=` (list, 1 credit) then
  `/v4/historical/sports/{sport}/odds?...&date=` (10 credits).
- Free datasets (football-data.co.uk, most Kaggle sets) are **club leagues only**.
- OddsPortal covers internationals (open + close) but has **no API**; scraping it
  violates its terms and is anti-bot protected.

Decision (June 2026): **deferred.** Since the model does not train on odds, a
historical-odds dataset unlocks nothing today; it would only matter for
backtesting/calibrating the market blend or training a new market-aware model.
