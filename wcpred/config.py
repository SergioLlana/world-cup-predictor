"""Global configuration for the World Cup predictor."""

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/results.csv"
)
# Sibling files of the same dataset. results.csv records knockout scores
# *after extra time* (pens excluded); Penka/Superbru and the 1X2 market settle
# on the 90-minute result. goalscorers.csv (goal minutes; stoppage time is
# recorded as the base minute, so minute >= 91 ⇔ extra time) plus
# shootouts.csv let data.load_results rebuild the 90' score.
GOALSCORERS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/goalscorers.csv"
)
SHOOTOUTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/shootouts.csv"
)

# --- Generated-file locations (keep the project root clean) ---
INPUT_DIR = "data/input"              # results.csv, odds.csv, xg.csv
PREDICTIONS_DIR = "data/predictions"  # `predict --out`
GROUPS_DIR = "data/groups"            # `groups --out`
SIM_DIR = "data/simulations"          # `simulate --out`
RANKINGS_DIR = "data/rankings"        # `ratings --out`
RESULTS_PATH = f"{INPUT_DIR}/results.csv"
GOALSCORERS_PATH = f"{INPUT_DIR}/goalscorers.csv"
SHOOTOUTS_PATH = f"{INPUT_DIR}/shootouts.csv"
ODDS_PATH = f"{INPUT_DIR}/odds.csv"   # live odds (latest fetch)

# Frozen-in-time odds: every fetch also lands in ODDS_SNAPSHOT_DIR as
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
SHRINKAGE_MODE = None       # regularize weakly-identified cross-confederation
                            # offsets via data augmentation (arXiv 2606.03805;
                            # rejected, docs/known-limitations.md). None =
                            # off (today's model). "phantom": one synthetic
                            # 1-1 draw per team vs a __phantom__ anchor team;
                            # "pseudo": fractional 1-1 draws between
                            # cross-confederation team pairs.
SHRINKAGE_WEIGHT = 0.5      # total synthetic weight per team, in
                            # match-equivalents (a real match today weighs 1).
                            # Inactive while SHRINKAGE_MODE is None; sweep via
                            # `wcpred tune --shrinkage`.
CONF_ANCHOR_BETA = 0.0      # two-timescale confederation re-anchoring
                            # (rejected, docs/known-limitations.md): blend
                            # each confederation's mean strength in the short-
                            # window fit toward the level a long-window fit
                            # assigns it (where bridge games are plentiful).
                            # 0 = off (today's model); 1 = adopt the long
                            # window's levels fully. Sweep via
                            # `wcpred tune --anchor`.
CONF_ANCHOR_HALF_LIFE_DAYS = 2920  # slow-timescale window for the level fit
                                   # (8y; bounded below by TRAIN_START)

# --- Bayesian engine (--engine bayes) ---
BAYES_DYNAMIC = False        # dynamic random-walk strengths
                             # (docs/bayesian-engine.md): replace the exponential
                             # time-decay weighting with an explicit random-walk
                             # evolution of each team's strength over time blocks,
                             # predicting from the most recent block. False =
                             # static (the decay-weighted offset-prior model, the
                             # bayes default); opt-in via --bayes-dynamic. No
                             # effect under --engine dc.
BAYES_TIME_BLOCK = "halfyear"  # random-walk block granularity when BAYES_DYNAMIC
                               # is on: "year" | "halfyear" | "quarter". Finer =
                               # more temporal resolution, slower MCMC.
BAYES_SIGMA_CONF_SCALE = 0.5   # half-normal prior scale on sigma_conf, the
                               # between-confederation offset spread
                               # (docs/bayesian-engine.md). 0.5 = today's
                               # bayes model exactly. Shrinking it toward 0 pins
                               # the bloc offsets near 0 (the user's "no bloc is
                               # systematically stronger" hypothesis in its
                               # strongest form), testing whether an externally
                               # constrained offset scale corrects the diagnosed
                               # CONMEBOL/CONCACAF-vs-UEFA bias. No effect under
                               # --engine dc. Sweep via --bayes-sigma-conf.
