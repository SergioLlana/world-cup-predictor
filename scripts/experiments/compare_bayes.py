"""Validation check comparison: MLE vs Bayesian Dixon-Coles, static fit, six tournaments.

See docs/bayesian-engine.md. Prints per-tournament
and pooled RPS / log-loss / Penka points for each engine variant plus the
bridge-audit table (the cross-confederation regional-bias metric):

  dc            — MLE Dixon-Coles, static (the apples-to-apples baseline).
  bayes         — Bayesian, static decay weights.
  bayes-dyn     — Bayesian, dynamic random-walk strengths.
  bayes-dyn-prop — dynamic strengths + full posterior propagation.

Run from the project root. Not wired into the CLI on purpose — this is an
experiment script. Pass a block granularity for the dynamic variant as the
first CLI arg (year|halfyear|quarter; default halfyear).
"""
import sys

from wcpred.backtest import TOURNAMENTS, _pool_metrics, backtest, bridge_audit
from wcpred.data import load_results

# (label, backtest kwargs)
VARIANTS = [
    ("dc", dict(engine="dc")),
    ("bayes", dict(engine="bayes")),
    ("bayes-dyn", dict(engine="bayes", dynamic=True)),
    ("bayes-dyn-prop", dict(engine="bayes", dynamic=True, propagate=True)),
]


def run(df, label, kw, audit):
    rows = []
    for t in TOURNAMENTS:
        r = backtest(df, t, rolling=False, audit=audit, **kw)
        rows.append(r)
        print(f"  {label:9s} {t:9s} {r['points']:6.1f} pts | "
              f"rps {r['rps']:.4f} | ll {r['log_loss']:.4f} | "
              f"exact {r['exact']}", flush=True)
    p = _pool_metrics(rows)
    print(f"  {label:9s} POOLED    {p['points']:6.1f} pts "
          f"({p['pts_per_match']:.3f}/match) | rps {p['rps']:.4f} | "
          f"ll {p['log_loss']:.4f} | exact {p['exact']} | n={p['matches']}\n",
          flush=True)
    return p["rps"], p["log_loss"], p["points"]


if __name__ == "__main__":
    block = sys.argv[1] if len(sys.argv) > 1 else "halfyear"
    df = load_results()
    for label, kw in VARIANTS:
        kw = dict(kw)
        if kw.get("dynamic"):
            kw["time_block"] = block
            label = f"{label}/{block}"
        print(f"=== {label} (static) ===", flush=True)
        audit = []
        run(df, label, kw, audit)
        print(f"--- bridge audit ({label}) ---", flush=True)
        print(bridge_audit(audit).to_string(index=False), flush=True)
        print(flush=True)
