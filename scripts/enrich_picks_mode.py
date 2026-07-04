#!/usr/bin/env python3
"""Add the `pick_mode` column (mode of the score matrix — the single most likely
exact scoreline, independent of Penka) to existing data/predictions/picks_*.csv
snapshots, WITHOUT touching the original columns.

New snapshots already carry `pick_mode` (predict.predict_fixtures). This
back-fills the old ones so the public webapp calendar can show the most probable
scoreline. It mirrors enrich_picks_outcome.py: existing rows are preserved
exactly (read as text, written back byte-for-byte) and `pick_mode` is mapped in
by fixture key, so no future-known knockout fixtures leak into a past snapshot —
freshly listed fixtures that weren't in the snapshot are simply ignored.

Engines: dc and elo (bayes is local-only and uses the ev/outcome toggle). Run
from the project root: `python scripts/enrich_picks_mode.py`.
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

# pick_mode goes right before odds_used, matching predict_fixtures' output.
SCHEMA = ["date", "home", "away", "stage", "P_1", "P_X", "P_2", "pick",
          "expected_points", "pick_outcome", "expected_points_outcome",
          "pick_mode", "odds_used"]
_RE = re.compile(r"picks_(odds|history)_(dc|elo)_(\d{4}-\d{2}-\d{2})\.csv$")


def _build(engine, as_of, tm, df):
    if engine == "dc":
        return DixonColes().fit(tm)
    return EloDixonColes().fit(tm, df=df, as_of=as_of)


def main():
    df = load_results()
    done = skip = missing_total = 0
    for f in sorted(glob.glob("data/predictions/picks_*.csv")):
        m = _RE.search(f)
        if not m:
            continue
        approach, engine, as_of = m.groups()
        ex = pd.read_csv(f, dtype=str)
        if "pick_mode" in ex.columns:
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
        pm = {r.k: r.pick_mode for r in fresh.itertuples()}
        ex["k"] = ex["date"].astype(str) + "|" + ex["home"] + "|" + ex["away"]
        ex["pick_mode"] = ex["k"].map(pm)
        missing = int(ex["pick_mode"].isna().sum())
        missing_total += missing
        if missing:
            print(f"  ! {f}: {missing} rows without a recomputed pick_mode")
        ex.drop(columns=["k"])[SCHEMA].to_csv(f, index=False)
        done += 1
    print(f"\nEnriched: {done} · already had the column: {skip} · "
          f"rows left blank: {missing_total}")


if __name__ == "__main__":
    main()
