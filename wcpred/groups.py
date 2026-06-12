"""Group-stage standings via Monte Carlo simulation.

Unlike `scoring.best_prediction` (which picks the pool-optimal scoreline),
this samples scorelines straight from the match probability matrix — the
model's, or the market-blended one when odds are given (`--approach odds`),
exactly as `predict`/`simulate` build it — so the simulated results follow
the *realistic* distribution of outcomes. Matches
already played enter the standings with their actual result; the rest are
simulated many times, points/goal difference tallied with the standard 3-1-0
system, and each team's chance of finishing 1st/2nd/3rd/4th reported.
"""
import numpy as np
import pandas as pd

from .config import ODDS_WEIGHT
from .predict import home_side, odds_lookup_for, predict_match


def derive_groups(fixtures):
    """Infer groups as connected components of the fixture graph.

    Each World Cup group plays an internal round-robin and no cross-group
    matches in the first round, so every group of 4 is an isolated clique in
    the fixture list. Pass the *full* group schedule (played + upcoming):
    mid-tournament, the remaining fixtures alone no longer connect all four
    teams. Groups are returned ordered by their first kick-off and labelled
    A, B, C ... (inferred — the dataset carries no group column)."""
    adj, first = {}, {}
    for _, r in fixtures.iterrows():
        adj.setdefault(r.home_team, set()).add(r.away_team)
        adj.setdefault(r.away_team, set()).add(r.home_team)
        for t in (r.home_team, r.away_team):
            first[t] = min(first.get(t, r.date), r.date)
    seen, comps = set(), []
    for team in adj:
        if team in seen:
            continue
        stack, comp = [team], set()
        while stack:
            t = stack.pop()
            if t in comp:
                continue
            comp.add(t)
            stack.extend(adj[t] - comp)
        seen |= comp
        comps.append(sorted(comp))
    comps.sort(key=lambda c: min(first[t] for t in c))
    labels = [chr(ord("A") + i) for i in range(len(comps))]
    return dict(zip(labels, comps))


def _sample_scores(P, n, rng):
    """Draw n (home_goals, away_goals) pairs from a score matrix P."""
    flat = (P / P.sum()).ravel()
    idx = rng.choice(flat.size, size=n, p=flat)
    return np.divmod(idx, P.shape[1])


def _group_points(model, teams, fixtures, played, n_sims, rng,
                  odds_lookup, odds_weight):
    """Tally one group's matches into per-sim standings arrays.

    Real results in `played` enter as fixed; the remaining group fixtures are
    sampled from the (optionally odds-blended) score matrix. Returns
    (pts, gd, gf) arrays of shape (n_sims, len(teams)), columns in `teams`
    order. Shared by `simulate_group` and the joint tournament simulation."""
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    pts = np.zeros((n_sims, n))
    gd = np.zeros((n_sims, n))
    gf = np.zeros((n_sims, n))

    def tally(h, a, hg, ag):
        pts[:, h] += 3 * (hg > ag) + (hg == ag)
        pts[:, a] += 3 * (ag > hg) + (hg == ag)
        gd[:, h] += hg - ag
        gd[:, a] += ag - hg
        gf[:, h] += hg
        gf[:, a] += ag

    done_pairs = set()
    if played is not None and len(played):
        gp = played[played.home_team.isin(teams)
                    & played.away_team.isin(teams)]
        for _, r in gp.iterrows():
            tally(idx[r.home_team], idx[r.away_team],
                  int(r.home_score), int(r.away_score))
            done_pairs.add(frozenset((r.home_team, r.away_team)))
    gfix = fixtures[fixtures.home_team.isin(teams)
                    & fixtures.away_team.isin(teams)]
    for _, r in gfix.iterrows():
        # each group pair meets exactly once in the group stage; a second
        # meeting is a knockout rematch and must not count here
        if frozenset((r.home_team, r.away_team)) in done_pairs:
            continue
        odds = odds_lookup.get((r.home_team, r.away_team)) if odds_lookup else None
        P = predict_match(
            model, r.home_team, r.away_team,
            side=home_side(r.home_team, r.away_team, r.country),
            odds=odds, odds_weight=odds_weight)["P"]
        hg, ag = _sample_scores(P, n_sims, rng)
        tally(idx[r.home_team], idx[r.away_team], hg, ag)
    return pts, gd, gf