BAYES_PROPAGATE = True         # posterior propagation (docs/bayesian-engine.md):
                               # full posterior propagation — the score matrix is
                               # the *posterior mean of per-draw Dixon-Coles
                               # matrices* instead of one matrix built from the
                               # posterior-mean ratings (the plug-in path).
                               # Averaging over the MCMC draws carries the
                               # cross-bloc rating uncertainty (widest on the
                               # weakly-identified bridges) into the scorelines.
                               # DEFAULT-ON (2026-06-19, owner-directed): the
                               # honest posterior-predictive scoreline. It does
                               # NOT fix the cross-confederation bias but is
                               # accuracy-neutral (609 vs 604 Penka pts,
                               # RPS +0.0002, ll −0.0002 — a wash) and the
                               # principled Bayesian choice. Set False to recover
                               # the plug-in mean. No effect under --engine dc.
                               # SCOPE: shapes --approach history outputs only —
                               # with ODDS_WEIGHT=1.0 predict_match rebuilds the
                               # matrix from matrix_from_rates (the plug-in
                               # path), so odds-approach outputs (all the webapp
                               # serves) are identical either way. See
                               # docs/bayesian-engine.md.
BAYES_CACHE_DIR = "data/models"  # posterior cache for the bayes engine: each
                               # fit saves its draws to an .npz keyed by a hash
                               # of (Stan source, training data, sampler args),
                               # and an identical later fit loads them instead
                               # of re-sampling (~minutes → <1 s; same numbers,
                               # since the posterior means are recomputed from
                               # the same float64 draws). Local only, gitignored
                               # — delete the directory to force re-sampling.
BAYES_CONNECT_SHRINK = False   # connectivity-weighted offset shrinkage (rejected
                               # experiment, docs/connectivity.md). Scale
                               # each team's confederation offset by its bridge-
                               # match share (confederations.bridge_share), so a
                               # weakly-connected team (the AFC/OFC minnows that
                               # never play outside their pool) stops inheriting
                               # its bloc's level and anchors to the global scale
                               # instead — the Australia-inflation fix the uniform
                               # offset cannot reach (the uniform offset is pinned
                               # by the bloc ELITE's bridges and applied to all).
                               # False = today's bayes model (every team gets the
                               # FULL offset). Opt-in via --bayes-connect; uses a
                               # separate Stan file (dixon_coles_connect.stan) so
                               # the default model stays byte-regenerable. Static
                               # only (no --bayes-dynamic). No effect under
                               # --engine dc.
BAYES_CONNECT_REF = 0.4        # bridge share at which a team earns the FULL
                               # confederation offset/deviation: c = min(1,
                               # share / ref). Teams below it are attenuated
                               # proportionally. Lower = more teams fully trusted.
                               # Only used when BAYES_CONNECT_SHRINK; sweep via
                               # --bayes-connect-ref.
BAYES_CONNECT_BY = "bridge"    # which predictor drives the connectivity weight c
                               # (only used when BAYES_CONNECT_SHRINK):
                               #   "bridge" — bridge-match share
                               #             (confederations.bridge_share);
                               #             c = min(1, share / BAYES_CONNECT_REF).
                               #             REJECTED: Australia's bridge share is
                               #             high, so it is the wrong predictor.
                               #   "opp"    — weighted mean opponent
                               #             rating (schedule difficulty,
                               #             confederations.opponent_rating, from
                               #             a pre-fit dc); c = min(1, opp_rating /
                               #             BAYES_CONNECT_OPP_REF). Low opp_rating
                               #             (soft schedule, e.g. Australia) →
                               #             shrunk; this is the predictor that
                               #             separates inflated teams from
                               #             legitimate outliers (Spain/Argentina,
                               #             hard schedules). Set via
                               #             --bayes-connect-by.
BAYES_CONNECT_OPP_REF = 1.5    # opp_rating earning the full weight when
                               # BAYES_CONNECT_BY="opp": c = min(1, opp / ref).
                               # ~1.5 ≈ the WC-team p75; teams below it (soft
                               # schedules) are attenuated. Sweep via
                               # --bayes-connect-opp-ref.
BAYES_CONNECT_MODE = "offset"  # which quantity the connectivity weight c scales
                               # (only used when BAYES_CONNECT_SHRINK):
                               #   "offset"    (formulation A,
                               #                dixon_coles_connect.stan): scale
                               #                the confederation OFFSET — isolated
                               #                teams anchor toward the global
                               #                scale. REJECTED: a weak bloc's
                               #                offset is negative, so attenuating
                               #                it toward 0 raises that bloc.
                               #   "deviation" (formulation B,
                               #                dixon_coles_connect_dev.stan):
                               #                scale the team's own DEVIATION —
                               #                isolated teams are pulled toward
                               #                their confederation mean (partial
                               #                pooling). Set via --bayes-connect-mode.

# --- Elo engine (--engine elo) ---
# An Elo trained on results.csv (NOT scraped).
# Two extensions over plain eloratings.net: a per-confederation K multiplier and
# a long-term (median) Elo covariate (EL PAÍS "trayectoria histórica" feature). Each team's
# attack/defence is derived from its current + long-term Elo via a 4-parameter
# GAM-Poisson + Dixon-Coles calibration, so the rest of the pipeline is unchanged.
# Defaults reproduce the published eloratings.net rule. See docs/elo-engine.md.
ELO_HA = 100.0              # eloratings.net home-advantage points added to dr on
                           # home soil (0 at neutral venues). 100 = published rule.
