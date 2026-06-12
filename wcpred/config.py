"""Global configuration for the World Cup predictor."""

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/results.csv"
)

# --- Generated-file locations (keep the project root clean) ---
INPUT_DIR = "data/input"              # results.csv, odds.csv, xg.csv
PREDICTIONS_DIR = "data/predictions"  # `predict --out`
GROUPS_DIR = "data/groups"            # `groups --out`
SIM_DIR = "data/simulations"          # `simulate --out`
RESULTS_PATH = f"{INPUT_DIR}/results.csv"
ODDS_PATH = f"{INPUT_DIR}/odds.csv"   # live odds (latest fetch)

# Time-capsule odds: every fetch also lands in ODDS_SNAPSHOT_DIR as
# odds_<YYYY-MM-DDTHHMM>.csv, so a past `--as-of` run can be reproduced with
# the odds actually in force then (data.resolve_odds_path). ODDS_CUTOVER is
# the latest same-day fetch time (local, Europe/Madrid) a regeneration may
# use — anything stamped later could already reflect that day's matches. The
# earliest WC2026 kickoff is 18:00 CEST (12:00 at the Eastern-region venues),
# so 17:00 keeps an hour of margin before any ball rolls.
ODDS_SNAPSHOT_DIR = f"{INPUT_DIR}/odds"
ODDS_CUTOVER = "17:00"

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
CROSS_CONF_WEIGHT = 1.0     # extra weight on inter-confederation matches —
                            # the "bridge" games anchoring AFC/OFC/... to the
                            # global scale (docs/known-limitations.md). 1.0 =
                            # off; sweep via `wcpred tune`.

# --- Blending weights ---
ODDS_WEIGHT = 1.0           # 1X2 marginals come 100% from the market; the model
                            # only shapes the score distribution *within* each
                            # outcome (odds carry no scoreline info). Override
                            # with --odds-weight to reintroduce the model.
XG_ALPHA = 0.6              # effective_goals = a*goals + (1-a)*xG

# --- Optional knockout resolution (off by default) ---
EXTRA_TIME_FRACTION = 1 / 3  # extra time ≈ 30 min vs 90 regulation

# --- Game-mode scoring ---
SCORING_MODE = "penka"      # default pool: picks maximise expected Penka
                            # points. "superbru" restores the old behaviour
                            # (CLI: --scoring superbru).

# Penka: exact score / goal-difference-or-draw / winner, with stage-dependent
# points (exact, gd_or_draw, winner). The middle tier is a correct outcome
# with the exact goal difference; any correct draw pick qualifies (GD = 0).
PENKA_STAGE_POINTS = {
    "group":   (5.0, 3.0, 2.0),
    "r32_r16": (8.0, 5.0, 3.0),    # Round of 32 and Round of 16
    "qf_plus": (11.0, 7.0, 5.0),   # quarter-finals onwards
}

# Superbru scoring
PTS_EXACT = 3.0
PTS_CLOSE = 1.5             # correct outcome + Closeness Index <= CLOSE_MAX
PTS_OUTCOME = 1.0
CLOSE_MAX = 1.5
