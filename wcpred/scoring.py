"""Superbru scoring rules and optimal-pick selection."""
from functools import lru_cache

import numpy as np

from .config import CLOSE_MAX, PTS_CLOSE, PTS_EXACT, PTS_OUTCOME


def closeness_index(pred, true):
    """Superbru CI = |dGD| + |dTotalGoals| / 2 (lower is closer)."""
    ph, pa = pred
    th, ta = true
    return abs((ph - pa) - (th - ta)) + abs((ph + pa) - (th + ta)) / 2.0


def points(pred, true):
    """Official Superbru: 3 exact / 1.5 outcome+close / 1 outcome / 0."""
    if tuple(pred) == tuple(true):
        return PTS_EXACT

    def sign(d):
        return (d > 0) - (d < 0)
    if sign(pred[0] - pred[1]) == sign(true[0] - true[1]):
        return PTS_CLOSE if closeness_index(pred, true) <= CLOSE_MAX \
            else PTS_OUTCOME
    return 0.0


@lru_cache(maxsize=None)
def points_matrix(n):
    """M[p, t] = Superbru points for predicting score p when the true score is
    t, over all n*n scorelines flattened row-major (index = goals_h*n+goals_a).

    Cached per grid size so it is built once and reused across every match
    (e.g. all 64 backtest fixtures), turning best_prediction into a matvec."""
    scores = [(h, a) for h in range(n) for a in range(n)]
    M = np.empty((len(scores), len(scores)))
    for pi, pred in enumerate(scores):
        for ti, true in enumerate(scores):
            M[pi, ti] = points(pred, true)
    return M


def best_prediction(P):
    """Scoreline maximising expected Superbru points under matrix P."""
    n = P.shape[0]
    ep = points_matrix(n) @ P.ravel()
    k = int(np.argmax(ep))          # row-major flatten ⇒ same tie-break as before
    return (k // n, k % n), float(ep[k])


def outcome_probs(P):
    """(P_home_win, P_draw, P_away_win)."""
    return np.tril(P, -1).sum(), np.trace(P), np.triu(P, 1).sum()


# --- Optional knockout resolution (off by default; Superbru scores 90') -------

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
