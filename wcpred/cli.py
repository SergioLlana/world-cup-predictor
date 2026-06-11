"""Command-line interface.

Usage examples:
    wcpred update-data
    wcpred predict --approach history
    wcpred predict --approach odds --odds odds.csv --days 3
    wcpred predict --approach xg --xg xg.csv
    wcpred predict --approach full --odds odds.csv --xg xg.csv
    wcpred ratings --top 20
    wcpred backtest --tournament wc2022
"""
import argparse
import os
import sys
from datetime import date, timedelta

import pandas as pd

from .backtest import TOURNAMENTS, backtest, tune
from .config import (GROUPS_DIR, ODDS_WEIGHT, PREDICTIONS_DIR, RESULTS_PATH,
                     XG_ALPHA)
from .data import (download_results, load_odds, load_results,
                   played_world_cup, prepare_training, upcoming_world_cup)
from .groups import simulate_groups
from .model import DixonColes
from .predict import predict_fixtures

APPROACHES = ("history", "odds", "xg", "full")


def resolve_out(path, default_dir):
    """Resolve a `--out` value so generated files stay out of the project root.

    A bare filename (no directory part) is placed under `default_dir`; a path
    that already names a directory is honoured as-is. The parent directory is
    created either way. Returns the resolved path (or None if path is None)."""
    if path is None:
        return None
    if not os.path.dirname(path):
        path = os.path.join(default_dir, path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def build_model(df, args):
    if args.approach == "xg" and not args.xg:
        sys.exit("--approach xg requires --xg FILE")
    xg = args.xg if args.approach in ("xg", "full") else None
    train = prepare_training(df, as_of=args.as_of, xg_path=xg,
                             xg_alpha=args.xg_alpha)
    model = DixonColes().fit(train)
    print(f"Model trained on {len(train)} matches "
          f"(as of {args.as_of}, xG={'yes' if xg else 'no'})")
    return model


def cmd_predict(args):
    df = load_results(args.data)
    model = build_model(df, args)
    to_date = None
    if args.days:
        to_date = str(date.fromisoformat(args.as_of) + timedelta(days=args.days))
    fixtures = upcoming_world_cup(df, from_date=args.as_of, to_date=to_date)
    if fixtures.empty:
        sys.exit("No upcoming World Cup fixtures found. "
                 "Run `wcpred update-data` first.")
    odds_df = None
    if args.approach in ("odds", "full"):
        if not args.odds:
            sys.exit("--approach odds requires --odds FILE")
        odds_df = load_odds(args.odds)
    out = predict_fixtures(model, fixtures, odds_df,
                           odds_weight=args.odds_weight,
                           extra_time=args.extra_time or args.shootout,
                           shootout=args.shootout)
    print()
    print(out.to_string(index=False))
    print(f"\nTotal expected points: {out.expected_points.sum():.1f}")
    if odds_df is not None:
        missing = (~out.odds_used).sum()
        if missing:
            print(f"WARNING: {missing} fixtures had no odds in {args.odds}; "
                  f"model-only predictions used for those.")
    if args.out:
        dest = resolve_out(args.out, PREDICTIONS_DIR)
        out.to_csv(dest, index=False)
        print(f"Saved to {dest}")


def cmd_groups(args):
    df = load_results(args.data)
    model = build_model(df, args)
    fixtures = upcoming_world_cup(df, from_date=args.as_of)
    if fixtures.empty:
        sys.exit("No upcoming World Cup fixtures found. "
                 "Run `wcpred update-data` first.")
    played = played_world_cup(df, year=int(fixtures["date"].dt.year.min()),
                              as_of=args.as_of)
    tables = simulate_groups(model, fixtures, n_sims=args.sims, played=played)
    note = f", counting {len(played)} played matches" if len(played) else ""
    print(f"\nMonte Carlo group standings ({args.sims:,} sims{note}) — "
          f"realistic outcomes, not Superbru-optimal picks\n")
    frames = []
    for label, t in tables.items():
        disp = t.copy()
        disp.insert(0, "pos", range(1, len(disp) + 1))
        disp.insert(1, "Q", ["Y" if i < 2 else "" for i in range(len(disp))])
        print(f"Group {label}")
        print(disp.to_string(index=False))
        print()
        t.insert(0, "group", label)
        frames.append(t)
    if args.out:
        dest = resolve_out(args.out, GROUPS_DIR)
        pd.concat(frames).to_csv(dest, index=False)
        print(f"Saved to {dest}")


def cmd_ratings(args):
    df = load_results(args.data)
    model = build_model(df, args)
    teams = sorted(model.idx, key=lambda t: -(model.atk[model.idx[t]]
                                              - model.dfn[model.idx[t]]))
    print(f"\n{'#':>3} {'Team':22s} {'Attack':>7s} {'Defence':>8s} {'Overall':>8s}")
    for i, t in enumerate(teams[:args.top], 1):
        k = model.idx[t]
        print(f"{i:3d} {t:22s} {model.atk[k]:7.2f} {model.dfn[k]:8.2f} "
              f"{model.atk[k] - model.dfn[k]:8.2f}")


def cmd_backtest(args):
    df = load_results(args.data)
    names = list(TOURNAMENTS) if args.tournament == "all" else [args.tournament]
    for name in names:
        r = backtest(df, name, rolling=not args.static,
                     xg_path=args.xg if args.approach in ("xg", "full") else None,
                     xg_alpha=args.xg_alpha)
        print(f"Backtest {r['tournament']}: {r['points']:.1f} pts in "
              f"{r['matches']} matches ({r['points_per_match']:.2f}/match) | "
              f"exact {r['exact']} | outcome correct {r['outcome_correct']} | "
              f"rps {r['rps']:.4f} | log-loss {r['log_loss']:.4f}")


def cmd_tune(args):
    df = load_results(args.data)
    table = tune(df, rolling=args.rolling)
    print("\nGrid sorted by pooled RPS (lower is better):\n")
    print(table.to_string(index=False))
    b = table.iloc[0]
    print(f"\nBest by RPS: gd_cap={b.gd_cap} half_life={int(b.half_life)} "
          f"friendly_w={b.friendly_w} "
          f"({b.pts_per_match:.3f} pts/match, rps {b.rps:.4f})")
    print("Re-validate the winner with `wcpred backtest --tournament all` "
          "(rolling re-fit) before changing config.py.")


def main():
    p = argparse.ArgumentParser(prog="wcpred",
                                description="World Cup Superbru predictor")
    p.add_argument("--data", default=RESULTS_PATH,
                   help=f"path to results.csv (default: {RESULTS_PATH})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("update-data", help="download latest results dataset")

    def common(sp):
        sp.add_argument("--approach", choices=APPROACHES, default="history",
                        help="information sources to use (default: history)")
        sp.add_argument("--odds", help="odds CSV (home_team,away_team,"
                                       "odds_1,odds_X,odds_2)")
        sp.add_argument("--xg", help="xG CSV (date,home_team,away_team,"
                                     "home_xg,away_xg)")
        sp.add_argument("--as-of", default=str(date.today()),
                        help="train on matches before this date "
                             "(default: today)")
        sp.add_argument("--odds-weight", type=float, default=ODDS_WEIGHT)
        sp.add_argument("--xg-alpha", type=float, default=XG_ALPHA,
                        help="effective_goals = alpha*goals + (1-alpha)*xG; "
                             "0 = pure xG, 1 = pure goals (default: %(default)s)")

    sp = sub.add_parser("predict", help="predict upcoming WC fixtures")
    common(sp)
    sp.add_argument("--days", type=int,
                    help="only fixtures within N days of --as-of")
    sp.add_argument("--out", help="save predictions CSV here (a bare filename "
                    f"goes under {PREDICTIONS_DIR}/)")
    sp.add_argument("--extra-time", action="store_true",
                    help="resolve knockout draws through extra time "
                         "(default off: Superbru scores the 90' result)")
    sp.add_argument("--shootout", action="store_true",
                    help="also resolve still-level ties as a penalty "
                         "shootout (implies --extra-time)")
    sp.set_defaults(func=cmd_predict)

    sp = sub.add_parser("groups", help="simulate final group standings")
    common(sp)
    sp.add_argument("--sims", type=int, default=1000000,
                    help="Monte Carlo simulations per group (default: 1000000)")
    sp.add_argument("--out", help="save standings CSV here (a bare filename "
                    f"goes under {GROUPS_DIR}/)")
    sp.set_defaults(func=cmd_groups)

    sp = sub.add_parser("ratings", help="show team strength ratings")
    common(sp)
    sp.add_argument("--top", type=int, default=20)
    sp.set_defaults(func=cmd_ratings)

    sp = sub.add_parser("backtest", help="score the model on a past tournament")
    common(sp)
    sp.add_argument("--tournament", choices=list(TOURNAMENTS) + ["all"],
                    default="wc2022")
    sp.add_argument("--static", action="store_true",
                    help="single pre-tournament fit instead of the default "
                         "rolling per-matchday re-fit")
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("tune", help="grid-search training hyperparameters "
                                     "across all backtest tournaments (no xG)")
    sp.add_argument("--rolling", action="store_true",
                    help="rolling re-fit during the grid (slow; default is a "
                         "single pre-tournament fit per config)")
    sp.set_defaults(func=cmd_tune)

    args = p.parse_args()
    if args.cmd == "update-data":
        download_results(args.data)
        return
    args.func(args)


if __name__ == "__main__":
    main()
