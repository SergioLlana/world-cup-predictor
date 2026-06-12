# wcpred — World Cup predictor optimised for Penka

Predicts FIFA World Cup 2026 scorelines and picks the prediction that
maximises your expected points under the Penka scoring rules, which pay
three tiers — exact score / exact goal difference (any correct draw counts) /
correct winner — with stakes that grow by stage:

| Result | Group stage | R32 & R16 | QF onwards |
|---|---|---|---|
| Exact score | 5 | 8 | 11 |
| Goal difference or draw | 3 | 5 | 7 |
| Match winner only | 2 | 3 | 5 |

The original Superbru mode (3 exact / 1.5 outcome+close / 1 outcome, with the
Closeness Index `|ΔGoalDiff| + |ΔTotalGoals| / 2 ≤ 1.5` defining "close") is
still available everywhere via `--scoring superbru`; the default lives in
`config.SCORING_MODE`.

The key idea: the optimal pick is **not** the most likely scoreline. The model
computes the full probability matrix of scorelines and picks the one with the
highest expected points for the game mode and stage (e.g. under Penka a 2-1
pick collects the middle tier from 1-0 and 3-2 as well, because they share its
goal difference).

## Install

```bash
pip install -e .
wcpred update-data        # downloads data/input/results.csv (run before every session)
```

## Quick start

```bash
# 1. Pure history-based model (no external data needed)
wcpred predict --approach history --days 3

# 2. With betting odds (recommended — strongest signal available)
wcpred predict --approach odds --odds data/input/odds.csv --days 3

# 3. Everything at once
wcpred predict --approach full --odds data/input/odds.csv --xg data/input/xg.csv \
               --out picks.csv

# 4. Tournament-level odds: group standings and the full bracket
wcpred groups
wcpred simulate --approach odds --odds data/input/odds.csv
```

All generated files live under `data/` (kept out of the project root): inputs in
`data/input/` (`results.csv`, `odds.csv`, `xg.csv`), prediction CSVs in
`data/predictions/`, group standings in `data/groups/`, tournament simulations
in `data/simulations/`. A bare `--out` filename is placed in the right folder
automatically (e.g. `--out picks.csv` → `data/predictions/picks.csv`); pass a
path with a directory to override.

**Track how picks evolve** — `scripts/generate_predictions.sh` regenerates
predictions, group standings and the full-tournament simulation with a
date-stamped filename, so daily runs accumulate instead of overwriting:

```bash
scripts/generate_predictions.sh                 # → data/predictions/picks_<approach>_<date>.csv
                                                #   data/groups/groups_<approach>_<date>.csv
                                                #   data/simulations/sim_<approach>_<date>.csv
scripts/generate_predictions.sh --help          # all options
```

It defaults to `--approach odds` when `data/input/odds.csv` exists (else
`history`) and wires in the standard `data/input/` files automatically. The stamp
is the `--as-of` date (today by default); use `--time` to also keep multiple runs
within a day.

Re-run any time during the tournament: `update-data` pulls the latest
results (the dataset updates daily), training always uses everything played
before `--as-of` (default: today), and `predict` covers only fixtures that
haven't been played yet — so group-stage results automatically inform your
knockout picks.

## Web app

A local 538-style dashboard over the date-stamped CSVs (Spanish UI, flags,
odds toggle):

```bash
pip install -e '.[web]'        # or: uv sync --extra web
scripts/run_webapp.sh          # → http://localhost:8026
```

Four views: advancement probabilities per round (full-tournament simulation),
day-by-day evolution of those probabilities across snapshots, group-stage
position probabilities, and a round-by-round calendar showing each match's
prediction *as of its date*, market odds, and — once played — the real score
graded against the pick. Clicking a match opens the full exact-score
probability matrix (computed on demand with the model as of that date). The «Cuotas de mercado» toggle switches between the
`odds` and `history` CSV variants, and «Actualizar datos» runs
`generate_predictions.sh --refresh` for both variants from the browser.
Backend: `webapp/server.py` (FastAPI); it re-reads the CSVs on every request,
so manual `generate_predictions.sh` runs show up on reload.

## Commands

