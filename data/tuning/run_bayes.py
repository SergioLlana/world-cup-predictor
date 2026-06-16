"""Rejilla completa de tuning del motor bayes (estático-only), reanudable.

Recorre dynamic x time_block x sigma_conf_scale x propagate, evalua cada
combinacion sobre los 6 torneos de backtest.TOURNAMENTS y agrega con
_pool_metrics (RPS agrupado, desempate por puntos Penka). Persiste UNA fila por
combinacion en data/tuning/bayes.csv en cuanto termina (flush a disco); al
rearrancar lee el CSV y salta las combinaciones ya hechas.

    uv run python data/tuning/run_bayes.py
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

SIGMAS = (0.1, 0.25, 0.5, 1.0)
BLOCKS = ("year", "halfyear", "quarter")


def configs():
    # estaticas primero (mas rapidas), luego dinamicas
    for prop in (False, True):
        for sig in SIGMAS:
            yield dict(dynamic=False, time_block=None,
                       sigma_conf_scale=sig, propagate=prop)
    for blk in BLOCKS:
        for prop in (False, True):
            for sig in SIGMAS:
                yield dict(dynamic=True, time_block=blk,
                           sigma_conf_scale=sig, propagate=prop)


def _tb(x):
    # None / "" / "None" all denote the static (no time-block) configs.
    return "none" if x in (None, "", "None") else str(x)


def key(c):
    return (str(c["dynamic"]), _tb(c["time_block"]),
            str(c["sigma_conf_scale"]), str(c["propagate"]))


def done_keys():
    if not os.path.exists(OUT):
        return set()
    with open(OUT) as f:
        return {(r["dynamic"], _tb(r["time_block"]), r["sigma_conf"],
                 r["propagate"]) for r in csv.DictReader(f)}


def main():
    df = load_results(cfg.RESULTS_PATH)
    ts = list(TOURNAMENTS)
    new = not os.path.exists(OUT)
    done = done_keys()
    all_cfgs = list(configs())
    pending = [c for c in all_cfgs if key(c) not in done]
    print(f"{len(all_cfgs)} configs totales, {len(done)} hechas, "
          f"{len(pending)} pendientes", flush=True)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
            f.flush()
        for i, c in enumerate(pending, 1):
            t0 = time.time()
            res = [backtest(df, t, rolling=False, engine="bayes",
                            dynamic=c["dynamic"], time_block=c["time_block"],
                            sigma_conf_scale=c["sigma_conf_scale"],
                            propagate=c["propagate"]) for t in ts]
            p = _pool_metrics(res)
            secs = round(time.time() - t0, 1)
            row = {"dynamic": c["dynamic"], "time_block": c["time_block"],
                   "sigma_conf": c["sigma_conf_scale"],
                   "propagate": c["propagate"], **p, "secs": secs}
            w.writerow(row)
            f.flush()
            os.fsync(f.fileno())
            print(f"[{i}/{len(pending)}] dynamic={c['dynamic']} "
                  f"block={c['time_block']} sigma={c['sigma_conf_scale']} "
                  f"prop={c['propagate']}: {p['points']:.0f} pts, "
                  f"rps {p['rps']:.4f}, ll {p['log_loss']:.4f} ({secs}s)",
                  flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
