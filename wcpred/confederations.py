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
(AFC above all) from drifting — see docs/known-limitations.md.
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