def simulate_group(model, teams, fixtures, n_sims=100000, rng=None,
                   played=None, odds_lookup=None, odds_weight=ODDS_WEIGHT):
    """Simulate one group; return a standings DataFrame sorted best-first.

    `played` rows (same fixture columns plus scores) count as fixed results,
    so mid-tournament standings include the points already won.
    `odds_lookup` ({(home, away): (odds_1, odds_X, odds_2)}, dataset names)
    blends the market into each fixture's score matrix, as in `predict`;
    fixtures absent from it fall back to the model-only matrix.
    Columns: team, P1..P4 (finish-position probabilities), qualify (top 2),
    xPts (expected points), xGD (expected goal difference)."""
    rng = rng or np.random.default_rng(0)
    n = len(teams)
    pts, gd, gfor = _group_points(model, teams, fixtures, played, n_sims, rng,
                                  odds_lookup, odds_weight)

    # FIFA-style ranking: points, then GD, then goals for; ties broken at
    # random (head-to-head is not modelled). lexsort's last key is primary.
    tiebreak = rng.random((n_sims, n))
    order = np.lexsort((tiebreak, gfor, gd, pts), axis=1)[:, ::-1]
    pos = np.empty_like(order)
    rows = np.arange(n_sims)[:, None]
    pos[rows, order] = np.arange(n)[None, :]          # pos: 0 = 1st place

    rank_prob = np.stack([(pos == k).mean(axis=0) for k in range(n)], axis=1)
    out = pd.DataFrame({
        "team": teams,
        **{f"P{k+1}": rank_prob[:, k].round(3) for k in range(n)},
        "qualify": (rank_prob[:, 0] + rank_prob[:, 1]).round(3),
        "xPts": pts.mean(axis=0).round(2),
        "xGD": gd.mean(axis=0).round(2),
    })
    return out.sort_values(["P1", "qualify", "xPts"],
                           ascending=False).reset_index(drop=True)


def simulate_groups(model, fixtures, n_sims=100000, seed=0, played=None,
                    groups=None, odds_df=None, odds_weight=ODDS_WEIGHT):
    """Simulate every group; return {label: standings DataFrame}.

    `groups` ({label: [teams]}) overrides inference — pass the official draw
    when known (inferred labels follow kick-off order, not FIFA's A..L).
    Otherwise groups are derived from played + upcoming matches together so
    they stay intact mid-tournament. `played` results enter the standings
    as-is. `odds_df` (home_team, away_team, odds_1, odds_X, odds_2) blends
    the market into the remaining fixtures, as in `predict`/`simulate`."""
    rng = np.random.default_rng(seed)
    if groups is None:
        sched = fixtures
        if played is not None and len(played):
            sched = pd.concat([played, fixtures], ignore_index=True)
        groups = derive_groups(sched)

    odds_lookup = None
    if odds_df is not None:
        odds_lookup = odds_lookup_for(
            odds_df, [t for ts in groups.values() for t in ts])
        missing = sum(
            1 for _, r in fixtures.iterrows()
            if any(r.home_team in ts and r.away_team in ts
                   for ts in groups.values())
            and (r.home_team, r.away_team) not in odds_lookup)
        if missing:
            print(f"WARNING: {missing} group fixtures had no odds; "
                  f"model-only matrices used for those.")

    return {label: simulate_group(model, teams, fixtures, n_sims, rng, played,
                                  odds_lookup, odds_weight)
            for label, teams in groups.items()}
