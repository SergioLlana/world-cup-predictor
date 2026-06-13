"""Phase A/B1 canaries + prior diagnostics for the Bayesian engine.

Fits BayesianDixonColes on the live window (as-of today) — both the static
(Phase A) and dynamic random-walk (Phase B1) time treatments — and reports the
diagnosed-canary rating gaps (AUS-USA, ARG-ESP), the top-10, the learned
confederation-offset scale sigma_conf, and (dynamic) the random-walk step
scales sigma_rw_* plus MCMC convergence — the checks
docs/model-robustness-plan.md requires before any verdict.
"""
import numpy as np

from wcpred.data import load_results, prepare_training
from wcpred.model import DixonColes
from wcpred.model_bayes import BayesianDixonColes

AS_OF = "2026-06-13"

df = load_results()
tm = prepare_training(df, as_of=AS_OF)

mle = DixonColes().fit(tm)
bay = BayesianDixonColes().fit(tm, show_progress=False)
dyn = BayesianDixonColes().fit(tm, dynamic=True, time_block="halfyear",
                               show_progress=False)


def gaps(m, tag):
    ov = {t: m.atk[i] - m.dfn[i] for t, i in m.idx.items()}
    aus_usa = ov["Australia"] - ov["United States"]
    arg_esp = ov["Argentina"] - ov["Spain"]
    top = sorted(ov, key=lambda t: -ov[t])[:10]
    print(f"\n[{tag}] AUS-USA {aus_usa:+.3f} | ARG-ESP {arg_esp:+.3f}")
    print(f"[{tag}] top10:", ", ".join(f"{t} {ov[t]:.2f}" for t in top))


gaps(mle, "dc")
gaps(bay, "bayes")
gaps(dyn, "bayes-dyn")


def conf_offsets(m, tag):
    sc = m._mcmc.stan_variable("sigma_conf")
    ac = m._mcmc.stan_variable("atk_conf")   # (draws, C)
    dc_ = m._mcmc.stan_variable("dfn_conf")
    conf_names = sorted({c for c in m.conf.values() if c})
    print(f"\n[{tag}] sigma_conf posterior mean {sc.mean():.3f} "
          f"(95% CI {np.percentile(sc, 2.5):.3f}-{np.percentile(sc, 97.5):.3f})")
    print(f"[{tag}] confederation offsets (atk_conf - dfn_conf = bloc shift):")
    strength = ac.mean(axis=0) - dc_.mean(axis=0)
    for c, s in sorted(zip(conf_names, strength), key=lambda x: -x[1]):
        print(f"  {c:9s} {s:+.3f}")


conf_offsets(bay, "bayes")
conf_offsets(dyn, "bayes-dyn")

# Phase B1 random-walk diagnostics.
print(f"\n[bayes-dyn] blocks={len(dyn.blocks)} "
      f"({dyn.blocks[0]}..{dyn.blocks[-1]}, time_block=halfyear)")
for p in ("sigma_rw_atk", "sigma_rw_dfn"):
    v = dyn._mcmc.stan_variable(p)
    print(f"[bayes-dyn] {p} mean {v.mean():.4f} "
          f"(95% CI {np.percentile(v, 2.5):.4f}-{np.percentile(v, 97.5):.4f})")
print("\n[bayes-dyn] MCMC diagnose:")
print(dyn._mcmc.diagnose())
