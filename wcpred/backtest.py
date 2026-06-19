"""Backtesting and hyperparameter tuning on past tournaments.

Reported metrics per tournament:
- pool points under the chosen game mode (Penka by default, the thing we
  ultimately care about — but noisy on ~64 matches, so don't tune on it alone);
- mean 1X2 ranked probability score (RPS, lower is better);
- mean exact-score log-loss (lower is better).
RPS/log-loss have far lower variance than points, so they drive tuning;
points decide between configs the probabilistic metrics can't separate.
"""
import itertools

import numpy as np
import pandas as pd

from .anchor import anchor_model
from .config import (BAYES_SIGMA_CONF_SCALE, CONF_ANCHOR_BETA,
                     CONF_ANCHOR_HALF_LIFE_DAYS, ELO_BASE, ELO_CONF_K, ELO_HA,
                     ELO_LONGTERM_YEARS, ELO_TRAIN_START, MAX_GOALS,
                     PICK_STRATEGY, SCORING_MODE)
from .confederations import infer_confederations
from .data import prepare_training
from .model import DixonColes
from .predict import home_side, predict_match
from .scoring import points

# as_of (first matchday), window, exact tournament name in results.csv, and
# the format (n group matches, n middle-tier knockouts) used to map each
# match — in chronological order — to its Penka payout tier: the first
# n_group matches are 'group', the next n_mid are 'r32_r16' (the R16 of
# 32/24-team formats; the Copa América jumps straight to the QF) and the
# rest are 'qf_plus'.
# Names must be exact: Euro and Copa América overlap in summer 2021/2024,
# so a loose "Euro|Copa" pattern would mix the two tournaments.
TOURNAMENTS = {
    "wc2018":   ("2018-06-14", "2018-06-01", "2018-07-31", "FIFA World Cup", 48, 8),
    "euro2021": ("2021-06-11", "2021-06-01", "2021-07-31", "UEFA Euro", 36, 8),
    "copa2021": ("2021-06-13", "2021-06-01", "2021-07-31", "Copa América", 20, 0),
    "wc2022":   ("2022-11-19", "2022-11-01", "2022-12-31", "FIFA World Cup", 48, 8),
    "euro2024": ("2024-06-14", "2024-06-01", "2024-07-31", "UEFA Euro", 36, 8),
    "copa2024": ("2024-06-20", "2024-06-15", "2024-07-31", "Copa América", 24, 0),
}

# Lookback matching what the 2026 setup gets from TRAIN_START="2015-01-01",
# so older tournaments (wc2018) train on a comparable span of history.
TRAIN_WINDOW_YEARS = 11


def _match_metrics(res, true, scoring=SCORING_MODE, stage="group"):
    """(pool_points, exact_score_log_loss, 1X2_rps) for one match."""
    p = points(res["pick"], true, scoring, stage)
    h, a = min(true[0], MAX_GOALS), min(true[1], MAX_GOALS)
    ll = -np.log(max(res["P"][h, a], 1e-12))
    d = true[0] - true[1]
    o1, ox = float(d > 0), float(d == 0)
    rps = 0.5 * ((res["p1"] - o1) ** 2
                 + (res["p1"] + res["px"] - o1 - ox) ** 2)
    return p, ll, rps


def _bridge_record(tournament, r, res, true, hc, ac, rps):
    """One inter-confederation ("bridge") audit record: predicted vs realised.

    Shared by `backtest` and the experiment scripts (scripts/gate_b2.py) so
    the schema `bridge_audit` consumes is defined in exactly one place.
    """
    P = res["P"]
    goals = np.arange(P.shape[0])
    return {
        "tournament": tournament, "date": str(r["date"].date()),
        "home_conf": hc, "away_conf": ac,
        "p_home": res["p1"], "p_draw": res["px"],
        "home_goals": true[0], "away_goals": true[1],
        "exp_home": float(P.sum(axis=1) @ goals),
        "exp_away": float(P.sum(axis=0) @ goals),
        "rps": rps,
    }


