"""Cierre de la rejilla bayes: granularidad del bloque dinamico.

El barrido estatico y el dinamico-year ya demostraron que sigma_conf y propagate
son planos (ruido en el 4o decimal). La unica pregunta dinamica que queda es la
GRANULARIDAD del bloque temporal: year (hecho) vs halfyear vs quarter. Se corren
esos dos al sigma/prop representativos (0.5 / False).

Las dinamicas finas (mas bloques -> mas parametros) fallan a veces el muestreo;
por eso cada config se reintenta con otra semilla. Resultado anexado a la misma
data/tuning/bayes.csv (esquema compatible). Reanudable.

    uv run python data/tuning/run_bayes_blocks.py
"""
import csv
import os
import time

from wcpred.backtest import backtest, _pool_metrics, TOURNAMENTS
from wcpred.data import load_results
import wcpred.config as cfg

OUT = "data/tuning/bayes.csv"
FIELDS = ["dynamic", "time_block", "sigma_conf", "propagate",
          "matches", "points", "pts_per_match", "exact", "rps", "log_loss",
          "secs"]
SEEDS = (2026, 777, 555)            # reintentos ante fallo de muestreo


def done_blocks():
    if not os.path.exists(OUT):
        return set()
    with open(OUT) as f:
        return {r["time_block"] for r in csv.DictReader(f) if r["dynamic"] == "True"}


def main():
    df = load_results(cfg.RESULTS_PATH)
    ts = list(TOURNAMENTS)
    done = done_blocks()
    pending = [b for b in ("halfyear", "quarter") if b not in done]
    print(f"bloques dinamicos pendientes: {pending}", flush=True)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        for blk in pending:
            t0 = time.time()
            res, err = None, None
            for sd in SEEDS:
                try:
                    res = [backtest(df, t, rolling=False, engine="bayes",
                                    dynamic=True, time_block=blk,
                                    sigma_conf_scale=0.5, propagate=False,
                                    bayes_seed=sd) for t in ts]
                    break
                except Exception as e:                       # noqa: BLE001
                    err = e
                    print(f"  [{blk}] fallo con seed={sd}: "
                          f"{type(e).__name__}; reintento", flush=True)
            if res is None:
                print(f"  [{blk}] DESCARTADO tras {len(SEEDS)} semillas: {err}",
                      flush=True)
                continue
            p = _pool_metrics(res)
            secs = round(time.time() - t0, 1)
            w.writerow({"dynamic": True, "time_block": blk, "sigma_conf": 0.5,
                        "propagate": False, **p, "secs": secs})
            f.flush(); os.fsync(f.fileno())
            print(f"  [{blk}] {p['points']:.0f} pts, rps {p['rps']:.4f}, "
                  f"ll {p['log_loss']:.4f} ({secs}s)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
