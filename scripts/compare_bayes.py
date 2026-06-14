"""Gate comparison: MLE vs Bayesian Dixon-Coles, static fit, six tournaments.

Phases A and B1 of docs/bayesian-confederation-plan.md. Prints per-tournament
and pooled RPS / log-loss / Penka points for each engine variant plus the
bridge-audit table (the cross-confederation regional-bias metric):

  dc            — MLE Dixon-Coles, static (the apples-to-apples baseline).
  bayes         — Bayesian, static decay weights (Phase A).
  bayes-dyn     — Bayesian, dynamic random-walk strengths (Phase B1).
  bayes-dyn-prop — Phase B1 + full posterior propagation (Phase B2).

Run from the project root. Not wired into the CLI on purpose — this is an
experiment harness. Pass a block granularity for the dynamic variant as the
first CLI arg (year|halfyear|quarter; default halfyear).
"""
import sys

from wcpred.backtest import TOURNAMENTS, backtest, bridge_audit
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
    n = sum(r["matches"] for r in rows)
    pts = sum(r["points"] for r in rows)
    rps = sum(r["rps"] * r["matches"] for r in rows) / n
    ll = sum(r["log_loss"] * r["matches"] for r in rows) / n
    ex = sum(r["exact"] for r in rows)
    print(f"  {label:9s} POOLED    {pts:6.1f} pts ({pts/n:.3f}/match) | "
          f"rps {rps:.4f} | ll {ll:.4f} | exact {ex} | n={n}\n", flush=True)
    return rps, ll, pts


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