def _pool_metrics(results):
    """Match-weighted pooled metrics across per-tournament result dicts.

    Single source of truth for the RPS/log-loss (match-weighted) + points
    pooling repeated by `tune`, the elo-engine tuners and the experiment
    experiment scripts.
    """
    n = sum(r["matches"] for r in results)
    return {
        "matches": n,
        "points": sum(r["points"] for r in results),
        "pts_per_match": sum(r["points"] for r in results) / n,
        "exact": sum(r["exact"] for r in results),
        "rps": sum(r["rps"] * r["matches"] for r in results) / n,
        "log_loss": sum(r["log_loss"] * r["matches"] for r in results) / n,
    }


WEAK_BLOCS = ("AFC", "OFC", "CONCACAF", "CAF")  # the thinly-bridged blocs


def elo_conf_strength(m, df, as_of, longterm_years=None, cap=None, only=None):
    """Empirical informative prior MEANS for the Bayesian confederation offsets.

    The zero-mean offset prior says "no bloc is stronger absent bridge
    evidence" — exactly where the AFC/OFC schedule-inflation bias lives. This
    derives a non-zero per-bloc mean from a *globally connected* rating (the
    Elo, which propagates across confederations through the iterative
    update), so the prior pulls a poorly-bridged bloc toward its Elo-anchored
    level. Returns ``{confederation: net_strength_offset}`` (zero-sum, log-rate
    units) to feed ``BayesianDixonColes.fit(conf_strength=...)``.

    Magnitude is auto-calibrated, no free parameter: fit a plain Dixon-Coles on the
    same frame, take each team's strength = atk - dfn, regress it on the team's
    Elo to get the log-rate-per-Elo slope ``beta``, then map each bloc's mean
    Elo gap vs the global mean through ``beta``.

    ``cap`` (optional) winsorises every offset to ``[-cap, cap]`` — tames the
    bloc-composition spike (a small all-strong bloc like CONMEBOL towers over
    the minnow-laden global mean) while keeping the empirical ordering.
    ``only`` (optional) restricts the offsets to a set of blocs (the others get
    a 0 prior mean, i.e. stay data-driven) — e.g. pull down only the
    thinly-bridged blocs without touching UEFA/CONMEBOL.
    """
    from .model_elo import EloHistory
    dc = DixonColes().fit(m)
    strength = {t: float(dc.atk[i] - dc.dfn[i]) for t, i in dc.idx.items()}
    raw = df[(df["date"] >= pd.Timestamp(ELO_TRAIN_START))
             & (df["date"] < pd.Timestamp(as_of))]
    ratings, _, _ = EloHistory(raw).at(
        as_of, ELO_LONGTERM_YEARS if longterm_years is None else longterm_years)
    confs = infer_confederations(m)
    teams = [t for t in strength if t in ratings and t in confs]
    if len(teams) < 5:
        return {}
    elo = np.array([ratings[t] for t in teams])
    st = np.array([strength[t] for t in teams])
    beta = float(np.polyfit(elo, st, 1)[0])      # log-rate per Elo point
    global_elo = elo.mean()
    blocs = sorted(set(confs[t] for t in teams))
    s = {c: beta * (np.mean([ratings[t] for t in teams if confs[t] == c])
                    - global_elo) for c in blocs}
    shift = np.mean(list(s.values()))            # zero-sum across blocs
    s = {c: v - shift for c, v in s.items()}
    if only is not None:
        s = {c: v for c, v in s.items() if c in only}
    if cap is not None:
        s = {c: max(-cap, min(cap, v)) for c, v in s.items()}
    return s


