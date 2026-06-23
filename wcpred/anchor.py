"""Two-timescale confederation re-anchoring (rejected experiment).

Dixon-Coles identifies cross-confederation rating offsets only through the
thin "bridge" games inside its ~2y-effective window — the weakly-identified
quantity behind the bridge-audit bias (docs/known-limitations.md).
Confederation levels move slowly, so estimate them on a long window
(CONF_ANCHOR_HALF_LIFE_DAYS, where bridges are plentiful) and recenter the
short-window model's per-confederation mean strength toward those levels.

Only the relative levels *between* confederations move: every team of a
confederation is shifted by the same amount, split evenly between attack and
defence, so intra-confederation predictions are exactly invariant and the
intra-confederation spread, rho and home advantage are untouched. Teams whose
confederation cannot be inferred (or that are missing from the long fit) are
left alone.
"""
import numpy as np

from .config import CONF_ANCHOR_BETA, CONF_ANCHOR_HALF_LIFE_DAYS
from .confederations import infer_confederations
from .data import prepare_training
from .model import DixonColes


def conf_deltas(model, df, as_of, long_half_life=CONF_ANCHOR_HALF_LIFE_DAYS,
                xg_path=None, **train_kw):
    """Per-confederation level corrections from a slow-timescale fit.

    Fits Dixon-Coles on the same window as `model` but with `long_half_life`
    time decay (shrinkage augmentation off — stage 1 stays pure), then
    returns ({conf: long_level − short_level}, {team: conf}) where each level
    is the mean strength (atk − dfn) over the teams the two fits share.
    Deltas are centred to a team-weighted mean of 0 so the population level
    stays put; only differences between confederations matter for predictions.
    """
    kw = dict(train_kw, half_life=long_half_life, shrinkage_mode=None)
    tm = prepare_training(df, as_of, xg_path=xg_path, **kw)
    long_m = DixonColes().fit(tm)
    confs = infer_confederations(tm)
    diffs = {}
    for t, i in model.idx.items():
        c, j = confs.get(t), long_m.idx.get(t)
        if c is None or j is None:
            continue
        short_s = model.atk[i] - model.dfn[i]
        long_s = long_m.atk[j] - long_m.dfn[j]
        diffs.setdefault(c, []).append(long_s - short_s)
    deltas = {c: float(np.mean(v)) for c, v in diffs.items()}
    n_total = sum(len(v) for v in diffs.values())
    center = sum(deltas[c] * len(v) for c, v in diffs.items()) / n_total
    return {c: d - center for c, d in deltas.items()}, confs


def anchor_model(model, df, as_of, beta=CONF_ANCHOR_BETA,
                 long_half_life=CONF_ANCHOR_HALF_LIFE_DAYS, xg_path=None,
                 **train_kw):
    """Shift `model`'s ratings by beta x the confederation-level deltas.

    beta = 0 is an exact no-op (the model is returned untouched); beta = 1
    adopts the long window's confederation levels fully. The shift is split
    between attack and defence (+d/2 / −d/2) so a corrected team scores more
    and concedes less in equal measure.
    """
    if not beta:
        return model
    deltas, confs = conf_deltas(model, df, as_of, long_half_life=long_half_life,
                                xg_path=xg_path, **train_kw)
    for t, i in model.idx.items():
        d = deltas.get(confs.get(t))
        if d:
            adj = 0.5 * beta * d
            model.atk[i] += adj
            model.dfn[i] -= adj
    return model
