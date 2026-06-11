"""Backtesting and hyperparameter tuning on past tournaments.

Reported metrics per tournament:
- Superbru points (the thing we ultimately care about — but noisy on ~64
  matches, so don't tune on it alone);
- mean 1X2 ranked probability score (RPS, lower is better);
- mean exact-score log-loss (lower is better).
RPS/log-loss have far lower variance than points, so they drive tuning;
points decide between configs the probabilistic metrics can't separate.
"""
import numpy as np
import pandas as pd

from .config import MAX_GOALS
from .data import prepare_training
from .model import DixonColes
from .predict import home_side, predict_match
from .scoring import points

# as_of (first matchday), window, exact tournament name in results.csv.
# Names must be exact: Euro and Copa América overlap in summer 2021/2024,
# so a loose "Euro|Copa" pattern would mix the two tournaments.
TOURNAMENTS = {
    "wc2018":   ("2018-06-14", "2018-06-01", "2018-07-31", "FIFA World Cup"),
    "euro2021": ("2021-06-11", "2021-06-01", "2021-07-31", "UEFA Euro"),
    "copa2021": ("2021-06-13", "2021-06-01", "2021-07-31", "Copa América"),
    "wc2022":   ("2022-11-19", "2022-11-01", "2022-12-31", "FIFA World Cup"),
    "euro2024": ("2024-06-14", "2024-06-01", "2024-07-31", "UEFA Euro"),
    "copa2024": ("2024-06-20", "2024-06-15", "2024-07-31", "Copa América"),
}

# Lookback matching what the 2026 setup gets from TRAIN_START="2015-01-01",
# so older tournaments (wc2018) train on a comparable span of history.
TRAIN_WINDOW_YEARS = 11


def _match_metrics(res, true):
    """(superbru_points, exact_score_log_loss, 1X2_rps) for one match."""
    p = points(res["pick"], true)
    h, a = min(true[0], MAX_GOALS), min(true[1], MAX_GOALS)
    ll = -np.log(max(res["P"][h, a], 1e-12))
    d = true[0] - true[1]
    o1, ox = float(d > 0), float(d == 0)
    rps = 0.5 * ((res["p1"] - o1) ** 2
                 + (res["p1"] + res["px"] - o1 - ox) ** 2)
    return p, ll, rps


def backtest(df, tournament="wc2022", rolling=True, xg_path=None,
             xg_alpha=None, **train_kw):
    """Score every match of a past tournament.

    rolling=True re-fits the model at each matchday (training on matches
    strictly before it, so earlier tournament results feed later picks) —
    the same way `--as-of` is used live. rolling=False fits once
    pre-tournament. Host teams get home advantage, as in the live pipeline.
    Extra train_kw (half_life, friendly_weight, gd_cap, ...) reach
    prepare_training.
    """
    as_of, start, end, name = TOURNAMENTS[tournament]
    matches = df.dropna(subset=["home_score"])
    matches = matches[matches["date"].between(start, end)
                      & (matches["tournament"] == name)].sort_values("date")

    kw = dict(train_kw)
    if xg_alpha is not None:
        kw["xg_alpha"] = xg_alpha
    kw.setdefault("train_start", str(
        (pd.Timestamp(as_of) - pd.DateOffset(years=TRAIN_WINDOW_YEARS)).date()))

    model, fitted_at = None, None
    total, exact, outcome = 0.0, 0, 0
    lls, rpss = [], []
    for _, r in matches.iterrows():
        cutoff = str(r["date"].date()) if rolling else as_of
        if cutoff != fitted_at:
            model = DixonColes().fit(
                prepare_training(df, cutoff, xg_path=xg_path, **kw))
            fitted_at = cutoff
        side = home_side(r.home_team, r.away_team, r.country)
        res = predict_match(model, r.home_team, r.away_team, side=side)
        true = (int(r.home_score), int(r.away_score))
        p, ll, rps = _match_metrics(res, true)
        total += p
        exact += p == 3.0
        outcome += p > 0
        lls.append(ll)
        rpss.append(rps)
    n = len(matches)
    return {"tournament": tournament, "matches": n, "points": total,
            "points_per_match": total / n, "exact": exact,
            "outcome_correct": outcome, "log_loss": float(np.mean(lls)),
            "rps": float(np.mean(rpss))}


def tune(df, tournaments=None, gd_caps=(None, 3, 4),
         half_lives=(365, 545, 730, 1095), friendly_weights=(0.5, 0.75, 1.0),
         cross_conf_weights=(1.0,), rolling=False, verbose=True):
    """Grid-search training hyperparameters across tournaments (no xG).

    Static fit by default to keep the grid cheap; re-validate the winner
    with rolling=True afterwards. Returns a DataFrame sorted by pooled RPS,
    with per-match-pooled metrics across all tournaments.
    """
    tournaments = list(tournaments or TOURNAMENTS)
    rows = []
    for cap in gd_caps:
        for hl in half_lives:
            for fw in friendly_weights:
                for ccw in cross_conf_weights:
                    res = [backtest(df, t, rolling=rolling, gd_cap=cap,
                                    half_life=hl, friendly_weight=fw,
                                    cross_conf_weight=ccw)
                           for t in tournaments]
                    n = sum(r["matches"] for r in res)
                    row = {
                        "gd_cap": cap, "half_life": hl, "friendly_w": fw,
                        "cross_conf_w": ccw,
                        "points": sum(r["points"] for r in res),
                        "pts_per_match": sum(r["points"] for r in res) / n,
                        "exact": sum(r["exact"] for r in res),
                        "rps": sum(r["rps"] * r["matches"] for r in res) / n,
                        "log_loss": sum(r["log_loss"] * r["matches"]
                                        for r in res) / n,
                    }
                    rows.append(row)
                    if verbose:
                        print(f"gd_cap={cap} half_life={hl} friendly_w={fw} "
                              f"cross_conf_w={ccw}: "
                              f"{row['pts_per_match']:.3f} pts/match, "
                              f"rps {row['rps']:.4f}, ll {row['log_loss']:.4f}")
    return (pd.DataFrame(rows)
            .sort_values("rps").reset_index(drop=True))
