"""Full-tournament Monte Carlo: group stage + knockout bracket.

Extends the group-only simulation (`groups.py`) to the whole 2026 World Cup:
the **8 best third-placed teams** (of 12 groups), the official FIFA Round-of-32
bracket (Annex C allocation of thirds, see `thirds_table.py`), and extra-time +
penalty resolution of knockout ties. Matches already played in real life —
group *or* knockout — are used as-is; only the remaining fixtures are simulated,
so the same command works mid-tournament.

Two modelling notes:
- **Knockout venue is neutral.** The bracket is synthetic (no venue/country per
  slot), so host-nation advantage is modelled only in the group stage (where the
  fixtures carry a `country`). See `docs/known-limitations.md`.
- **Official group labels.** The Round-of-32 wiring (Winner A, Runner-up B, the
  third-place slots) is defined in terms of FIFA's official A..L labels, which
  do *not* match `groups.derive_groups`' kick-off-order labels. We therefore key
  off the official draw (`OFFICIAL_GROUPS`), not the inferred ordering.
"""
import numpy as np
import pandas as pd

from .config import EXTRA_TIME_FRACTION, ODDS_WEIGHT
from .predict import home_side, predict_match
from .scoring import outcome_probs, resolve_extra_time, resolve_shootout
from .thirds_table import THIRD_PLACE_ALLOCATION

# Official 2026 group draw (team names match the martj42 dataset). Source of
# truth for both group membership and the A..L labels the bracket relies on.
OFFICIAL_GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}
GROUP_LABELS = list(OFFICIAL_GROUPS)              # A..L, index 0..11
GROUP_IDX = {g: i for i, g in enumerate(GROUP_LABELS)}

# Round-of-32 bracket as data. Feeder tokens:
#   ("W", "A") winner of group A · ("R", "B") runner-up of group B
#   ("3", "M74") third-placed team assigned to that match by the FIFA table
#   ("M", 74) winner of match 74
R32 = {
    73: (("R", "A"), ("R", "B")), 74: (("W", "E"), ("3", "M74")),
    75: (("W", "F"), ("R", "C")), 76: (("W", "C"), ("R", "F")),
    77: (("W", "I"), ("3", "M77")), 78: (("R", "E"), ("R", "I")),
    79: (("W", "A"), ("3", "M79")), 80: (("W", "L"), ("3", "M80")),
    81: (("W", "D"), ("3", "M81")), 82: (("W", "G"), ("3", "M82")),
    83: (("R", "K"), ("R", "L")), 84: (("W", "H"), ("R", "J")),
    85: (("W", "B"), ("3", "M85")), 86: (("W", "J"), ("R", "H")),
    87: (("W", "K"), ("3", "M87")), 88: (("R", "D"), ("R", "G")),
}
LATER = {
    89: (("M", 74), ("M", 77)), 90: (("M", 73), ("M", 75)),
    91: (("M", 76), ("M", 78)), 92: (("M", 79), ("M", 80)),
    93: (("M", 83), ("M", 84)), 94: (("M", 81), ("M", 82)),
    95: (("M", 86), ("M", 88)), 96: (("M", 85), ("M", 87)),
    97: (("M", 89), ("M", 90)), 98: (("M", 93), ("M", 94)),
    99: (("M", 91), ("M", 92)), 100: (("M", 95), ("M", 96)),
    101: (("M", 97), ("M", 98)), 102: (("M", 99), ("M", 100)),
    104: (("M", 101), ("M", 102)),
}
THIRD_SLOTS = ["M74", "M77", "M79", "M80", "M81", "M82", "M85", "M87"]
ROUND_MATCHES = {                       # which match winners "reach" each round
    "r16": range(73, 89), "qf": range(89, 97), "sf": range(97, 101),
    "final": (101, 102), "champion": (104,),
}


