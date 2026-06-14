"""In-house Elo engine (--engine elo).

A drop-in :class:`DixonColes` subclass that trains its own Elo ratings on
``results.csv`` (eloratings.net update rule) instead of reading external
snapshots, then calibrates an EL PAÍS-style GAM-Poisson + Dixon-Coles goal model
whose expected goals are driven by the *current* and *long-term* Elo differences.

Only ``fit`` and ``rates`` are overridden; ``matrix_from_rates`` / ``_tau`` /
``score_matrix`` are inherited, so the rest of the pipeline (predict, groups,
simulate, odds, webapp) is unchanged — the same way :class:`BayesianDixonColes`
plugs in.

Two extensions over plain eloratings.net, both default-off-equivalent
(``config`` defaults reproduce the published rule):

* a **per-confederation K** multiplier — each team updates its rating by its own
  confederation's K on top of the tournament base K;
* a **long-term Elo** covariate — the median of a team's Elo over the trailing
  ``ELO_LONGTERM_YEARS`` (the "pedigree" regression-to-the-mean feature).

The Elo iteration runs on the full raw history from ``ELO_TRAIN_START`` (ratings
need ~30 matches to converge and the long-term median needs a decade); the goal
model is calibrated on the decay-weighted ``prepare_training`` frame (recent
emphasis). Both are strictly causal: only matches before the cutoff are used.
See docs/elo-engine-plan.md.
"""
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import (ELO_BASE, ELO_CONF_K, ELO_HA, ELO_K_FINALS, ELO_K_TIERS,
                     ELO_LONGTERM_YEARS, ELO_TRAIN_START)
from .confederations import infer_confederations
from .model import DixonColes

_ELO_SCALE = 100.0  # Elo points per calibration unit (dr/400 lives in the K rule;
                    # the goal model just needs O(1) features → divide diffs by 100)


def tournament_k(tournament):
    """Base eloratings.net K for a martj42 ``tournament`` string."""
    if tournament == "Friendly":
        return ELO_K_TIERS["friendly"]
    if tournament == "FIFA World Cup":
        return ELO_K_TIERS["world_cup"]
    if str(tournament).endswith("qualification"):
        return ELO_K_TIERS["qualifier"]
    if tournament in ELO_K_FINALS:
        return ELO_K_TIERS["continental_final"]
    return ELO_K_TIERS["other"]


def gd_mult(n):
    """eloratings.net goal-difference K multiplier for a margin of ``n`` goals."""
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    if n == 3:
        return 1.75
    return 1.75 + (n - 3) / 8.0


def compute_elo(matches, as_of, ha=ELO_HA, conf_k=None, base=ELO_BASE,
                longterm_years=ELO_LONGTERM_YEARS):
    """Run the eloratings.net iteration over ``matches`` (played, chronological,
    strictly before ``as_of``).

    Returns ``(ratings, longterm, n_matches)``: current rating per team, the
    median post-match rating over the trailing ``longterm_years`` window, and the
    match count (for provisional <30-match flagging).
    """
    conf_k = conf_k if conf_k is not None else ELO_CONF_K
    confs = infer_confederations(matches)
    m = matches.dropna(subset=["home_score", "away_score"])
    m = m[m["date"] < pd.Timestamp(as_of)].sort_values("date")

    R = defaultdict(lambda: base)
    history = defaultdict(list)   # team -> [(date, rating_after_match), ...]
    for r in m.itertuples(index=False):
        Rh, Ra = R[r.home_team], R[r.away_team]
        dr = (Rh - Ra) + (0.0 if r.neutral else ha)
        we_h = 1.0 / (10.0 ** (-dr / 400.0) + 1.0)
        margin = r.home_score - r.away_score
        w_h = 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0
        g = gd_mult(abs(margin))
        k = tournament_k(r.tournament) * g
        k_h = k * conf_k.get(confs.get(r.home_team), 1.0)
        k_a = k * conf_k.get(confs.get(r.away_team), 1.0)
        R[r.home_team] = Rh + k_h * (w_h - we_h)
        R[r.away_team] = Ra + k_a * ((1.0 - w_h) - (1.0 - we_h))
        history[r.home_team].append((r.date, R[r.home_team]))
        history[r.away_team].append((r.date, R[r.away_team]))

    ratings = dict(R)
    window_start = pd.Timestamp(as_of) - pd.DateOffset(years=longterm_years)
    longterm, n_matches = {}, {}
    for team, hist in history.items():
        recent = [rt for (d, rt) in hist if d >= window_start]
        longterm[team] = float(np.median(recent)) if recent else ratings[team]
        n_matches[team] = len(hist)
    return ratings, longterm, n_matches