def backtest(df, tournament="wc2022", rolling=True, xg_path=None,
             xg_alpha=None, scoring=SCORING_MODE, audit=None,
             anchor_beta=CONF_ANCHOR_BETA,
             anchor_half_life=CONF_ANCHOR_HALF_LIFE_DAYS, engine="dc",
             dynamic=False, time_block=None,
             sigma_conf_scale=BAYES_SIGMA_CONF_SCALE, propagate=False,
             informed_conf=False, connect_shrink=False, connect_ref=None,
             connect_mode=None, connect_by=None, connect_opp_ref=None,
             bayes_seed=2026,
             elo_conf_k=None, elo_longterm_years=None, elo_ha=None,
             pick_strategy=PICK_STRATEGY,
             **train_kw):
    """Score every match of a past tournament.

    rolling=True re-fits the model at each matchday (training on matches
    strictly before it, so earlier tournament results feed later picks) —
    the same way `--as-of` is used live. rolling=False fits once
    pre-tournament. Host teams get home advantage, as in the live pipeline.
    scoring sets the game mode: picks are optimised for it and points are
    reported in it. Extra train_kw (half_life, friendly_weight, gd_cap, ...)
    reach prepare_training.

    audit, if given, is a list that collects one record per
    inter-confederation ("bridge") match — predicted vs realised — for
    `bridge_audit`. Confederations are inferred from each re-fit's own
    training window, so the tagging stays causal.

    anchor_beta > 0 applies the Phase 2b two-timescale confederation
    re-anchoring after each (re-)fit, with the long fit's cutoff tracking the
    short fit's — the same protocol a live `--as-of` run would use.

    engine "bayes" swaps the MLE Dixon-Coles for the Stan
    BayesianDixonColes (hierarchical confederation-offset prior). It is
    static only (rolling=False): a per-matchday MCMC re-fit over six
    tournaments is prohibitively slow, and the anchor parameter is
    MLE-specific. dynamic=True (Phase B1, bayes only) replaces the decay
    weighting with a random-walk evolution of team strengths over
    time_block-sized blocks ("year"/"halfyear"/"quarter").

    sigma_conf_scale (bayes only) is the half-normal prior scale on the
    between-confederation offset spread — the Phase 4 tight-sigma_conf
    sensitivity. 0.5 reproduces the current bayes model; shrinking it toward 0
    pins the bloc offsets near 0.

    propagate=True (Phase B2, bayes only) builds each match's score matrix as
    the posterior mean of the per-draw Dixon-Coles matrices (full posterior
    propagation) instead of plugging in the posterior-mean ratings.

    connect_shrink=True (Phase C, bayes only) scales each team's confederation
    offset by its bridge-match share (connect_ref = the share earning the full
    offset), anchoring weakly-connected teams to the global scale. Static only.
    """
    if engine == "bayes":
        if rolling:
            raise ValueError("engine='bayes' is static only; pass "
                             "rolling=False (CLI: --static)")
        if anchor_beta:
            raise ValueError("anchor_beta is an MLE-engine parameter; "
                             "it has no effect under engine='bayes'")
    elif dynamic or propagate or informed_conf or connect_shrink:
        raise ValueError("dynamic=True/propagate=True/informed_conf=True/"
                         "connect_shrink=True only apply to engine='bayes'")
    if engine == "elo" and anchor_beta:
        raise ValueError("anchor_beta is an MLE-engine parameter; it has "
                         "no effect under engine='elo' (it trains its own Elo)")
    as_of, start, end, name, n_group, n_mid = TOURNAMENTS[tournament]
    matches = df.dropna(subset=["home_score"])
    matches = matches[matches["date"].between(start, end)
                      & (matches["tournament"] == name)].sort_values("date")

    kw = dict(train_kw)
    if xg_alpha is not None:
        kw["xg_alpha"] = xg_alpha
    kw.setdefault("train_start", str(
        (pd.Timestamp(as_of) - pd.DateOffset(years=TRAIN_WINDOW_YEARS)).date()))

    # The Elo engine re-iterates the full eloratings history at every cutoff;
    # in a rolling backtest that is the same decade of matches re-run per
    # matchday. Iterate it ONCE over the whole window here and let each re-fit
    # slice it causally (EloHistory.at(cutoff) reproduces a from-scratch fit
    # exactly). Bounded at `end` so we never iterate matches past the tournament.
    elo_history = None
    if engine == "elo":
        from .model_elo import EloHistory
        raw_elo = df[(df["date"] >= pd.Timestamp(ELO_TRAIN_START))
                     & (df["date"] <= pd.Timestamp(end))]
        elo_history = EloHistory(raw_elo, conf_k=elo_conf_k,
                                 ha=(ELO_HA if elo_ha is None else elo_ha))

    model, fitted_at, confs = None, None, {}
    total, exact, outcome = 0.0, 0, 0
    lls, rpss = [], []
    for i, (_, r) in enumerate(matches.iterrows()):
        stage = ("group" if i < n_group
                 else "r32_r16" if i < n_group + n_mid else "qf_plus")
        cutoff = str(r["date"].date()) if rolling else as_of
        if cutoff != fitted_at:
            tm = prepare_training(df, cutoff, xg_path=xg_path, **kw)
            if engine == "bayes":
                from .model_bayes import BayesianDixonColes
                cs = None
                if informed_conf:
                    cap = 0.4 if informed_conf == "capped" else None
                    only = WEAK_BLOCS if informed_conf == "weak" else None
                    cs = elo_conf_strength(tm, df, cutoff, cap=cap, only=only)
                model = BayesianDixonColes().fit(
                    tm, dynamic=dynamic, time_block=time_block,
                    sigma_conf_scale=sigma_conf_scale, propagate=propagate,
                    conf_strength=cs, connect_shrink=connect_shrink,
                    connect_ref=connect_ref, connect_mode=connect_mode,
                    connect_by=connect_by, connect_opp_ref=connect_opp_ref,
                    seed=bayes_seed)
            elif engine == "elo":
                from .model_elo import EloDixonColes
                model = EloDixonColes().fit(
                    tm, as_of=cutoff, conf_k=elo_conf_k,
                    longterm_years=elo_longterm_years, ha=elo_ha,
                    elo_history=elo_history)
            else:
                model = DixonColes().fit(tm)
            if anchor_beta:
                anchor_model(model, df, cutoff, beta=anchor_beta,
                             long_half_life=anchor_half_life,
                             xg_path=xg_path, **kw)
            if audit is not None:
                confs = infer_confederations(tm)
            fitted_at = cutoff
        side = home_side(r.home_team, r.away_team, r.country)
        res = predict_match(model, r.home_team, r.away_team, side=side,
                            scoring=scoring, stage=stage,
                            pick_strategy=pick_strategy)
        true = (int(r.home_score), int(r.away_score))
        p, ll, rps = _match_metrics(res, true, scoring, stage)
        total += p
        exact += tuple(res["pick"]) == true
        outcome += p > 0
        lls.append(ll)
        rpss.append(rps)
        if audit is not None:
            hc, ac = confs.get(r.home_team), confs.get(r.away_team)
            if hc is not None and ac is not None and hc != ac:
                audit.append(_bridge_record(tournament, r, res, true, hc, ac,
                                            rps))
    n = len(matches)
    return {"tournament": tournament, "matches": n, "points": total,
            "points_per_match": total / n, "exact": exact,
            "outcome_correct": outcome, "log_loss": float(np.mean(lls)),
            "rps": float(np.mean(rpss))}


