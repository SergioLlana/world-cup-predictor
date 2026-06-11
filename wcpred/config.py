"""Global configuration for the World Cup predictor."""

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/results.csv"
)

# --- Generated-file locations (keep the project root clean) ---
INPUT_DIR = "data/input"              # results.csv, odds.csv, xg.csv
PREDICTIONS_DIR = "data/predictions"  # `predict --out`
GROUPS_DIR = "data/groups"            # `groups --out`
RESULTS_PATH = f"{INPUT_DIR}/results.csv"

# --- Model hyperparameters (validated by `wcpred tune` across the six
# backtest tournaments 2018-2024; rolling re-fit confirmation) ---
HALF_LIFE_DAYS = 730        # match weight halves every 2 years
FRIENDLY_WEIGHT = 1.0       # friendlies count fully: weighting them down
                            # worsened RPS/log-loss/points in every grid combo
TRAIN_START = "2015-01-01"  # ignore older matches
MIN_MATCHES = 10            # drop teams with fewer matches
MAX_GOALS = 8               # score grid 0..MAX_GOALS
GD_CAP = None               # cap goal margin in training (e.g. 3 ⇒ 5-0 → 3-0);
                            # None = off. Counters blowout inflation vs minnows.

# --- Blending weights ---
ODDS_WEIGHT = 0.75          # market-implied matrix vs pure model
XG_ALPHA = 0.6              # effective_goals = a*goals + (1-a)*xG

# --- Optional knockout resolution (off by default) ---
EXTRA_TIME_FRACTION = 1 / 3  # extra time ≈ 30 min vs 90 regulation

# --- Superbru scoring ---
PTS_EXACT = 3.0
PTS_CLOSE = 1.5             # correct outcome + Closeness Index <= CLOSE_MAX
PTS_OUTCOME = 1.0
CLOSE_MAX = 1.5

# 2026 hosts get home advantage when playing in their own country
HOSTS = ("United States", "Mexico", "Canada")