class EloDixonColes(DixonColes):
    """Dixon-Coles whose ratings come from an in-house Elo, not goal-MLE."""

    def fit(self, m, df=None, as_of=None, ha=ELO_HA, conf_k=None,
            longterm_years=ELO_LONGTERM_YEARS, elo_train_start=ELO_TRAIN_START,
            elo=None, elo_tau=0.0):
        """``m`` is the decay-weighted calibration frame (prepare_training);
        ``df``/``as_of`` give the raw full history for the Elo iteration.

        ``elo``/``elo_tau`` are accepted for signature parity with
        ``DixonColes.fit`` but ignored — this engine *is* the Elo anchor.
        """
        if df is None or as_of is None:
            raise ValueError("EloDixonColes.fit needs df and as_of (raw history "
                             "for the Elo iteration)")
        raw = df[(df["date"] >= pd.Timestamp(elo_train_start))
                 & (df["date"] < pd.Timestamp(as_of))]
        ratings, longterm, n_matches = compute_elo(
            raw, as_of, ha=ha, conf_k=conf_k, longterm_years=longterm_years)

        teams = sorted(set(m["home_team"]) | set(m["away_team"]))
        self.idx = {t: i for i, t in enumerate(teams)}
        self.elo_cur = np.array([ratings.get(t, ELO_BASE) for t in teams])
        self.elo_lt = np.array(
            [longterm.get(t, ratings.get(t, ELO_BASE)) for t in teams])
        self.elo_n = np.array([n_matches.get(t, 0) for t in teams])

        # --- calibration: 4-parameter weighted Poisson MLE on `m` ---
        hi = m["home_team"].map(self.idx).to_numpy()
        ai = m["away_team"].map(self.idx).to_numpy()
        hg = m["home_score"].to_numpy(float)
        ag = m["away_score"].to_numpy(float)
        w = m["w"].to_numpy(float)
        hh = np.where(m["neutral"].to_numpy(bool), 0.0, 1.0)
        de = (self.elo_cur[hi] - self.elo_cur[ai]) / _ELO_SCALE
        dl = (self.elo_lt[hi] - self.elo_lt[ai]) / _ELO_SCALE

        def nll_grad(p):
            b0, bh, be, blt = p
            lam = np.exp(b0 + bh * hh + be * de + blt * dl)
            mu = np.exp(b0 - be * de - blt * dl)
            ll = w * (hg * np.log(lam) - lam + ag * np.log(mu) - mu)
            rh, ra = w * (hg - lam), w * (ag - mu)   # d ll / d(log rate)
            g = np.array([
                (rh + ra).sum(),
                (rh * hh).sum(),
                (rh * de - ra * de).sum(),
                (rh * dl - ra * dl).sum(),
            ])
            return -ll.sum(), -g

        p0 = np.array([np.log(max(hg.mean(), 0.1)), 0.0, 0.0, 0.0])
        res = minimize(nll_grad, p0, jac=True, method="L-BFGS-B",
                       options={"maxiter": 500})
        self.beta = res.x
        b0, bh, be, blt = self.beta
        self.home = bh

        # rho via the same profile grid search as DixonColes.fit
        lam = np.exp(b0 + bh * hh + be * de + blt * dl)
        mu = np.exp(b0 - be * de - blt * dl)
        best, best_ll = 0.0, -np.inf
        for rho in np.linspace(-0.2, 0.2, 41):
            tau = self._tau(hg, ag, lam, mu, rho)
            cand = np.sum(w * np.log(np.clip(tau, 1e-10, None)))
            if cand > best_ll:
                best_ll, best = cand, rho
        self.rho = best

        # display attack/defence so `wcpred ratings` orders teams by Elo strength
        s = (be * (self.elo_cur - 1500.0) / _ELO_SCALE
             + blt * (self.elo_lt - 1500.0) / _ELO_SCALE)
        self.atk = b0 / 2.0 + s / 2.0
        self.dfn = b0 / 2.0 - s / 2.0
        return self

    def rates(self, home, away, home_side=None):
        try:
            i, j = self.idx[home], self.idx[away]
        except KeyError as e:
            raise KeyError(f"team not in the fitted model (misspelt, or fewer "
                           f"than MIN_MATCHES results before the training "
                           f"cutoff?): {e.args[0]}") from None
        b0, bh, be, blt = self.beta
        de = (self.elo_cur[i] - self.elo_cur[j]) / _ELO_SCALE
        dl = (self.elo_lt[i] - self.elo_lt[j]) / _ELO_SCALE
        hh = bh if home_side == "home" else 0.0
        ah = bh if home_side == "away" else 0.0
        lam = np.exp(b0 + hh + be * de + blt * dl)
        mu = np.exp(b0 + ah - be * de - blt * dl)
        return lam, mu
