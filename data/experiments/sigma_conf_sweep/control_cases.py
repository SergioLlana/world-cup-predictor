"""Tight-sigma_conf control cases + offset characterisation.

For a given prior scale, fit the dynamic Bayesian Dixon-Coles at the live
as-of on the full training window and report:
  - ARG-ESP and AUS-USA overall rating gaps (atk - dfn) — the standing control cases.
  - posterior-mean sigma_conf and the per-confederation offset (atk_conf -
    dfn_conf), to see how tightening the prior collapses the bloc levels.

Usage: python control_cases.py <sigma_conf_scale> <as_of>
"""
import os
import sys

# This script lives under data/experiments/...; ensure the repo root (which
# holds the `wcpred` package) is importable regardless of how it is invoked.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np

from wcpred.data import load_results, prepare_training
from wcpred.model_bayes import BayesianDixonColes
from wcpred.confederations import infer_confederations

scale = float(sys.argv[1])
as_of = sys.argv[2]

df = load_results("data/input/results.csv")
train = prepare_training(df, as_of=as_of)
m = BayesianDixonColes().fit(train, dynamic=True, time_block="halfyear",
                             sigma_conf_scale=scale)


def gap(a, b):
    if a not in m.idx or b not in m.idx:
        return float("nan")
    ia, ib = m.idx[a], m.idx[b]
    return (m.atk[ia] - m.dfn[ia]) - (m.atk[ib] - m.dfn[ib])


arg_esp = gap("Argentina", "Spain")
aus_usa = gap("Australia", "United States")

mc = m._mcmc
sigma_conf = float(mc.stan_variable("sigma_conf").mean())
atk_conf = mc.stan_variable("atk_conf").mean(axis=0)
dfn_conf = mc.stan_variable("dfn_conf").mean(axis=0)
# Recover the confederation label order used inside fit (sorted unique names).
confs = infer_confederations(train)
conf_names = sorted(set(confs.values()))
offsets = {c: float(atk_conf[i] - dfn_conf[i]) for i, c in enumerate(conf_names)}
ordered = sorted(offsets.items(), key=lambda kv: -kv[1])

print(f"SCALE {scale} (as-of {as_of})")
print(f"  ARG-ESP gap: {arg_esp:+.3f}   AUS-USA gap: {aus_usa:+.3f}")
print(f"  sigma_conf (post. mean): {sigma_conf:.3f}")
print("  bloc offsets (atk_conf - dfn_conf): "
      + " > ".join(f"{c} {v:+.2f}" for c, v in ordered))