| Command | What it does |
|---|---|
| `wcpred update-data` | Download/refresh `results.csv` (int. results since 1872 + WC2026 fixtures) |
| `wcpred predict` | Predict upcoming WC fixtures; `--days N` limits horizon, `--out FILE` saves CSV |
| `wcpred groups` | Monte Carlo group standings; matches already played count with their real result |
| `wcpred simulate` | Full-tournament Monte Carlo (groups → best thirds → bracket → champion), also using real results where played |
| `wcpred ratings` | Show current attack/defence/overall ratings per team |
| `wcpred backtest` | Score the model on past tournaments (`--tournament all` or wc2018/euro2021/copa2021/wc2022/euro2024/copa2024) |
| `wcpred tune` | Grid-search training hyperparameters across all backtest tournaments |

## Approaches (`--approach`)

| Approach | Sources used | When to use |
|---|---|---|
| `history` | Match results only | Baseline; always works |
| `odds` | History + market 1X2 odds | **Best accuracy.** Use whenever odds exist |
| `xg` | History with goals blended with xG | If you have an xG dataset (see below) |
| `full` | All of the above | Whatever files you pass get used |

### How each source is integrated

- **Model core**: Dixon-Coles — weighted Poisson with attack/defence rating
  per team, time decay (half-life 2 years), home advantage for the three
  hosts in their own country, and the rho correction for low-scoring draws.
  Trained on ~11k internationals since 2015 (friendlies at full weight since
  the June 2026 tuning run).
- **Odds**: the bookmaker margin is stripped from the 1X2 odds and the clean
  probabilities are turned into a market-implied scoreline matrix
  (recalibrating the Poisson rates to match the market). By default the 1X2
  probabilities come **100% from the market** (`ODDS_WEIGHT = 1.0`); the model
  only shapes the scoreline distribution within each outcome (odds carry no
  scoreline info). Use `--odds-weight` to blend the model back in.
- **xG**: training targets become `0.6*goals + 0.4*xG` where available —
  xG is less noisy than goals, improving the underlying ratings.

## Getting the data

> Source coverage, historical cutoffs and gotchas are documented in
> [`docs/data-sources.md`](docs/data-sources.md).

**Refresh everything at once (incrementally):**

```bash
scripts/update_data.sh           # results + xG + odds into data/input/
scripts/update_data.sh --help    # options: --xg-window, --full-xg, --skip-*
```

It re-downloads `results.csv`, tops up `xg.csv` (re-fetching the last ~2 weeks
so late-finishing matches are picked up) and upserts `odds.csv` when
`ODDS_API_KEY` is set. Each source is independent; a failure in one is reported
but doesn't stop the others. The individual sources are described below.

