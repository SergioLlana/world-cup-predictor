"""Dixon-Coles model: weighted Poisson with low-score correction."""
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from .config import MAX_GOALS


class DixonColes:
    """Attack/defence ratings per team + home advantage + rho correction."""

    def fit(self, m, elo=None, elo_tau=0.0):
        """elo/elo_tau (off by default): external Elo prior — penalty
        elo_tau * sum_i (s_i - a - b*elo_i)^2 on team strength s = atk - dfn,
        over the teams present in `elo`, with a, b re-profiled by OLS at every
        evaluation. Profiling makes the penalty invariant to the affine
        position of the ratings: only Elo's *relative* levels pull the model
        (docs/model-robustness-plan.md Phase 3)."""
        teams = sorted(set(m["home_team"]) | set(m["away_team"]))
        self.idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = m["home_team"].map(self.idx).to_numpy()
        ai = m["away_team"].map(self.idx).to_numpy()
        hg = m["home_score"].to_numpy(float)
        ag = m["away_score"].to_numpy(float)
        w = m["w"].to_numpy(float)
        hadv = np.where(m["neutral"].to_numpy(bool), 0.0, 1.0)

        ei = np.array([self.idx[t] for t in teams if elo and t in elo], int)
        if elo_tau and len(ei) > 2:
            X = np.column_stack([np.ones(len(ei)),
                                 [elo[teams[i]] for i in ei]])
            Xp = np.linalg.pinv(X)   # fixed: a, b = Xp @ s at every step
        else:
            elo_tau = 0.0

        def unpack(p):
            return p[:n], p[n:2 * n], p[2 * n]

        def nll_grad(p):
            atk, dfn, home = unpack(p)
            lam = np.exp(atk[hi] + dfn[ai] + home * hadv)
            mu = np.exp(atk[ai] + dfn[hi])
            ll = w * (hg * np.log(lam) - lam + ag * np.log(mu) - mu)
            g = np.zeros_like(p)
            dl, dm = w * (hg - lam), w * (ag - mu)
            np.add.at(g, hi, dl)
            np.add.at(g, ai, dm)
            np.add.at(g, n + ai, dl)
            np.add.at(g, n + hi, dm)
            g[2 * n] = np.sum(dl * hadv)
            pen = 100.0 * atk.mean() ** 2          # identifiability
            g[:n] -= 100.0 * 2 * atk.mean() / n
            if elo_tau:
                s = atk[ei] - dfn[ei]
                r = s - X @ (Xp @ s)   # OLS residuals; d pen/d s = 2*tau*r
                pen += elo_tau * (r @ r)
                g[ei] -= 2 * elo_tau * r
                g[n + ei] += 2 * elo_tau * r
            return -(ll.sum() - pen), -g

        res = minimize(nll_grad, np.zeros(2 * n + 1), jac=True,
                       method="L-BFGS-B", options={"maxiter": 500})
        self.atk, self.dfn, self.home = unpack(res.x)

        # rho via profile grid search (corrects 0-0/1-0/0-1/1-1)
        lam = np.exp(self.atk[hi] + self.dfn[ai] + self.home * hadv)
        mu = np.exp(self.atk[ai] + self.dfn[hi])
        best, best_ll = 0.0, -np.inf
        for rho in np.linspace(-0.2, 0.2, 41):
            tau = self._tau(hg, ag, lam, mu, rho)
            ll = np.sum(w * np.log(np.clip(tau, 1e-10, None)))
            if ll > best_ll:
                best_ll, best = ll, rho
        self.rho = best
        return self

    @staticmethod
    def _tau(x, y, lam, mu, rho):
        t = np.ones_like(lam)
        t = np.where((x == 0) & (y == 0), 1 - lam * mu * rho, t)
        t = np.where((x == 0) & (y == 1), 1 + lam * rho, t)
        t = np.where((x == 1) & (y == 0), 1 + mu * rho, t)
        t = np.where((x == 1) & (y == 1), 1 - rho, t)
        return t

    def rates(self, home, away, home_side=None):
        """home_side: 'home', 'away' or None — which listed team is playing on
        home soil and gets the home-advantage boost (None = neutral venue).
        The boost can go to the away side, e.g. a host as the listed away team
        in a knockout tie played in its own country."""
        try:
            i, j = self.idx[home], self.idx[away]
        except KeyError as e:
            # KeyError (not ValueError) so callers that guard unknown teams
            # (webapp /api/matrix) keep working.
            raise KeyError(f"team not in the fitted model (misspelt, or fewer "
                           f"than MIN_MATCHES results before the training "
                           f"cutoff?): {e.args[0]}") from None
        hb = self.home if home_side == "home" else 0.0
        ab = self.home if home_side == "away" else 0.0
        return (np.exp(self.atk[i] + self.dfn[j] + hb),
                np.exp(self.atk[j] + self.dfn[i] + ab))

    def matrix_from_rates(self, lam, mu):
        g = np.arange(MAX_GOALS + 1)
        P = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
        for x in (0, 1):
            for y in (0, 1):
                P[x, y] *= self._tau(np.array([x]), np.array([y]),
                                     np.array([lam]), np.array([mu]),
                                     self.rho)[0]
        P = np.clip(P, 0.0, None)   # tau can push P[0,0] below 0 at high rates
        return P / P.sum()

    def score_matrix(self, home, away, home_side=None):
        """P[home_goals, away_goals] over the 0..MAX_GOALS grid."""
        return self.matrix_from_rates(*self.rates(home, away, home_side))