def bridge_audit(records):
    """Aggregate bridge-match records into a per-confederation-pair table.

    The regional-bias test from the Elo literature: on inter-confederation
    matches only, compare the model's predicted match share with the realised
    one. For each unordered pair the perspective side A is the alphabetically
    first confederation; a match share is win + half a draw, so
    bias = exp_share − real_share > 0 means the model overrates A against B.
    goal_res_a/b are mean (actual − expected) goals for each side: positive
    means that side scored more than the model expected.
    """
    agg = {}
    for r in records:
        swap = r["home_conf"] > r["away_conf"]
        key = tuple(sorted((r["home_conf"], r["away_conf"])))
        a = agg.setdefault(key, {"n": 0, "exp": 0.0, "real": 0.0,
                                 "res_a": 0.0, "res_b": 0.0, "rps": 0.0})
        exp_home = r["p_home"] + 0.5 * r["p_draw"]
        d = r["home_goals"] - r["away_goals"]
        real_home = 1.0 if d > 0 else 0.5 if d == 0 else 0.0
        res_home = r["home_goals"] - r["exp_home"]
        res_away = r["away_goals"] - r["exp_away"]
        a["n"] += 1
        a["exp"] += 1.0 - exp_home if swap else exp_home
        a["real"] += 1.0 - real_home if swap else real_home
        a["res_a"] += res_away if swap else res_home
        a["res_b"] += res_home if swap else res_away
        a["rps"] += r["rps"]
    rows = []
    for (ca, cb), a in agg.items():
        n = a["n"]
        rows.append({
            "conf_a": ca, "conf_b": cb, "n": n,
            "exp_share_a": a["exp"] / n, "real_share_a": a["real"] / n,
            "bias_a": (a["exp"] - a["real"]) / n,
            "goal_res_a": a["res_a"] / n, "goal_res_b": a["res_b"] / n,
            "rps": a["rps"] / n,
        })
    return (pd.DataFrame(rows)
            .sort_values("n", ascending=False).reset_index(drop=True))