ELO_BASE = 1500.0          # Elo seed for a team's first match.
ELO_TRAIN_START = "2006-01-01"  # raw-history start for the Elo *iteration* —
                           # deliberately earlier than TRAIN_START (2015, used for
                           # the goal-model calibration): ratings converge after
                           # ~30 matches and the long-term median needs a decade.
ELO_LONGTERM_YEARS = 10    # trailing window (years) for the long-term (median)
                           # Elo covariate (the regression-to-the-mean "trayectoria histórica").
ELO_CONF_K = {             # per-confederation K multiplier (the extension): a team
    "UEFA": 1.0,           # updates its rating by its OWN confederation's K on top
    "CONMEBOL": 1.0,       # of the tournament base K, so the two sides of a match
    "CONCACAF": 1.0,       # can move by different amounts. All 1.0 = pure
    "CAF": 1.0,            # eloratings.net (no bloc treatment); unknown-conf teams
    "AFC": 1.0,            # use 1.0. NOTE: non-unit values break Elo's zero-sum
    "OFC": 1.0,            # property (total rating mass shifts) — that is the
}                          # intended effect, not a bug, when the parameter is enabled.
ELO_K_SCALE = 1.0          # global multiplier on every tournament-tier K
                           # (ELO_K_TIERS), i.e. the Elo learning rate. 1.0 =
                           # the published eloratings.net rule. Explicit so
                           # `tune --elo-engine` can absorb a global-K effect
                           # directly instead of letting it leak through the
                           # per-confederation multipliers (June 2026: four
                           # conf-Ks piled onto the 2.0 grid ceiling for ~0 RPS
                           # gain — docs/elo-engine.md).
ELO_K_TIERS = {            # base K by tournament type (eloratings.net tiers);
    "world_cup": 60.0,     # tournament_k() maps the martj42 `tournament` string.
    "continental_final": 50.0,
    "qualifier": 40.0,     # WC + continental qualifiers (names ending
    "other": 30.0,         # "qualification")
    "friendly": 20.0,
}
ELO_K_FINALS = (           # continental / major-intercontinental finals → the
    "UEFA Euro",           # 'continental_final' (50) tier. Everything not matched
    "Copa América",        # here, by a qualifier suffix, or by the world_cup/
    "African Cup of Nations",   # friendly names falls through to 'other' (30).
    "AFC Asian Cup",
    "Gold Cup",
    "CONCACAF Championship",
    "Oceania Nations Cup",
    "Confederations Cup",
)

# --- Blending weights ---
ODDS_WEIGHT = 1.0           # 1X2 marginals come 100% from the market; the model
                            # only shapes the score distribution *within* each
                            # outcome (odds carry no scoreline info). Override
                            # with --odds-weight to reintroduce the model.
XG_ALPHA = 0.6              # effective_goals = a*goals + (1-a)*xG

# --- Optional knockout resolution (off by default) ---
EXTRA_TIME_FRACTION = 1 / 3  # extra time ≈ 30 min vs 90 regulation

# --- WC2026 knockout calendar: (first day, last day, round id) ---
# Single source of truth for the round boundaries: predict.wc2026_stage derives
# the Penka payout tiers from it and the webapp its round labels.
WC2026_KNOCKOUT_ROUNDS = (
    ("2026-06-28", "2026-07-03", "r32"),
    ("2026-07-04", "2026-07-08", "r16"),
    ("2026-07-09", "2026-07-12", "qf"),
    ("2026-07-13", "2026-07-16", "sf"),
    ("2026-07-17", "2026-07-18", "p3"),
    ("2026-07-19", "2026-07-31", "f"),
)

# --- Game-mode scoring ---
SCORING_MODE = "penka"      # default pool: picks maximise expected Penka
                            # points. "superbru" restores the old behaviour
                            # (CLI: --scoring superbru).

# --- Scoreline pick strategy ---
PICK_STRATEGY = "ev"        # how scoring.select_prediction turns a score matrix
                            # into a pick. "ev" = maximise expected points (the
                            # regenerable default — keeps past snapshots
                            # reproducible). "outcome" = strategy C: pick the
                            # most likely 1X2 outcome, then the most likely
                            # scoreline within it (CLI: --pick-strategy outcome;
                            # +8% Penka on the backtest, see docs/
                            # pick-strategy.md). The model is unchanged; this is
                            # only the post-probability pick step.

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