### Results (automatic)
`wcpred update-data` downloads the
[martj42/international_results](https://github.com/martj42/international_results)
dataset (updated daily, includes the WC2026 schedule).

### Odds (`data/input/odds.csv`)
Format — American or decimal odds both work:

```csv
home_team,away_team,odds_1,odds_X,odds_2
Mexico,South Africa,-235,+375,+800
Brazil,Morocco,1.67,3.90,5.50
```

Two ways to fill it:
1. **Automatic**: `python scripts/fetch_odds.py` (writes `data/input/odds.csv`)
   using a free [The Odds API](https://the-odds-api.com) key
   (`export ODDS_API_KEY=...`, 500 free requests/month is plenty). Takes the
   median across bookmakers.
2. **Manual**: copy from
   [oddschecker](https://www.oddschecker.com/us/soccer/world-cup) —
   ~1 minute per matchday. Odds firm up 1-2 days before each match;
   the closer to kickoff, the sharper they are.

Team names must match the dataset (`United States`, `South Korea`,
`Czech Republic`, `Ivory Coast`, `Turkey`).

### xG (`data/input/xg.csv`) — optional
Format:

```csv
date,home_team,away_team,home_xg,away_xg
2025-09-05,Spain,Bulgaria,2.8,0.4
```

**Automatic**: `python scripts/fetch_xg.py --from 2023-01-01 --to <today>`
pulls international xG from [FotMob](https://www.fotmob.com)'s public JSON API
(no key needed) — friendlies, qualifiers, continental cups and the World Cup.
It writes `data/input/xg.csv` directly in the format above.

> **Note:** FotMob runs its own xG model, so numbers won't match other
> providers exactly — fine here, since xG only nudges the ratings and is
> blended with goals.

Matches without xG rows simply train on goals — partial coverage is fine, so a
narrow date range to top up before a session works too.

## Validation

Backtests cover six tournaments — WC 2018, Euro 2021, Copa América 2021,
WC 2022, Euro 2024 and Copa América 2024 — under Penka scoring by default
(`--scoring superbru` for the old pool; each match's stage tier is derived
from the tournament format), re-fitting the model at every matchday exactly
as the live `--as-of` workflow does (pass `--static` for a single
pre-tournament fit). Besides points, each run reports the 1X2 ranked
probability score (RPS) and exact-score log-loss; those low-variance metrics
drive hyperparameter choices, with points as the tie-breaker (points alone
are too noisy on ~64 matches).

Current defaults score **594 Penka pts over 290 matches** (2.05/match,
37 exact scores; 295.5 pts at 1.02/match under Superbru). The upset-heavy
WC 2022 is the weakest tournament (1.53 Penka pts/match, 53% correct
outcomes — bookmaker favourites hit ~55% there).

```bash
wcpred backtest --tournament all   # or wc2018/euro2021/copa2021/wc2022/...
wcpred tune                        # grid: GD_CAP × HALF_LIFE_DAYS × FRIENDLY_WEIGHT
```

The June 2026 tuning run set `FRIENDLY_WEIGHT = 1.0` (down-weighting
friendlies hurt every metric) and rejected capping blowout margins
(`GD_CAP` stays off) — details in `docs/known-limitations.md`.

## Package layout

```
wcpred/
├── config.py        # hyperparameters and scoring constants
├── data.py          # download, loading, training-set preparation (incl. xG blend)
├── model.py         # Dixon-Coles fit + score matrices
├── scoring.py       # Penka/Superbru points and the optimal-pick search
├── odds.py          # odds conversion, margin removal, market-implied matrices
├── predict.py       # per-match and per-fixture-list pipelines
├── groups.py        # Monte Carlo group standings
├── tournament.py    # full-tournament Monte Carlo (bracket through the final)
├── thirds_table.py  # FIFA allocation of the 8 best thirds (auto-generated)
├── backtest.py      # historical tournament evaluation + `tune` grid search
└── cli.py           # the `wcpred` command
webapp/
├── server.py        # FastAPI backend (JSON API over data/ + refresh runner)
└── static/          # frontend (vanilla JS/SVG) + flags/ (48 country SVGs)
scripts/
├── update_data.sh          # incrementally refresh all data sources into data/input/
├── generate_predictions.sh # date-stamped predictions + standings + simulation
├── run_webapp.sh           # serve the local web app on :8026
├── fetch_odds.py           # data/input/odds.csv via The Odds API
├── fetch_xg.py             # data/input/xg.csv via FotMob's public JSON API
└── build_thirds_table.py   # regenerates wcpred/thirds_table.py
data/             # all generated files
├── input/        # results.csv, odds.csv, xg.csv
├── predictions/  # `predict --out` CSVs
├── groups/       # `groups --out` standings
└── simulations/  # `simulate --out` probability tables
```

## Notes & caveats

- Knockout rounds: Penka and Superbru score the 90-minute result, which is
  exactly what the model predicts — so the default ignores extra time. For
  pools that score the *final* knockout result, `predict --extra-time` plays
  the extra 30' (at 1/3 the scoring rate) on top of every regulation draw, and
  `--shootout` additionally resolves still-level ties as a penalty win. Both
  are **off by default**; do not use them for Penka or Superbru.
- The dataset takes a day or so to register just-played matches; predictions
  made the same morning still include everything up to yesterday.
- `--odds-weight` controls the market/model mix for the 1X2 probabilities:
  `1.0` (the default) is purely market-driven, `0` ignores odds entirely.
- `groups` and `simulate` rank teams by points, goal difference and goals
  scored; remaining ties are broken at random (head-to-head and disciplinary
  records are not modelled).