def tune(df, tournaments=None, gd_caps=(None, 3, 4),
         half_lives=(365, 545, 730, 1095), friendly_weights=(0.5, 0.75, 1.0),
         cross_conf_weights=(1.0,), shrinkages=((None, 0.0),),
         anchor_betas=(0.0,), rolling=False, verbose=True):
    """Grid-search training hyperparameters across tournaments (no xG).

    Static fit by default to keep the grid cheap; re-validate the winner
    with rolling=True afterwards. Returns a DataFrame sorted by pooled RPS,
    with per-match-pooled metrics across all tournaments.
    `shrinkages` sweeps (SHRINKAGE_MODE, SHRINKAGE_WEIGHT) pairs — the
    Phase 1 data-augmentation parameters (`wcpred tune --shrinkage`).
    `anchor_betas` sweeps the Phase 2b confederation re-anchoring blend
    (`wcpred tune --anchor`).
    """
    tournaments = list(tournaments or TOURNAMENTS)
    rows = []
    for cap, hl, fw, ccw, (sm, sw), ab in itertools.product(
            gd_caps, half_lives, friendly_weights, cross_conf_weights,
            shrinkages, anchor_betas):
        res = [backtest(df, t, rolling=rolling, gd_cap=cap,
                        half_life=hl, friendly_weight=fw,
                        cross_conf_weight=ccw,
                        shrinkage_mode=sm, shrinkage_weight=sw,
                        anchor_beta=ab)
               for t in tournaments]
        row = {
            "gd_cap": cap, "half_life": hl, "friendly_w": fw,
            "cross_conf_w": ccw,
            "shrink_mode": sm, "shrink_w": sw, "anchor_beta": ab,
            **_pool_metrics(res),
        }
        rows.append(row)
        if verbose:
            print(f"gd_cap={cap} half_life={hl} "
                  f"friendly_w={fw} cross_conf_w={ccw} "
                  f"shrinkage={sm}:{sw} anchor={ab}: "
                  f"{row['pts_per_match']:.3f} pts/match, "
                  f"rps {row['rps']:.4f}, "
                  f"ll {row['log_loss']:.4f}")
    return (pd.DataFrame(rows)
            .sort_values("rps").reset_index(drop=True))


def _elo_pool(df, tournaments, conf_k, ly, ha, rolling):
    """Pooled (across tournaments) elo-engine metrics for one config."""
    res = [backtest(df, t, rolling=rolling, engine="elo",
                    elo_conf_k=conf_k, elo_longterm_years=ly, elo_ha=ha)
           for t in tournaments]
    return _pool_metrics(res)


