# wcpred — FIFA World Cup 2026 score predictor

`wcpred` predicts scorelines for the 2026 World Cup and, for each match, picks the prediction that **maximises your expected points** in a prediction pool. The key idea: the best pick is **not** the most likely scoreline. The model builds the full probability matrix of scorelines and then chooses the one worth the most points on average.

It includes a command-line tool, a local dashboard, and a public website at **<https://wc-pred.com>**.

---

## Getting started

```bash
pip install -e .            # install the `wcpred` CLI
wcpred update-data          # download the match dataset (run before each session)
```

Make your first prediction:

```bash
wcpred predict --approach history --days 3          # history-only, no extra data
wcpred predict --approach odds --odds data/input/odds.csv --days 3   # + market odds (best)
```

Or start the dashboard:

```bash
pip install -e '.[web]'     # adds FastAPI + uvicorn
scripts/run_webapp.sh       # → http://localhost:8026
```

`run_webapp.sh` serves whatever CSVs are in your local `data/`. To instead see exactly what the public site is showing, pull the published data from S3 — either once, or automatically on startup:

```bash
scripts/aws/pull_data.sh    # sync data/ from the wcpred-data S3 bucket
scripts/run_webapp.sh --s3  # …or let the app pull on startup, then serve it
```

Both need the `wcpred` AWS profile configured (`aws configure --profile wcpred`, region `eu-south-2`). More on running it locally versus hosted is [below](#web-app).

---

## How it works

It works in five steps, from data to a pick:

1. **Data.** International match results since 1872 (the [martj42](https://github.com/martj42/international_results) dataset, updated daily and including the WC2026 schedule), plus optional betting odds and xG.
2. **Ratings.** A **Dixon-Coles** model — a weighted Poisson with an attack/defence rating per team, time decay (2-year half-life), a home edge for the three hosts, and a correction for low-scoring draws — fitted on ~11k internationals since 2015. Two alternative [engines](#engines) (`elo`, `bayes`) can be used instead.
3. **Score matrix.** The ratings give each fixture a full `P[home goals, away goals]` grid. When odds are supplied, the match-winner (1X2) probabilities are taken **from the market** and the model only shapes the scoreline distribution within each outcome.
4. **Pick.** From that matrix, pick the scoreline with the highest expected points for the pool's scoring rules and the match's stage — not the single most likely score. See [`docs/pick-strategy.md`](docs/pick-strategy.md).
5. **Tournament.** A Monte Carlo simulation plays the group stage, the best-thirds allocation and the knockout bracket many times to estimate each team's chance of reaching each round and winning. Matches already played enter with their real result, so group results feed the knockout picks automatically.

You can re-run everything each day: training always uses matches before `--as-of` (default today) and `predict` covers only unplayed fixtures. Full walkthrough: [`docs/models-explained.md`](docs/models-explained.md).

The `scripts/generate_*.sh` helpers write **date-stamped** CSVs so daily runs add to the collection instead of overwriting, which is what lets the dashboard chart how picks and ratings change over time:

```bash
scripts/generate_predictions.sh   # picks + group standings + tournament sim, per day
scripts/generate_rankings.sh      # team-strength rankings, per engine per day
```

---

## Web app

A web dashboard (bilingual EN/ES) over the date-stamped CSVs. Views: advancement probabilities per round and their day-by-day evolution, group positions, a round-by-round calendar showing each match's prediction *as of its date* (and, once played, the real score graded against the pick), a **Rankings** tab with an evolution chart, a **connectivity** view, and a **How it works** explainer. Clicking a match opens its full exact-score probability matrix. Backend: `webapp/server.py` (FastAPI), re-reading the CSVs on every request.

### Local vs. hosted

Same app, three ways to run it — they differ only in **where the data comes from** and whether the editing tools are available:

| | Data source | UI | How |
|---|---|---|---|
| **Local, your data** | CSVs you generate under `data/` | full (refresh, Connectivity, EV/outcome toggle) | `scripts/run_webapp.sh` |
| **Local, live data** | pulled from the `wcpred-data` S3 bucket on startup | full | `scripts/run_webapp.sh --s3` |
| **Hosted, public** | static export of the S3 data, rebuilt by the pipeline | restricted public mode | <https://wc-pred.com> |

The **hosted** site runs in a restricted public mode (`WCPRED_PUBLIC=1`): no refresh, no Connectivity tab, and it shows the most likely scoreline instead of the points-maximising pick. Preview it locally with `WCPRED_PUBLIC=1 uvicorn webapp.server:app --port 8027`.

### Updating the hosted site

The public site is a set of pre-built static files on S3 + CloudFront (no server to keep running), at `wc-pred.com` and the CloudFront URL `d1h6wbyne03264.cloudfront.net`. A daily job on **ECS Fargate** does everything automatically — pull data, refresh sources, regenerate all engines (`bayes` MCMC included), export and publish. Run it once the day's results have appeared on martj42 (region `eu-south-2`, profile `wcpred`):

```bash
scripts/aws/run_pipeline.sh          # launch the Fargate task
scripts/aws/run_pipeline.sh --wait   # …and block until it finishes
aws logs tail /wcpred/pipeline --follow   # watch it
```

> The date-stamped CSVs under `data/` are **not** committed to git — the versioned `wcpred-data` S3 bucket is the source of truth. Pull them with `scripts/aws/pull_data.sh`; the pre-migration history stays in git.

---

## Input data

All inputs live in `data/input/`. Refresh everything at once (incrementally):

```bash
scripts/update_data.sh           # results + xG + odds
scripts/update_data.sh --help    # --xg-window, --full-xg, --skip-*
```

### Results — `results.csv` (required, automatic)

`wcpred update-data` downloads the [martj42/international_results](https://github.com/martj42/international_results) dataset: every international since 1872 plus the WC2026 fixtures, updated daily. This is the only input the model strictly needs. Note the dataset takes a day or so to register a just-played match.

### Odds — `odds.csv` (recommended)

The most useful extra input. Format (American or decimal both work):

```csv
home_team,away_team,odds_1,odds_X,odds_2
Mexico,South Africa,-235,+375,+800
Brazil,Morocco,1.67,3.90,5.50
```

Fill it either automatically with `python scripts/fetch_odds.py` (a free [The Odds API](https://the-odds-api.com) key via `ODDS_API_KEY`; takes the median across bookmakers), or manually from [oddschecker](https://www.oddschecker.com/us/soccer/world-cup) (~1 min per matchday). Odds become more reliable 1-2 days before kickoff. Each fetch also saves a dated copy under `data/input/odds/`, so regenerating a past day (`--as-of DATE`) uses the odds that were available that day, not later ones. Team names must match the dataset exactly (`United States`, `South Korea`, `Czech Republic`, `Ivory Coast`, `Turkey`).

### xG — `xg.csv` (optional)

```csv
date,home_team,away_team,home_xg,away_xg
2025-09-05,Spain,Bulgaria,2.8,0.4
```

`python scripts/fetch_xg.py --from 2023-01-01 --to <today>` pulls international xG from [FotMob](https://www.fotmob.com)'s public JSON API (no key). xG is mixed into the training targets (`0.6*goals + 0.4*xG` where present) to make the ratings less noisy; partial coverage is fine. FotMob runs its own xG model, so numbers won't match other providers exactly — acceptable here, since xG only slightly adjusts the ratings.

---

## Scoring

The default scoring mode is **Penka**, which pays three tiers with stakes that grow by stage:

| Result | Group stage | R32 & R16 | QF onwards |
|---|---|---|---|
| Exact score | 5 | 8 | 11 |
| Goal difference or draw | 3 | 5 | 7 |
| Match winner only | 2 | 3 | 5 |

The original **Superbru** mode (3 exact / 1.5 outcome+close / 1 outcome, where "close" is the Closeness Index `|ΔGoalDiff| + |ΔTotalGoals| / 2 ≤ 1.5`) is available everywhere via `--scoring superbru`. The default lives in `config.SCORING_MODE`. The scoring rules are exactly what makes the best pick differ from the most likely scoreline — see [`docs/pick-strategy.md`](docs/pick-strategy.md).

---

## Commands

| Command | What it does |
|---|---|
| `wcpred update-data` | Download/refresh `results.csv` (internationals since 1872 + WC2026 fixtures) |
| `wcpred predict` | Predict upcoming WC fixtures; `--days N` limits horizon, `--out FILE` saves CSV |
| `wcpred groups` | Monte Carlo group standings; played matches count with their real result |
| `wcpred simulate` | Full-tournament Monte Carlo (groups → best thirds → bracket → champion) |
| `wcpred ratings` | Show current attack/defence/overall ratings per team |
| `wcpred backtest` | Score the model on past tournaments (`--tournament all` or a single one) |
| `wcpred tune` | Grid-search training hyperparameters across all backtest tournaments |

Generated files are routed under `data/` automatically: a bare `--out picks.csv` lands in `data/predictions/`; pass a path with a directory to override.

### Approaches

| Approach | Sources used | When to use |
|---|---|---|
| `history` | Match results only | Baseline; always works |
| `odds` | History + market 1X2 odds | **Best accuracy.** Use whenever odds exist |
| `xg` | History with goals blended with xG | If you have an xG dataset |
| `full` | All of the above | Whatever files you pass get used |

Set with `--approach`. By default the 1X2 probabilities come **100% from the market** (`ODDS_WEIGHT = 1.0`); the model only shapes scorelines within each outcome. Blend the model back in with `--odds-weight` (`0` ignores odds entirely).

### Engines

Three interchangeable engines feed the same later steps, selected with `--engine`:

| Engine | What it is | When |
|---|---|---|
| `dc` (default) | Dixon-Coles MLE, the regenerable production model | Always |
| `elo` | An Elo trained on results + a Dixon-Coles goal calibration | Alternative ratings |
| `bayes` | Stan hierarchical Dixon-Coles (confederation-offset prior); slow, needs `.[bayes]` + CmdStan | Uncertainty-aware, local only |

Details: [`docs/elo-engine.md`](docs/elo-engine.md),
[`docs/bayesian-engine.md`](docs/bayesian-engine.md).

---

## Validation

Backtests cover six past tournaments — WC 2018, Euro 2021, Copa América 2021, WC 2022, Euro 2024 and Copa América 2024 — re-fitting the model at every matchday exactly as the live `--as-of` workflow does (`--static` for a single pre-tournament fit). Besides points, each run reports the 1X2 ranked probability score (RPS) and exact-score log-loss; those low-variance metrics guide the tuning choices, with points as the tie-breaker.

Current defaults score **~566 Penka points over 290 matches** (scoring the 90-minute result, the Penka/Superbru convention). The upset-heavy WC 2022 is the weakest tournament — even the bookmaker favourites were right only ~55% of the time there.

```bash
wcpred backtest --tournament all   # or wc2018/euro2021/copa2021/wc2022/...
wcpred tune                        # grid: GD_CAP × HALF_LIFE_DAYS × FRIENDLY_WEIGHT
```

The June 2026 tuning run set `FRIENDLY_WEIGHT = 1.0` and rejected capping blowout margins (`GD_CAP` stays off) — see [`docs/known-limitations.md`](docs/known-limitations.md).

---

## Documentation

All under [`docs/`](docs/):

| Doc | What it covers |
|---|---|
| [`models-explained.md`](docs/models-explained.md) | End-to-end walkthrough of the model and pipeline |
| [`elo-engine.md`](docs/elo-engine.md) | The `--engine elo` engine + its tuning |
| [`bayesian-engine.md`](docs/bayesian-engine.md) | The `--engine bayes` Stan engine + its tuning |
| [`pick-strategy.md`](docs/pick-strategy.md) | Turning the score matrix into a pick (`ev` vs `outcome`) |
| [`data-sources.md`](docs/data-sources.md) | Where each input comes from, coverage, gotchas |
| [`known-limitations.md`](docs/known-limitations.md) | Modelling limitations and rejected mitigations |
| [`connectivity.md`](docs/connectivity.md) | Reading cross-confederation comparisons |
| [`aws-migration-plan.md`](docs/aws-migration-plan.md) | The S3 + CloudFront + Fargate deployment |
| [`webapp-public-deploy-plan.md`](docs/webapp-public-deploy-plan.md) | Public bilingual deployment plan |

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
├── update_data.sh          # incrementally refresh all data sources
├── generate_predictions.sh # date-stamped predictions + standings + simulation
├── generate_rankings.sh    # date-stamped model rankings (per engine)
├── run_webapp.sh           # serve the local web app on :8026 (--s3 to pull from S3)
├── fetch_odds.py           # data/input/odds.csv via The Odds API
├── fetch_xg.py             # data/input/xg.csv via FotMob's public JSON API
├── aws/                    # pull_data.sh, run_pipeline.sh, publish_site.sh, …
└── experiments/            # dev-only scripts
data/                       # all generated files (gitignored; S3 is source of truth)
├── input/                  # results.csv, odds.csv, xg.csv
├── predictions/ groups/ simulations/ rankings/   # date-stamped snapshots
└── matrices/ models/       # precomputed score matrices / bayes posterior cache
```

## Notes & caveats

- **Knockout rounds** score the 90-minute result, which is what the model predicts — so extra time is off by default. For pools that score the *final* result, `predict --extra-time` plays the extra 30' (at 1/3 goal rate) and `--shootout` resolves still-level ties; do **not** use them for Penka/Superbru.
- **`groups`/`simulate`** rank teams by points, goal difference and goals scored.
- **Cross-confederation comparisons** are weakest where few matches bridge confederations, which can inflate schedule-easy teams — see the Connectivity tab and [`docs/known-limitations.md`](docs/known-limitations.md).
