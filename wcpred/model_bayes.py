"""Bayesian Dixon-Coles (Stan) with a hierarchical confederation-offset prior.

A drop-in alternative to `model.DixonColes`: it subclasses it, so it inherits
`rates`, `matrix_from_rates`, `_tau` and `score_matrix` unchanged and slots
into `predict`/`groups`/`tournament`/`odds`/the webapp transparently. Only
`fit` is overridden — it samples a Stan Dixon-Coles via cmdstanpy and fixes
`atk`/`dfn`/`home`/`rho` to their posterior means (Phase A,
docs/bayesian-confederation-plan.md; full posterior propagation is Phase B2).

The structural difference from the MLE model is the prior: each team's
attack/defence carries an additive confederation-level offset that only the
rare inter-confederation "bridge" matches can move, so intra-confederation
games cannot drift a whole confederation up or down — the weak-anchoring fix the
internal-data interventions of the (closed) robustness plan could not achieve.

Two time treatments are available:
  - static (`stan/dixon_coles.stan`, default): time enters as the exponential
    time-decay weights `w` of the MLE model — Phase A.
  - dynamic (`stan/dixon_coles_dynamic.stan`, opt-in via `dynamic=True` /
    `--bayes-dynamic` / `config.BAYES_DYNAMIC`): each team's attack/defence
    deviation evolves as a Gaussian random walk over discrete time blocks and
    the most recent block's state is adopted — Phase B1. The random walk *is*
    the time model, so the decay weights are dropped (matches enter unweighted;
    the friendly/cross-conf weight multipliers, off by default, are ignored).

Needs the `bayes` extra and a one-off CmdStan install:
    pip install -e ".[bayes]"
    python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"
"""
import os

import numpy as np

from .config import BAYES_DYNAMIC, BAYES_TIME_BLOCK
from .confederations import infer_confederations
from .model import DixonColes

_STAN_DIR = os.path.join(os.path.dirname(__file__), "stan")
_STAN_STATIC = os.path.join(_STAN_DIR, "dixon_coles.stan")
_STAN_DYNAMIC = os.path.join(_STAN_DIR, "dixon_coles_dynamic.stan")

# Integer block key per match date for the dynamic random-walk's time blocks
# (pandas to_period multipliers like "2Q" do not aggregate, so derive the key
# directly). Sorted unique keys then map to contiguous 1..B block indices.
_BLOCK_KEY = {
    "year": lambda d: d.dt.year,
    "halfyear": lambda d: d.dt.year * 2 + (d.dt.month > 6).astype(int),
    "quarter": lambda d: d.dt.year * 4 + (d.dt.month - 1) // 3,
}

# Compile each Stan model once per process; backtests re-fit many times and
# recompilation would dominate the runtime.
_COMPILED = {}


def _compiled_model(stan_file):
    if stan_file not in _COMPILED:
        try:
            from cmdstanpy import CmdStanModel
        except ImportError as e:
            raise ImportError(
                "the Bayesian engine needs cmdstanpy: `pip install -e "
                "\".[bayes]\"` then `python -c \"import cmdstanpy; "
                "cmdstanpy.install_cmdstan()\"`") from e
        _COMPILED[stan_file] = CmdStanModel(stan_file=stan_file)
    return _COMPILED[stan_file]


class BayesianDixonColes(DixonColes):
    """Dixon-Coles fitted by MCMC with a confederation-offset prior."""

    def fit(self, m, chains=4, iter_warmup=500, iter_sampling=500, seed=2026,
            adapt_delta=0.9, show_progress=False, elo=None, elo_tau=0.0,
            dynamic=None, time_block=None, **stan_kwargs):
        """Sample the Stan model on training frame `m` and adopt posterior
        means. `elo`/`elo_tau` are accepted for a uniform call signature with
        DixonColes.fit but ignored (the Bayesian engine has no external prior).

        dynamic/time_block (resolved from config.BAYES_DYNAMIC /
        config.BAYES_TIME_BLOCK when None) select the time treatment: False =
        Phase A static decay weights; True = Phase B1 random-walk strengths over
        `time_block`-sized blocks ("year"/"halfyear"/"quarter"), adopting the
        most recent block. Extra `stan_kwargs` pass through to
        `CmdStanModel.sample`.
        """
        if dynamic is None:
            dynamic = BAYES_DYNAMIC
        if time_block is None:
            time_block = BAYES_TIME_BLOCK

        teams = sorted(set(m["home_team"]) | set(m["away_team"]))
        self.idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = m["home_team"].map(self.idx).to_numpy()
        ai = m["away_team"].map(self.idx).to_numpy()
        hg = m["home_score"].to_numpy()
        ag = m["away_score"].to_numpy()
        if not (np.allclose(hg, np.round(hg)) and np.allclose(ag, np.round(ag))):
            raise ValueError("the Bayesian engine needs integer scores "
                             "(no xG blend / shrinkage augmentation)")
        hadv = np.where(m["neutral"].to_numpy(bool), 0.0, 1.0)

        # Confederation index per team (1..C; 0 = unknown → no offset).
        confs = infer_confederations(m)
        conf_names = sorted(set(confs.values()))
        conf_id = {c: i + 1 for i, c in enumerate(conf_names)}
        conf = np.array([conf_id.get(confs.get(t), 0) for t in teams], int)
        self.conf = {t: confs.get(t) for t in teams}

        data = {
            "N": len(hi), "T": n, "C": len(conf_names),
            "hi": (hi + 1).tolist(), "ai": (ai + 1).tolist(),
            "hg": np.round(hg).astype(int).tolist(),
            "ag": np.round(ag).astype(int).tolist(),
            "hadv": hadv.tolist(), "conf": conf.tolist(),
        }

        if dynamic:
            stan_file = _STAN_DYNAMIC
            # Time blocks from match dates; the random walk replaces the decay
            # weights, so matches enter unweighted (w=1). The most recent block
            # is the prediction state.
            try:
                keys = _BLOCK_KEY[time_block](m["date"])
            except KeyError:
                raise ValueError(f"unknown time_block {time_block!r}; choose "
                                 f"from {sorted(_BLOCK_KEY)}") from None
            blocks = sorted(keys.unique())
            block_id = {k: i + 1 for i, k in enumerate(blocks)}
            tb = keys.map(block_id).to_numpy()
            self.blocks = blocks
            data.update(B=len(blocks), tb=tb.tolist(),
                        w=np.ones(len(hi)).tolist())
        else:
            stan_file = _STAN_STATIC
            data["w"] = m["w"].to_numpy(float).tolist()

        mcmc = _compiled_model(stan_file).sample(
            data=data, chains=chains, parallel_chains=chains,
            iter_warmup=iter_warmup, iter_sampling=iter_sampling,
            seed=seed, adapt_delta=adapt_delta,
            show_progress=show_progress, **stan_kwargs)

        if dynamic:
            # atk/dfn are (draws, T, B); adopt the most recent block's mean.
            self.atk = mcmc.stan_variable("atk")[:, :, -1].mean(axis=0)
            self.dfn = mcmc.stan_variable("dfn")[:, :, -1].mean(axis=0)
        else:
            self.atk = mcmc.stan_variable("atk").mean(axis=0)
            self.dfn = mcmc.stan_variable("dfn").mean(axis=0)
        self.home = float(mcmc.stan_variable("home").mean())
        self.rho = float(mcmc.stan_variable("rho").mean())
        self.dynamic = dynamic
        self._mcmc = mcmc   # kept for diagnostics / Phase B2 posterior draws
        return self
