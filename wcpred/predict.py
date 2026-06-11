"""High-level prediction pipeline combining model and odds."""
import pandas as pd

from .config import EXTRA_TIME_FRACTION, ODDS_WEIGHT
from .odds import devig, market_matrix, to_prob
from .scoring import (best_prediction, outcome_probs, resolve_extra_time,
                      resolve_shootout)


def home_side(home_team, away_team, venue_country):
    """Which listed side is playing on home soil (gets the home-advantage
    boost), or None for a neutral venue.

    A team is at home iff the match is played in its own country — independent
    of which side the fixture lists as 'home'. At a World Cup that means a host
    nation (USA, Mexico, Canada) playing in its own country; in the knockouts
    the host can be the listed away team yet still be the one at home."""
    if home_team == venue_country:
        return "home"
    if away_team == venue_country:
        return "away"
    return None


def predict_match(model, home, away, side=None, odds=None,
                  odds_weight=ODDS_WEIGHT, extra_time=False, shootout=False):
    """Predict one match.

    side: 'home', 'away' or None — which listed team is on home soil.
    odds: (odds_1, odds_X, odds_2) American or decimal, or None.
    extra_time/shootout: optional knockout resolution. Off by default because
    Superbru scores the 90-minute result; enable only for pools that score the
    final knockout result. shootout implies extra_time.
    Returns dict with score matrix, optimal Superbru pick, expected points
    and 1X2 probabilities.
    """
    P = model.score_matrix(home, away, home_side=side)
    used_odds = False
    if odds is not None and all(pd.notna(o) for o in odds):
        probs = devig(*[to_prob(o) for o in odds])
        P_mkt = market_matrix(model, home, away, probs, side)
        P = odds_weight * P_mkt + (1 - odds_weight) * P
        P = P / P.sum()
        used_odds = True
    if extra_time or shootout:
        lam, mu = model.rates(home, away, side)
        P_et = model.matrix_from_rates(lam * EXTRA_TIME_FRACTION,
                                       mu * EXTRA_TIME_FRACTION)
        P = resolve_extra_time(P, P_et)
        if shootout:
            P = resolve_shootout(P)
    pick, ep = best_prediction(P)
    p1, px, p2 = outcome_probs(P)
    return {"P": P, "pick": pick, "expected_points": ep,
            "p1": p1, "px": px, "p2": p2, "used_odds": used_odds}


def _norm_team(name):
    """Normalise a team name for odds matching: tolerate '&' vs 'and' and
    stray whitespace. Fixtures follow the martj42 dataset spelling, but the
    odds feed sometimes uses 'Bosnia & Herzegovina' etc."""
    return " ".join(str(name).replace("&", "and").split())


def _build_odds_lookup(odds_df):
    """Map normalised (home, away) -> (odds_1, odds_X, odds_2). Also indexes
    the reversed pairing with odds_1/odds_2 swapped, so a fixture listed in the
    opposite home/away order to the odds feed still matches correctly."""
    lookup = {}
    for _, o in odds_df.iterrows():
        h, a = _norm_team(o.home_team), _norm_team(o.away_team)
        lookup[(h, a)] = (o.odds_1, o.odds_X, o.odds_2)
        lookup.setdefault((a, h), (o.odds_2, o.odds_X, o.odds_1))
    return lookup


def predict_fixtures(model, fixtures, odds_df=None, odds_weight=ODDS_WEIGHT,
                     extra_time=False, shootout=False):
    """Predict a fixtures DataFrame; returns a tidy results DataFrame."""
    odds_lookup = _build_odds_lookup(odds_df) if odds_df is not None else None
    rows = []
    for _, r in fixtures.iterrows():
        odds = None
        if odds_lookup is not None:
            odds = odds_lookup.get((_norm_team(r.home_team),
                                    _norm_team(r.away_team)))
        res = predict_match(model, r.home_team, r.away_team,
                            side=home_side(r.home_team, r.away_team, r.country),
                            odds=odds, odds_weight=odds_weight,
                            extra_time=extra_time, shootout=shootout)
        rows.append({
            "date": r.date.date(), "home": r.home_team, "away": r.away_team,
            "P_1": round(res["p1"], 3), "P_X": round(res["px"], 3),
            "P_2": round(res["p2"], 3),
            "pick": f"{res['pick'][0]}-{res['pick'][1]}",
            "expected_points": round(res["expected_points"], 3),
            "odds_used": res["used_odds"],
        })
    return pd.DataFrame(rows)
