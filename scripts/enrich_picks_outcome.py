#!/usr/bin/env python3
"""Add the `pick_outcome`/`expected_points_outcome` columns (strategy C) to
existing data/predictions/picks_*.csv snapshots, WITHOUT touching the original
`ev` columns.

New snapshots already carry both columns (predict.predict_fixtures). This
back-fills the old ones so the webapp's strategy toggle works across the whole
calendar. The `ev` columns are read as text and written back byte-for-byte; only
the two outcome columns are appended — so the historical record of what was
played stays intact (a freshly recomputed `ev` pick can drift slightly if
results.csv changed since; that drift is reported, never applied).

Engines: dc and elo (bayes is slow — its outcome view falls back to ev). Run
from the project root: `python scripts/enrich_picks_outcome.py`.
"""
import glob
import re

import pandas as pd

from wcpred.backtest import TRAIN_WINDOW_YEARS
from wcpred.data import (load_odds, load_results, prepare_training,
                         resolve_odds_path, upcoming_world_cup)
from wcpred.model import DixonColes
from wcpred.model_elo import EloDixonColes
from wcpred.predict import predict_fixtures

SCHEMA = ["date", "home", "away", "stage", "P_1", "P_X", "P_2", "pick",
          "expected_points", "pick_outcome", "expected_points_outcome",
          "odds_used"]
_RE = re.compile(r"picks_(odds|history)_(dc|elo)_(\d{4}-\d{2}-\d{2})\.csv$")


def _build(engine, as_of, tm, df):
    if engine == "dc":
        return DixonColes().fit(tm)
    return EloDixonColes().fit(tm, df=df, as_of=as_of)


def main():
    df = load_results()
    done = skip = drift_total = 0
    for f in sorted(glob.glob("data/predictions/picks_*.csv")):
        m = _RE.search(f)
        if not m:
            continue
        approach, engine, as_of = m.groups()
        ex = pd.read_csv(f, dtype=str)
        if "pick_outcome" in ex.columns:
            skip += 1
            continue
        train_start = str((pd.Timestamp(as_of)
                           - pd.DateOffset(years=TRAIN_WINDOW_YEARS)).date())
        tm = prepare_training(df, as_of, train_start=train_start)
        model = _build(engine, as_of, tm, df)
        fixtures = upcoming_world_cup(df, from_date=as_of)
        odds_df = None
        if approach == "odds":
            op = resolve_odds_path(as_of)
            if op:
                odds_df = load_odds(op)
        fresh = predict_fixtures(model, fixtures, odds_df)
        fresh["k"] = (fresh["date"].astype(str) + "|" + fresh["home"]
                      + "|" + fresh["away"])
        po = {r.k: r.pick_outcome for r in fresh.itertuples()}
        epo = {r.k: f"{r.expected_points_outcome:g}" for r in fresh.itertuples()}
        evp = {r.k: r.pick for r in fresh.itertuples()}
        ex["k"] = ex["date"].astype(str) + "|" + ex["home"] + "|" + ex["away"]
        drift = sum(1 for _, row in ex.iterrows()
                    if row["k"] in evp and evp[row["k"]] != row["pick"])
        drift_total += drift
        ex["pick_outcome"] = ex["k"].map(po)
        ex["expected_points_outcome"] = ex["k"].map(epo)
        ex.drop(columns=["k"])[SCHEMA].to_csv(f, index=False)
        done += 1
        if drift:
            print(f"  ! {f}: {drift} rows with a different recomputed ev pick "
                  "(ev column left untouched)")
    print(f"\nEnriched: {done} · already had the column: {skip} · "
          f"ev drift rows: {drift_total}")


if __name__ == "__main__":
    main()