def _compile_thirds_table():
    """Precompile THIRD_PLACE_ALLOCATION into (COMBO_MASKS, SLOT_GROUP).

    COMBO_MASKS[k] = 12-bit mask of the 8 groups supplying a third (sorted);
    SLOT_GROUP[k, c] = group index (0..11) of the third assigned to THIRD_SLOTS[c].
    """
    masks, rows = [], []
    for combo, slots in THIRD_PLACE_ALLOCATION.items():
        masks.append(sum(1 << GROUP_IDX[g] for g in combo))
        rows.append([GROUP_IDX[slots[m]] for m in THIRD_SLOTS])
    masks, rows = np.array(masks), np.array(rows)
    order = np.argsort(masks)
    return masks[order], rows[order]


COMBO_MASKS, SLOT_GROUP = _compile_thirds_table()


def _split_played(played, team_group):
    """Partition real results into group (intra-group) and knockout (inter-group)
    matches. A match is knockout iff its two teams sit in different groups."""
    if played is None or not len(played):
        empty = played.iloc[0:0] if played is not None else None
        return empty, empty
    same = played.apply(
        lambda r: team_group.get(r.home_team) is not None
        and team_group.get(r.home_team) == team_group.get(r.away_team), axis=1)
    return played[same], played[~same]


def _simulate_groups_joint(model, fixtures, played_group, n_sims, rng,
                           odds_lookup, odds_weight, compact):
    """Joint group stage; returns per-sim compact team ids for 1st/2nd/3rd of
    each group plus the third-placed team's points/GD/GF (for ranking thirds).

    Arrays are shaped (n_sims, 12) with column g = group GROUP_LABELS[g]."""
    n_groups = len(GROUP_LABELS)
    winner = np.empty((n_sims, n_groups), dtype=np.int32)
    runner = np.empty((n_sims, n_groups), dtype=np.int32)
    third = np.empty((n_sims, n_groups), dtype=np.int32)
    third_pts = np.empty((n_sims, n_groups))
    third_gd = np.empty((n_sims, n_groups))
    third_gf = np.empty((n_sims, n_groups))

    for g, label in enumerate(GROUP_LABELS):
        teams = OFFICIAL_GROUPS[label]
        local = {t: i for i, t in enumerate(teams)}
        ids = np.array([compact[t] for t in teams])     # local 0..3 -> compact id
        pts = np.zeros((n_sims, 4))
        gd = np.zeros((n_sims, 4))
        gf = np.zeros((n_sims, 4))

        # Real group results already decided: enter them as fixed.
        done_pairs = set()
        if played_group is not None and len(played_group):
            gp = played_group[played_group.home_team.isin(teams)
                              & played_group.away_team.isin(teams)]
            for _, r in gp.iterrows():
                h, a = local[r.home_team], local[r.away_team]
                hg, ag = int(r.home_score), int(r.away_score)
                pts[:, h] += 3 * (hg > ag) + (hg == ag)
                pts[:, a] += 3 * (ag > hg) + (hg == ag)
                gd[:, h] += hg - ag
                gd[:, a] += ag - hg
                gf[:, h] += hg
                gf[:, a] += ag
                done_pairs.add(frozenset((r.home_team, r.away_team)))

        # Remaining fixtures: sample from the (optionally odds-blended) matrix.
        gf_fix = fixtures[fixtures.home_team.isin(teams)
                          & fixtures.away_team.isin(teams)]
        for _, r in gf_fix.iterrows():
            # each group pair meets exactly once in the group stage; a second
            # meeting is a knockout rematch and must not count here
            if frozenset((r.home_team, r.away_team)) in done_pairs:
                continue
            h, a = local[r.home_team], local[r.away_team]
            odds = odds_lookup.get((r.home_team, r.away_team)) if odds_lookup else None
            P = predict_match(model, r.home_team, r.away_team,
                              side=home_side(r.home_team, r.away_team, r.country),
                              odds=odds, odds_weight=odds_weight)["P"]
            flat = (P / P.sum()).ravel()
            draw = rng.choice(flat.size, size=n_sims, p=flat)
            hg, ag = np.divmod(draw, P.shape[1])
            pts[:, h] += 3 * (hg > ag) + (hg == ag)
            pts[:, a] += 3 * (ag > hg) + (hg == ag)
            gd[:, h] += hg - ag
            gd[:, a] += ag - hg
            gf[:, h] += hg
            gf[:, a] += ag

        # FIFA ranking: points, then GD, then GF; remaining ties broken at random.
        tiebreak = rng.random((n_sims, 4))
        order = np.lexsort((tiebreak, gf, gd, pts), axis=1)[:, ::-1]
        winner[:, g] = ids[order[:, 0]]
        runner[:, g] = ids[order[:, 1]]
        third[:, g] = ids[order[:, 2]]
        t = order[:, 2:3]
        third_pts[:, g] = np.take_along_axis(pts, t, axis=1)[:, 0]
        third_gd[:, g] = np.take_along_axis(gd, t, axis=1)[:, 0]
        third_gf[:, g] = np.take_along_axis(gf, t, axis=1)[:, 0]

    return winner, runner, third, third_pts, third_gd, third_gf


