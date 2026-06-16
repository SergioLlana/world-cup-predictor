"""Evaluacion de confederaciones del GANADOR bayes (dinamico, halfyear).

1) Cara a cara venue-neutral a 2026-06-15: Argentina vs Espana, Australia vs
   EE.UU. (1X2, pick, xG).
2) Bridge-audit (estatico, 6 torneos): sesgo inter-confederacion.

Escribe data/tuning/bridge_bayes-winner.csv y deja los numeros del cara a cara
en data/tuning/bayes_eval.log.
"""
from wcpred.data import load_results, prepare_training
from wcpred.model_bayes import BayesianDixonColes
from wcpred.predict import predict_match
from wcpred.backtest import backtest, bridge_audit, TOURNAMENTS
import wcpred.config as cfg

df = load_results(cfg.RESULTS_PATH)
AS_OF = "2026-06-15"
PAIRS = [("Argentina", "Spain"), ("Australia", "United States")]
BLK = "halfyear"

print(f"=== cara a cara bayes-winner (dynamic {BLK}, neutral, {AS_OF}) ===",
      flush=True)
tm = prepare_training(df, AS_OF)
m = BayesianDixonColes().fit(tm, dynamic=True, time_block=BLK,
                             sigma_conf_scale=0.5, show_progress=False)
for h, a in PAIRS:
    r = predict_match(m, h, a, side=None)
    lam, mu = m.rates(h, a, None)
    print(f"{h} vs {a}: 1={r['p1']:.1%} X={r['px']:.1%} 2={r['p2']:.1%} | "
          f"pick {r['pick'][0]}-{r['pick'][1]} | xG {lam:.2f}-{mu:.2f}",
          flush=True)

print("\n=== bridge-audit bayes-winner (static, 6 torneos) ===", flush=True)
rec = []
for t in TOURNAMENTS:
    backtest(df, t, rolling=False, engine="bayes", dynamic=True,
             time_block=BLK, sigma_conf_scale=0.5, audit=rec)
tab = bridge_audit(rec)
tab.to_csv("data/tuning/bridge_bayes-winner.csv", index=False)
print(tab[["conf_a", "conf_b", "n", "exp_share_a", "real_share_a",
           "bias_a", "rps"]].to_string(index=False), flush=True)
print("DONE", flush=True)
