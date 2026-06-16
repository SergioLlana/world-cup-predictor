"""Experimento: prior de confederacion INFORMATIVO (no media-cero) en bayes.

Medias de bloque ancladas al Elo in-house (beta auto-calibrada,
backtest.elo_conf_strength). Dos modos:
  - capped: offsets winsorizados a +-0.4 (doma el pico de CONMEBOL)
  - weak:   solo bajar AFC/OFC/CONCACAF/CAF (UEFA/CONMEBOL data-driven)
x dos fuerzas de prior sigma_conf_scale in {0.1 (apretado), 0.5 (default)}.

Reanudable: una fila por config en data/tuning/bayes_informed.csv.

    uv run python data/tuning/run_informed.py
"""
import csv
import os
import time

from wcpred.backtest import backtest, _pool_metrics, TOURNAMENTS
from wcpred.data import load_results
import wcpred.config as cfg

OUT = "data/tuning/bayes_informed.csv"
FIELDS = ["mode", "sigma_conf", "matches", "points", "pts_per_match",
          "exact", "rps", "log_loss", "secs"]


def configs():
    for mode in ("capped", "weak"):
        for sig in (0.1, 0.5):
            yield mode, sig


def done_keys():
    if not os.path.exists(OUT):
        return set()
    with open(OUT) as f:
        return {(r["mode"], r["sigma_conf"]) for r in csv.DictReader(f)}


def main():
    df = load_results(cfg.RESULTS_PATH)
    ts = list(TOURNAMENTS)
    new = not os.path.exists(OUT)
    done = done_keys()
    pending = [c for c in configs() if (c[0], str(c[1])) not in done]
    print(f"{len(pending)} configs pendientes", flush=True)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader(); f.flush()
        for i, (mode, sig) in enumerate(pending, 1):
            t0 = time.time()
            res = [backtest(df, t, rolling=False, engine="bayes",
                            informed_conf=mode, sigma_conf_scale=sig)
                   for t in ts]
            p = _pool_metrics(res)
            secs = round(time.time() - t0, 1)
            w.writerow({"mode": mode, "sigma_conf": sig, **p, "secs": secs})
            f.flush(); os.fsync(f.fileno())
            print(f"[{i}/{len(pending)}] mode={mode} sigma={sig}: "
                  f"{p['points']:.0f} pts, rps {p['rps']:.4f}, "
                  f"ll {p['log_loss']:.4f} ({secs}s)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