def _select_best_thirds(third_pts, third_gd, third_gf, rng):
    """Rank the 12 third-placed teams; return (qualifies mask, combo mask).

    qualifies[s, g] = group g's third is among the 8 best in sim s.
    combo_mask[s]   = 12-bit mask of which groups those 8 are."""
    n_sims = third_pts.shape[0]
    rank = np.lexsort((rng.random((n_sims, 12)), third_gf, third_gd, third_pts),
                      axis=1)[:, ::-1]
    qualifies = np.zeros((n_sims, 12), dtype=bool)
    np.put_along_axis(qualifies, rank[:, :8], True, axis=1)
    combo_mask = (qualifies * (1 << np.arange(12))).sum(axis=1)
    return qualifies, combo_mask


def _pairwise_winprob(model, teams, compact):
    """W[i, j] = P(team i beats team j) in a neutral knockout (ET + penalties).
    Indexed by compact team id."""
    n = len(teams)
    W = np.zeros((n, n))
    for a in teams:
        for b in teams:
            if a == b:
                continue
            i, j = compact[a], compact[b]
            if W[i, j] or W[j, i]:
                continue
            P = model.score_matrix(a, b, home_side=None)
            lam, mu = model.rates(a, b, None)
            P_et = model.matrix_from_rates(lam * EXTRA_TIME_FRACTION,
                                           mu * EXTRA_TIME_FRACTION)
            P = resolve_shootout(resolve_extra_time(P, P_et))
            p1, px, p2 = outcome_probs(P)
            W[i, j] = p1 + px           # px ≈ 0 after the shootout collapse
            W[j, i] = p2
    return W


def _ko_played_pairs(played_ko, team_group, compact):
    """List of (winner_id, loser_id) compact pairs for already-played knockouts.
    Draws (penalty results not in the score) are skipped with a warning."""
    pairs = []
    if played_ko is None or not len(played_ko):
        return pairs
    for _, r in played_ko.iterrows():
        hg, ag = int(r.home_score), int(r.away_score)
        if hg == ag:
            print(f"WARNING: knockout {r.home_team} v {r.away_team} ended level "
                  f"in the data (penalty winner unknown); leaving it simulated.")
            continue
        w, lo = (r.home_team, r.away_team) if hg > ag else (r.away_team, r.home_team)
        pairs.append((compact[w], compact[lo]))
    return pairs


def _simulate_bracket(winner, runner, third, qualifies, combo_mask, W,
                      ko_pairs, rng, n_teams):
    """Play the bracket; return per-round boolean reach masks of shape
    (n_sims, n_teams). Already-played knockouts force their real winner."""
    n_sims = winner.shape[0]
    row = np.searchsorted(COMBO_MASKS, combo_mask)
    assert np.all(COMBO_MASKS[row] == combo_mask), "combo not in FIFA table"
    slot_group = SLOT_GROUP[row]                         # (n_sims, 8)
    third_for_slot = {
        m: third[np.arange(n_sims), slot_group[:, c]]
        for c, m in enumerate(THIRD_SLOTS)
    }

    def resolve(token):
        kind, ref = token
        if kind == "W":
            return winner[:, GROUP_IDX[ref]]
        if kind == "R":
            return runner[:, GROUP_IDX[ref]]
        if kind == "3":
            return third_for_slot[ref]
        return won[ref]                                  # ("M", match)

    def play(a, b):
        a_wins = rng.random(n_sims) < W[a, b]
        for w_id, l_id in ko_pairs:                      # force real results
            hit = ((a == w_id) & (b == l_id)) | ((a == l_id) & (b == w_id))
            if hit.any():
                a_wins = np.where(hit, a == w_id, a_wins)
        return np.where(a_wins, a, b)

    won = {}                                             # match -> winner ids
    reach = {k: np.zeros((n_sims, n_teams), dtype=bool)
             for k in ("r32", "r16", "qf", "sf", "final", "champion")}
    rows = np.arange(n_sims)
    for match, (fa, fb) in {**R32, **LATER}.items():
        a, b = resolve(fa), resolve(fb)
        if match in R32:                                 # R32 participants
            reach["r32"][rows, a] = True
            reach["r32"][rows, b] = True
        won[match] = play(a, b)

    for key, matches in ROUND_MATCHES.items():
        for m in matches:
            reach[key][rows, won[m]] = True
    return reach


