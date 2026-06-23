"""Team -> confederation inference from continental competitions.

The martj42 dataset carries no confederation column, but every FIFA member
plays its own confederation's championship/qualifiers, so membership can be
read off the data: each team is assigned the confederation whose competitions
it has appeared in most often. Majority vote keeps invitational guests where
they belong (Qatar/Japan at the 2019 Copa América, the CONCACAF sides at the
2016/2024 editions, Australia's pre-2006 OFC history).

Used by `data.prepare_training` to upweight inter-confederation "bridge"
matches (`CROSS_CONF_WEIGHT`): they are the only games anchoring the
confederations to a common scale, which is what keeps weakly-connected pools
(AFC above all) from shifting — see docs/known-limitations.md.
"""
import pandas as pd

CONF_TOURNAMENTS = {
    "UEFA": (
        "UEFA Euro", "UEFA Euro qualification", "UEFA Nations League",
    ),
    "CONMEBOL": (
        "Copa América",
    ),
    "CONCACAF": (
        "Gold Cup", "Gold Cup qualification",
        "CONCACAF Nations League", "CONCACAF Nations League qualification",
        "CONCACAF Championship", "CONCACAF Championship qualification",
        "CFU Caribbean Cup", "CFU Caribbean Cup qualification",
        "UNCAF Cup", "CONCACAF Series",
    ),
    "CAF": (
        "African Cup of Nations", "African Cup of Nations qualification",
        "African Nations Championship", "COSAFA Cup", "CECAFA Cup",
        "Amilcar Cabral Cup",
    ),
    "AFC": (
        "AFC Asian Cup", "AFC Asian Cup qualification",
        "AFC Challenge Cup", "AFC Challenge Cup qualification",
        "AFF Championship", "AFF Championship qualification",
        "SAFF Cup", "EAFF Championship", "WAFF Championship", "Gulf Cup",
    ),
    "OFC": (
        "Oceania Nations Cup", "Oceania Nations Cup qualification",
        "Pacific Games",
    ),
}

_TOURN_TO_CONF = {t: c for c, ts in CONF_TOURNAMENTS.items() for t in ts}


def infer_confederations(matches):
    """{team: confederation} by majority vote over continental competitions.

    Pass the training window's matches (not the full dataset) so backtests
    stay strictly causal. Teams with no continental appearance in the window
    are absent from the result and treated as unknown by callers.
    """
    m = matches[matches["tournament"].isin(_TOURN_TO_CONF)]
    conf = m["tournament"].map(_TOURN_TO_CONF)
    long = pd.concat([
        pd.DataFrame({"team": m["home_team"], "conf": conf}),
        pd.DataFrame({"team": m["away_team"], "conf": conf}),
    ])
    counts = long.groupby(["team", "conf"]).size().unstack(fill_value=0)
    return counts.idxmax(axis=1).to_dict()


def cross_conf_mask(matches, confs):
    """Boolean Series: both confederations known and different."""
    hc = matches["home_team"].map(confs)
    ac = matches["away_team"].map(confs)
    return hc.notna() & ac.notna() & (hc != ac)


def bridge_share(matches, confs, weight_col="w"):
    """{team: fraction of its training weight from inter-confederation matches}.

    A "bridge" match (both confederations known and different) is the only kind
    of game that anchors a team to the *global* rating scale; intra-confederation
    games only fix a team's level relative to its own pool. So this share
    measures how well-connected — and thus how trustworthy in absolute terms — a
    team's rating is (the `model_bayes` connectivity-weighted offset
    shrinkage scales each team's confederation offset by it). Teams with no
    bridge weight get 0.0. `weight_col` selects the per-match weight column (the
    same time-decay `w` the model fits on); equal weights are used when absent.

    Mirrors the per-team `bridge_share` of `webapp/server.py:_connectivity`.
    """
    w = (matches[weight_col].astype(float) if weight_col in matches.columns
         else pd.Series(1.0, index=matches.index))
    bridge = cross_conf_mask(matches, confs)
    long = pd.concat([
        pd.DataFrame({"team": matches["home_team"], "w": w,
                      "bw": w * bridge.astype(float)}),
        pd.DataFrame({"team": matches["away_team"], "w": w,
                      "bw": w * bridge.astype(float)}),
    ])
    g = long.groupby("team")
    share = (g["bw"].sum() / g["w"].sum()).fillna(0.0)
    return share.to_dict()


def opponent_rating(matches, overall, weight_col="w"):
    """{team: weighted mean opponent overall rating} over `matches`.

    The average difficulty of a team's training schedule, using the same
    time-decay `w` the model fits on and a pre-fit `overall` = atk − dfn map
    (so it is exogenous to the model being trained — no circularity). This is
    the schedule-difficulty signal the connectivity shrinkage gates on
    (low opponent rating = a soft schedule = a rating to trust less in absolute
    terms), the predictor that actually separates Australia (soft schedule)
    from legitimate outliers like Spain/Argentina (hard schedules). Mirrors the
    per-team `opp_rating` of `webapp/server.py:_connectivity`. Opponents absent
    from `overall` are skipped; teams with no rated opponent are omitted.

    Mirrors `webapp/server.py`'s per-team weighted mean opponent rating.
    """
    w = (matches[weight_col].astype(float) if weight_col in matches.columns
         else pd.Series(1.0, index=matches.index))
    h_ov = matches["home_team"].map(overall)
    a_ov = matches["away_team"].map(overall)
    # Each row contributes the opponent's rating to each side (NaN where the
    # opponent is unrated; dropped from both numerator and denominator).
    long = pd.concat([
        pd.DataFrame({"team": matches["home_team"], "w": w, "opp": a_ov}),
        pd.DataFrame({"team": matches["away_team"], "w": w, "opp": h_ov}),
    ]).dropna(subset=["opp"])
    long["ow"] = long["w"] * long["opp"]
    g = long.groupby("team")
    return (g["ow"].sum() / g["w"].sum()).to_dict()