def tune_elo(df, tournaments=None, longterm_years=(5, 8, 10, 12, 15),
             has=(50.0, 75.0, 100.0, 125.0),
             conf_k_grid=(0.5, 0.75, 1.0, 1.25, 1.5, 2.0),
             confs=("UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"),
             rolling=False, verbose=True):
    """Coordinate tuning for the Elo engine (``--engine elo``) on pooled RPS
    (low variance), points as the tiebreak — the protocol the rest of `tune`
    follows.

    The per-confederation K is a 6-D dict, so a full grid is infeasible. Instead:

    1. **scalar grid** over (``longterm_years``, ``ha``) with every conf-K = 1.0;
    2. **coordinate descent** on the conf-K: holding the best scalar config,
       sweep one confederation's K multiplier at a time over ``conf_k_grid``,
       adopting an improvement before moving to the next confederation.

    Static fit by default to keep it cheap; re-validate the winner with
    rolling=True. Returns ``(scalar_df, conf_df, best)`` where ``best`` is the
    chosen ``{conf: k}`` dict plus the winning longterm_years/ha.
    """
    tournaments = list(tournaments or TOURNAMENTS)
    base_k = {c: 1.0 for c in confs}

    # --- step 1: scalar grid (longterm_years x ha), conf-K all 1.0 ---
    scalar_rows = []
    for ly, ha in itertools.product(longterm_years, has):
        row = {"longterm_years": ly, "ha": ha,
               **_elo_pool(df, tournaments, base_k, ly, ha, rolling)}
        scalar_rows.append(row)
        if verbose:
            print(f"[scalar] longterm_years={ly} ha={ha}: "
                  f"{row['pts_per_match']:.3f} pts/match, rps {row['rps']:.4f}, "
                  f"ll {row['log_loss']:.4f}")
    scalar_df = pd.DataFrame(scalar_rows).sort_values("rps").reset_index(drop=True)
    best_scalar = scalar_df.iloc[0]
    ly, ha = int(best_scalar["longterm_years"]), float(best_scalar["ha"])
    if verbose:
        print(f"--> best scalar: longterm_years={ly} ha={ha} "
              f"(rps {best_scalar['rps']:.4f})\n")

    # --- step 2: coordinate descent on the per-confederation K ---
    best_k = dict(base_k)
    best_rps = float(best_scalar["rps"])
    conf_rows = []
    for c in confs:
        for k in conf_k_grid:
            trial = dict(best_k)
            trial[c] = k
            row = {"conf": c, "k": k,
                   **_elo_pool(df, tournaments, trial, ly, ha, rolling)}
            conf_rows.append(row)
            if verbose:
                print(f"[conf-K] {c}={k} (others {best_k}): "
                      f"{row['pts_per_match']:.3f} pts/match, "
                      f"rps {row['rps']:.4f}, ll {row['log_loss']:.4f}")
            if row["rps"] < best_rps:
                best_rps, best_k[c] = row["rps"], k
        if verbose:
            print(f"--> {c} -> {best_k[c]} (running rps {best_rps:.4f})\n")

    best = {"longterm_years": ly, "ha": ha, "conf_k": best_k, "rps": best_rps}
    if verbose:
        print(f"BEST elo config: {best}")
    return (scalar_df,
            pd.DataFrame(conf_rows).sort_values("rps").reset_index(drop=True),
            best)


def elo_report(df, conf_k=None, longterm_years=None, ha=None, rolling=True,
               tournaments=None):
    """Per-tournament + pooled elo-engine metrics for one config.

    Used to re-validate a tuned config with the live rolling re-fit (the gold
    standard) before adopting it. Returns ``(per_tournament_df, pooled)``.
    """
    tournaments = list(tournaments or TOURNAMENTS)
    res = [dict(backtest(df, t, rolling=rolling, engine="elo",
                         elo_conf_k=conf_k, elo_longterm_years=longterm_years,
                         elo_ha=ha)) for t in tournaments]
    return pd.DataFrame(res), _pool_metrics(res)
