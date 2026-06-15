"""Phase B2 gate: posterior propagation vs plug-in mean, controlled pairing.

For each of the six backtest tournaments it fits the Bayesian engine ONCE
(dynamic random-walk strengths, Phase B1 — the strongest predictive base) and
scores every match twice from the *same* MCMC draws: once with the plug-in
posterior-mean score matrix (Phase A/B1) and once with full posterior
propagation (Phase B2). Same fit ⇒ the only difference is the score-matrix
treatment, so the comparison is exact (no seed/sampling drift).

Prints per-tournament and pooled RPS / log-loss / Penka points for both
treatments plus each one's bridge-audit table. Static only, as the whole
Bayesian engine. Run from the project root; experiment harness, not CLI-wired.
"""
import numpy as np
import pandas as pd

from wcpred.backtest import TOURNAMENTS, TRAIN_WINDOW_YEARS, _bridge_record, \
    _match_metrics, _pool_metrics, bridge_audit
from wcpred.confederations import infer_confederations
from wcpred.data import load_results, prepare_training
from wcpred.model_bayes import BayesianDixonColes
from wcpred.predict import home_side, predict_match

BLOCK = "halfyear"


def score(df, tournament, model, propagate, audit):
    """Score one tournament's matches with model.propagate set, returning a
    backtest-style result dict. The model is already fitted (static)."""
    model.propagate = propagate
    as_of, start, end, name, n_group, n_mid = TOURNAMENTS[tournament]
    matches = df.dropna(subset=["home_score"])
    matches = matches[matches["date"].between(start, end)
                      & (matches["tournament"] == name)].sort_values("date")
    confs = infer_confederations(prepare_training(df, as_of, train_start=str(
        (pd.Timestamp(as_of) - pd.DateOffset(years=TRAIN_WINDOW_YEARS)).date())))
    total, exact, lls, rpss = 0.0, 0, [], []
    for i, (_, r) in enumerate(matches.iterrows()):
        stage = ("group" if i < n_group
                 else "r32_r16" if i < n_group + n_mid else "qf_plus")
        side = home_side(r.home_team, r.away_team, r.country)
        res = predict_match(model, r.home_team, r.away_team, side=side,
                            stage=stage)
        true = (int(r.home_score), int(r.away_score))
        p, ll, rps = _match_metrics(res, true, stage=stage)
        total += p
        exact += tuple(res["pick"]) == true
        lls.append(ll)
        rpss.append(rps)
        if audit is not None:
            hc, ac = confs.get(r.home_team), confs.get(r.away_team)
            if hc is not None and ac is not None and hc != ac:
                audit.append(_bridge_record(tournament, r, res, true, hc, ac,
                                            rps))
    n = len(matches)
    return {"matches": n, "points": total, "exact": exact,
            "log_loss": float(np.mean(lls)), "rps": float(np.mean(rpss))}


def pooled(label, rows):
    p = _pool_metrics(rows)
    print(f"  {label:14s} POOLED {p['points']:6.1f} pts "
          f"({p['pts_per_match']:.3f}/match) | rps {p['rps']:.4f} | "
          f"ll {p['log_loss']:.4f} | exact {p['exact']} | n={p['matches']}\n",
          flush=True)


if __name__ == "__main__":
    df = load_results()
    rows = {"plug-in": [], "propagate": []}
    audits = {"plug-in": [], "propagate": []}
    for t in TOURNAMENTS:
        as_of = TOURNAMENTS[t][0]
        tm = prepare_training(df, as_of, train_start=str(
            (pd.Timestamp(as_of) - pd.DateOffset(years=TRAIN_WINDOW_YEARS))
            .date()))
        model = BayesianDixonColes().fit(tm, dynamic=True, time_block=BLOCK,
                                         show_progress=False)
        for label, prop in (("plug-in", False), ("propagate", True)):
            r = score(df, t, model, prop, audits[label])
            rows[label].append(r)
            print(f"  {label:14s} {t:9s} {r['points']:6.1f} pts | "
                  f"rps {r['rps']:.4f} | ll {r['log_loss']:.4f} | "
                  f"exact {r['exact']}", flush=True)
    print(flush=True)
    for label in ("plug-in", "propagate"):
        pooled(label, rows[label])
    for label in ("plug-in", "propagate"):
        print(f"--- bridge audit ({label}) ---", flush=True)
        print(bridge_audit(audits[label]).to_string(index=False), flush=True)
        print(flush=True)
