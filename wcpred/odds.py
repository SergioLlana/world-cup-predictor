"""Betting odds: conversion, de-vigging, market-implied score matrices."""
import numpy as np
from scipy.optimize import minimize

from .scoring import outcome_probs


def to_prob(odds):
    """American (-235, +375) or decimal (1.45) odds -> implied probability.
    Heuristic: |value| >= 100 -> American; otherwise decimal."""
    o = float(str(odds).replace("+", ""))
    if abs(o) >= 100:
        return 100 / (o + 100) if o > 0 else -o / (-o + 100)
    if o <= 1:
        raise ValueError(f"Decimal odds must be > 1, got {odds}")
    return 1 / o


def devig(p1, px, p2):
    """Strip the bookmaker margin by proportional normalisation."""
    s = p1 + px + p2
    return p1 / s, px / s, p2 / s


def market_matrix(model, home, away, probs, side=None):
    """Recalibrate (lam, mu) so the Dixon-Coles matrix reproduces the
    market's de-vigged 1X2 probabilities, starting from the model rates.
    `side` ('home'/'away'/None) seeds the optimiser with the right venue."""
    p1, px, p2 = probs
    lam0, mu0 = model.rates(home, away, side)

    def loss(p):
        P = model.matrix_from_rates(np.exp(p[0]), np.exp(p[1]))
        q1, qx, q2 = outcome_probs(P)
        return (q1 - p1) ** 2 + (qx - px) ** 2 + (q2 - p2) ** 2

    res = minimize(loss, [np.log(lam0), np.log(mu0)], method="Nelder-Mead")
    return model.matrix_from_rates(np.exp(res.x[0]), np.exp(res.x[1]))
