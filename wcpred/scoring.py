"""Game-mode scoring rules (Penka, Superbru) and optimal-pick selection."""
from functools import lru_cache

import numpy as np

from .config import (CLOSE_MAX, PENKA_STAGE_POINTS, PICK_STRATEGY, PTS_CLOSE,
                     PTS_EXACT, PTS_OUTCOME, SCORING_MODE)

SCORING_MODES = ("penka", "superbru")
STAGES = tuple(PENKA_STAGE_POINTS)      # group, r32_r16, qf_plus


def _sign(d):
    return (d > 0) - (d < 0)


def closeness_index(pred, true):
    """Superbru CI = |dGD| + |dTotalGoals| / 2 (lower is closer)."""
    ph, pa = pred
    th, ta = true
    return abs((ph - pa) - (th - ta)) + abs((ph + pa) - (th + ta)) / 2.0


def points_superbru(pred, true):
    """Official Superbru: 3 exact / 1.5 outcome+close / 1 outcome / 0."""
    if tuple(pred) == tuple(true):
        return PTS_EXACT
    if _sign(pred[0] - pred[1]) == _sign(true[0] - true[1]):
        return PTS_CLOSE if closeness_index(pred, true) <= CLOSE_MAX \
            else PTS_OUTCOME
    return 0.0


def points_penka(pred, true, stage="group"):
    """Penka: exact / goal-difference-or-draw / winner / 0, with the points of
    each tier set by the stage (PENKA_STAGE_POINTS). The middle tier needs the
    exact goal difference; a correct draw pick always has it (GD = 0)."""
    exact, gd, winner = PENKA_STAGE_POINTS[stage]
    if tuple(pred) == tuple(true):
        return exact
    if _sign(pred[0] - pred[1]) == _sign(true[0] - true[1]):
        return gd if pred[0] - pred[1] == true[0] - true[1] else winner
    return 0.0


def points(pred, true, mode=SCORING_MODE, stage="group"):
    """Points for picking `pred` when the real score is `true`. `stage` only
    matters for Penka, whose tiers pay more the deeper the round."""
    if mode == "superbru":
        return points_superbru(pred, true)
    return points_penka(pred, true, stage)


@lru_cache(maxsize=None)
def points_matrix(n, mode=SCORING_MODE, stage="group"):
    """M[p, t] = points for predicting score p when the true score is t,
    over all n*n scorelines flattened row-major (index = goals_h*n+goals_a).

    Cached per (grid size, mode, stage) so it is built once and reused across
    every match (e.g. all 64 backtest fixtures), turning best_prediction into
    a matvec."""
    scores = [(h, a) for h in range(n) for a in range(n)]
    M = np.empty((len(scores), len(scores)))
    for pi, pred in enumerate(scores):
        for ti, true in enumerate(scores):
            M[pi, ti] = points(pred, true, mode, stage)
    return M


def best_prediction(P, mode=SCORING_MODE, stage="group"):
    """Scoreline maximising expected points under matrix P. Penka picks can
    depend on the stage: the exact/GD/winner payout ratios differ slightly
    between the three tiers (5:3:2 vs 8:5:3 vs 11:7:5)."""
    n = P.shape[0]
    ep = points_matrix(n, mode, stage) @ P.ravel()
    k = int(np.argmax(ep))          # row-major flatten ⇒ same tie-break as before
    return (k // n, k % n), float(ep[k])


def outcome_probs(P):
    """(P_home_win, P_draw, P_away_win)."""
    return np.tril(P, -1).sum(), np.trace(P), np.triu(P, 1).sum()


def best_prediction_outcome(P, mode=SCORING_MODE, stage="group"):
    """Strategy C: pick the most likely 1X2 outcome, then the single most
    likely scoreline *within* that outcome.

    Beats pure expected-value (`best_prediction`) on Penka because the EV
    optimiser is too conservative — it defaults to 1-0 — while this picks the
    favourite's most likely actual winning scoreline (2-0, 2-1, ...), catching
    more exact/GD hits. +8% Penka on the 290-match backtest. See
    docs/pick-strategy.md. `mode`/`stage` only set the reported expected
    points; they do not change the pick (which is purely the modal scoreline of
    the modal outcome)."""
    n = P.shape[0]
    p1, px, p2 = outcome_probs(P)
    mask = np.zeros_like(P)
    if px >= p1 and px >= p2:
        np.fill_diagonal(mask, 1.0)            # draw most likely → diagonal
    elif p1 >= p2:
        mask = np.tril(np.ones_like(P), -1)    # home win → below diagonal
    else:
        mask = np.triu(np.ones_like(P), 1)     # away win → above diagonal
    k = int(np.argmax((P * mask).ravel()))
    ep = float(points_matrix(n, mode, stage)[k] @ P.ravel())
    return (k // n, k % n), ep


PICK_STRATEGIES = {"ev": best_prediction, "outcome": best_prediction_outcome}


def select_prediction(P, mode=SCORING_MODE, stage="group",
                      strategy=PICK_STRATEGY):
    """Dispatch to the configured scoreline pick strategy ("ev" / "outcome")."""
    return PICK_STRATEGIES[strategy](P, mode, stage)


# --- Optional knockout resolution (off by default; Penka and Superbru score
# the 90-minute result) ---------------------------------------------------------

def resolve_extra_time(P, P_et):
    """Turn a 90-minute score matrix into a final-result matrix by playing the
    extra 30' on top of every regulation draw.

    Each regulation draw d-d (prob `draws[d]`) is spread by the extra-time goal
    distribution `P_et`, shifting the scoreline to (d+h, d+a). Decisive 90'
    results pass through untouched. Mass that is still level after ET stays on
    the diagonal — those are ties headed for penalties; see resolve_shootout."""
    n = P.shape[0]
    draws = np.diag(P).copy()
    out = P.copy()
    np.fill_diagonal(out, 0.0)
    for d in range(n):
        if draws[d] == 0.0:
            continue
        for h in range(n - d):
            for a in range(n - d):
                out[d + h, d + a] += draws[d] * P_et[h, a]
    return out / out.sum()


def resolve_shootout(P):
    """Resolve ties still level after extra time as a penalty shootout: the
    recorded scoreline becomes a one-goal win, split 50/50 home/away."""
    n = P.shape[0]
    level = np.diag(P).copy()
    out = P.copy()
    np.fill_diagonal(out, 0.0)
    for d in range(n):
        if level[d] == 0.0:
            continue
        # at the top of the grid the winner stays at d and the loser drops
        w, lo = (d + 1, d) if d + 1 < n else (d, d - 1)
        out[w, lo] += level[d] / 2.0
        out[lo, w] += level[d] / 2.0
    return out / out.sum()