def simulate_tournament(model, fixtures, n_sims=100_000, seed=0, played=None,
                        odds_df=None, odds_weight=ODDS_WEIGHT):
    """Simulate the full 2026 tournament; return a per-team probability table.

    Columns: team, group, p_win_group, p_runner_up, p_third, p_best_third,
    p_knockout (reach R32), p_r16, p_qf, p_sf, p_final, p_champion."""
    teams = [t for g in GROUP_LABELS for t in OFFICIAL_GROUPS[g]]
    missing = [t for t in teams if t not in model.idx]
    if missing:
        raise ValueError(f"teams absent from the model (too few matches?): {missing}")
    compact = {t: i for i, t in enumerate(teams)}
    team_group = {t: g for g, ts in OFFICIAL_GROUPS.items() for t in ts}
    rng = np.random.default_rng(seed)

    odds_lookup = None
    if odds_df is not None:
        from .predict import _build_odds_lookup, _norm_team
        raw = _build_odds_lookup(odds_df)
        # _build_odds_lookup keys on normalised names; re-key on dataset names.
        norm = {_norm_team(t): t for t in teams}
        odds_lookup = {(norm[h], norm[a]): v for (h, a), v in raw.items()
                       if h in norm and a in norm}

    played_group, played_ko = _split_played(played, team_group)
    winner, runner, third, t_pts, t_gd, t_gf = _simulate_groups_joint(
        model, fixtures, played_group, n_sims, rng, odds_lookup, odds_weight,
        compact)
    qualifies, combo_mask = _select_best_thirds(t_pts, t_gd, t_gf, rng)
    W = _pairwise_winprob(model, teams, compact)
    ko_pairs = _ko_played_pairs(played_ko, team_group, compact)
    reach = _simulate_bracket(winner, runner, third, qualifies, combo_mask, W,
                              ko_pairs, rng, len(teams))

    # Combinatorial sanity (exact, independent of n_sims).
    assert np.all(qualifies.sum(1) == 8)
    assert np.all(reach["r32"].sum(1) == 32)
    assert np.all(reach["champion"].sum(1) == 1)

    def tally(id_array):
        counts = np.zeros(len(teams))
        np.add.at(counts, id_array.ravel(), 1)
        return counts / n_sims

    p_win = tally(winner)
    p_run = tally(runner)
    p_third = tally(third)
    bt = np.zeros(len(teams))
    np.add.at(bt, third[qualifies], 1)
    p_best_third = bt / n_sims

    out = pd.DataFrame({
        "team": teams,
        "group": [team_group[t] for t in teams],
        "p_win_group": p_win.round(4),
        "p_runner_up": p_run.round(4),
        "p_third": p_third.round(4),
        "p_best_third": p_best_third.round(4),
        "p_knockout": reach["r32"].mean(0).round(4),
        "p_r16": reach["r16"].mean(0).round(4),
        "p_qf": reach["qf"].mean(0).round(4),
        "p_sf": reach["sf"].mean(0).round(4),
        "p_final": reach["final"].mean(0).round(4),
        "p_champion": reach["champion"].mean(0).round(4),
    })
    return out.sort_values("p_champion", ascending=False).reset_index(drop=True)
