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

from .anchor import anchor_model
from .backtest import TOURNAMENTS, backtest, bridge_audit, tune
from .config import (BAYES_DYNAMIC, BAYES_TIME_BLOCK, CONF_ANCHOR_BETA,
                     ELO_PATH, ELO_PRIOR_TAU, GROUPS_DIR, ODDS_WEIGHT,
                     PREDICTIONS_DIR, RESULTS_PATH, SCORING_MODE, SIM_DIR,
                     XG_ALPHA)
from .data import (PHANTOM_TEAM, download_results, load_elo, load_odds,
                   load_results, played_world_cup, prepare_training,
                   upcoming_world_cup)
from .groups import simulate_groups
from .model import DixonColes
from .predict import predict_fixtures
from .tournament import OFFICIAL_GROUPS, simulate_tournament

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
    if getattr(args, "engine", "dc") == "bayes":
        # The Bayesian engine has its own confederation-offset prior; the
        # MLE-only external anchors do not apply.
        if args.elo_tau or args.anchor_beta:
            sys.exit("--elo-tau / --anchor-beta are MLE-engine knobs; they "
                     "have no effect under --engine bayes")
        from .model_bayes import BayesianDixonColes
        model = BayesianDixonColes().fit(train, dynamic=args.bayes_dynamic,
                                         time_block=args.bayes_block)
        mode = (f"dynamic random-walk, block={args.bayes_block}"
                if args.bayes_dynamic else "static decay weights")
        print(f"Bayesian model sampled on {len(train)} matches "
              f"({mode}; as of {args.as_of}, xG={'yes' if xg else 'no'})")
        return model
    if getattr(args, "bayes_dynamic", False):
        sys.exit("--bayes-dynamic only applies to --engine bayes")
    elo = load_elo(args.as_of, args.elo) if args.elo_tau else None
    if args.elo_tau and not elo:
        sys.exit(f"--elo-tau needs an Elo snapshot dated <= --as-of in "
                 f"{args.elo} (run scripts/fetch_elo.py)")
    model = DixonColes().fit(train, elo=elo, elo_tau=args.elo_tau)
    if args.elo_tau:
        print(f"External Elo prior applied (tau={args.elo_tau})")
    if args.anchor_beta:
        anchor_model(model, df, args.as_of, beta=args.anchor_beta,
                     xg_path=xg, xg_alpha=args.xg_alpha)
        print(f"Confederation re-anchoring applied "
              f"(beta={args.anchor_beta})")
    print(f"Model trained on {len(train)} matches "
          f"(as of {args.as_of}, xG={'yes' if xg else 'no'})")
    return model


def load_run_inputs(args, to_date=None):
    """Shared `predict`/`groups`/`simulate` preamble: results DataFrame,
    fitted model and the World Cup fixtures from --as-of onward. Exits with a
    clear message when a fixture team is missing from the fitted model
    (predicting it would otherwise die on a KeyError deep in the model)."""
    df = load_results(args.data)
    model = build_model(df, args)
    fixtures = upcoming_world_cup(df, from_date=args.as_of, to_date=to_date)
    missing = sorted((set(fixtures["home_team"]) | set(fixtures["away_team"]))
                     - set(model.idx))
    if missing:
        sys.exit("fixture teams missing from the model (misspelt, or too few "
                 f"matches before --as-of): {', '.join(missing)}")
    return df, model, fixtures


def load_odds_df(args):
    """Odds DataFrame for the market-blended approaches, or None."""
    if args.approach not in ("odds", "full"):
        return None
    if not args.odds:
        sys.exit(f"--approach {args.approach} requires --odds FILE")
    return load_odds(args.odds)


def cmd_predict(args):
    to_date = None
    if args.days:
        to_date = str(date.fromisoformat(args.as_of) + timedelta(days=args.days))
    df, model, fixtures = load_run_inputs(args, to_date=to_date)
    if fixtures.empty:
        sys.exit("No upcoming World Cup fixtures found. "
                 "Run `wcpred update-data` first.")
    odds_df = load_odds_df(args)
    out = predict_fixtures(model, fixtures, odds_df,
                           odds_weight=args.odds_weight,
                           extra_time=args.extra_time or args.shootout,
                           shootout=args.shootout, scoring=args.scoring)
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
    df, model, fixtures = load_run_inputs(args)
    if fixtures.empty:
        sys.exit("No upcoming World Cup fixtures found. "
                 "Run `wcpred update-data` first.")
    played = played_world_cup(df, year=int(fixtures["date"].dt.year.min()),
                              as_of=args.as_of)
    odds_df = load_odds_df(args)
    tables = simulate_groups(model, fixtures, n_sims=args.sims, played=played,
                             groups=OFFICIAL_GROUPS, odds_df=odds_df,
                             odds_weight=args.odds_weight)
    note = f", counting {len(played)} played matches" if len(played) else ""
    blend = "market-blended" if odds_df is not None else "model-only"
    print(f"\nMonte Carlo group standings ({args.sims:,} sims{note}, {blend}) "
          f"— realistic outcomes, not pool-optimal picks\n")
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


def cmd_simulate(args):
    df, model, fixtures = load_run_inputs(args)
    played = played_world_cup(df, year=2026, as_of=args.as_of)
    if fixtures.empty and not len(played):
        sys.exit("No World Cup fixtures found. Run `wcpred update-data` first.")
    odds_df = load_odds_df(args)
    out = simulate_tournament(model, fixtures, n_sims=args.sims, played=played,
                              odds_df=odds_df, odds_weight=args.odds_weight)
    note = f", counting {len(played)} played matches" if len(played) else ""
    print(f"\nFull-tournament Monte Carlo ({args.sims:,} sims{note}) — "
          f"knockouts at a neutral venue, ties via extra time + penalties\n")
    print(out.to_string(index=False))
    if args.out:
        dest = resolve_out(args.out, SIM_DIR)
        out.to_csv(dest, index=False)
        print(f"\nSaved to {dest}")


def cmd_ratings(args):
    df = load_results(args.data)
    model = build_model(df, args)
    teams = sorted((t for t in model.idx if t != PHANTOM_TEAM),
                   key=lambda t: -(model.atk[model.idx[t]]
                                   - model.dfn[model.idx[t]]))
    print(f"\n{'#':>3} {'Team':22s} {'Attack':>7s} {'Defence':>8s} {'Overall':>8s}")
    for i, t in enumerate(teams[:args.top], 1):
        k = model.idx[t]
        print(f"{i:3d} {t:22s} {model.atk[k]:7.2f} {model.dfn[k]:8.2f} "
              f"{model.atk[k] - model.dfn[k]:8.2f}")


def cmd_backtest(args):
    df = load_results(args.data)
    names = list(TOURNAMENTS) if args.tournament == "all" else [args.tournament]
    audit = [] if args.bridge_audit else None
    for name in names:
        r = backtest(df, name, rolling=not args.static,
                     xg_path=args.xg if args.approach in ("xg", "full") else None,
                     xg_alpha=args.xg_alpha, scoring=args.scoring, audit=audit,
                     anchor_beta=args.anchor_beta,
                     elo_tau=args.elo_tau, elo_path=args.elo,
                     engine=args.engine, dynamic=args.bayes_dynamic,
                     time_block=args.bayes_block)
        print(f"Backtest {r['tournament']} ({args.scoring}): "
              f"{r['points']:.1f} pts in "
              f"{r['matches']} matches ({r['points_per_match']:.2f}/match) | "
              f"exact {r['exact']} | outcome correct {r['outcome_correct']} | "
              f"rps {r['rps']:.4f} | log-loss {r['log_loss']:.4f}")
    if audit is not None:
        if not audit:
            print("\nBridge audit: no inter-confederation matches in the "
                  "selected tournaments (Euros/Copas are intra-confederation; "
                  "use --tournament all or a World Cup).")
            return
        table = bridge_audit(audit)
        print(f"\nBridge audit — {len(audit)} inter-confederation matches, "
              "share = win + draw/2 from conf_a's perspective "
              "(bias_a > 0: model overrates conf_a):\n")
        print(table.to_string(index=False, float_format=lambda v: f"{v:+.3f}"
                              if v < 0 else f"{v:.3f}"))


def cmd_tune(args):
    df = load_results(args.data)
    if args.shrinkage:
        # Phase 1 grid (docs/model-robustness-plan.md): sweep the shrinkage
        # knobs alone, other hyperparameters held at today's defaults.
        table = tune(df, rolling=args.rolling, gd_caps=(None,),
                     half_lives=(730,), friendly_weights=(1.0,),
                     shrinkages=[(None, 0.0)]
                                + [(m, e) for m in ("phantom", "pseudo")
                                   for e in (0.25, 0.5, 1.0, 2.0)])
    elif args.anchor:
        # Phase 2b grid (docs/model-robustness-plan.md): sweep the
        # confederation re-anchoring blend alone, other hyperparameters held
        # at today's defaults.
        table = tune(df, rolling=args.rolling, gd_caps=(None,),
                     half_lives=(730,), friendly_weights=(1.0,),
                     anchor_betas=(0.0, 0.25, 0.5, 0.75, 1.0))
    elif args.elo:
        # Phase 3 grid (docs/model-robustness-plan.md): sweep the external
        # Elo prior weight alone, other hyperparameters held at today's
        # defaults.
        table = tune(df, rolling=args.rolling, gd_caps=(None,),
                     half_lives=(730,), friendly_weights=(1.0,),
                     elo_taus=(0.0, 0.5, 1.0, 2.0, 5.0, 10.0))
    else:
        table = tune(df, rolling=args.rolling)
    print("\nGrid sorted by pooled RPS (lower is better):\n")
    print(table.to_string(index=False))
    b = table.iloc[0]
    print(f"\nBest by RPS: gd_cap={b.gd_cap} half_life={int(b.half_life)} "
          f"friendly_w={b.friendly_w} cross_conf_w={b.cross_conf_w} "
          f"shrinkage={b.shrink_mode}:{b.shrink_w} anchor={b.anchor_beta} "
          f"elo_tau={b.elo_tau} "
          f"({b.pts_per_match:.3f} pts/match, rps {b.rps:.4f})")
    print("Re-validate the winner with `wcpred backtest --tournament all` "
          "(rolling re-fit) before changing config.py.")


def main():
    p = argparse.ArgumentParser(prog="wcpred",
                                description="World Cup score predictor "
                                            "(Penka by default; Superbru via "
                                            "--scoring superbru)")
    p.add_argument("--data", default=RESULTS_PATH,
                   help=f"path to results.csv (default: {RESULTS_PATH})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("update-data", help="download latest results dataset")

    def common(sp):
        sp.add_argument("--approach", choices=APPROACHES, default="history",
                        help="information sources to use (default: history)")
        sp.add_argument("--engine", choices=("dc", "bayes"), default="dc",
                        help="rating model: 'dc' = MLE Dixon-Coles (default, "
                             "the regenerable production model), 'bayes' = "
                             "Stan Dixon-Coles with a hierarchical "
                             "confederation-offset prior (needs the bayes "
                             "extra; backtest static only)")
        sp.add_argument("--bayes-dynamic", action="store_true",
                        default=BAYES_DYNAMIC,
                        help="Phase B1: under --engine bayes, evolve team "
                             "strengths as a random walk over time blocks "
                             "(replacing the decay weighting) and predict from "
                             "the most recent block (default: off)")
        sp.add_argument("--bayes-block", choices=("year", "halfyear", "quarter"),
                        default=BAYES_TIME_BLOCK,
                        help="random-walk block granularity for --bayes-dynamic "
                             "(default: %(default)s)")
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
        sp.add_argument("--scoring", choices=("penka", "superbru"),
                        default=SCORING_MODE,
                        help="game mode whose expected points the picks "
                             "maximise (default: %(default)s)")
        sp.add_argument("--anchor-beta", type=float, default=CONF_ANCHOR_BETA,
                        help="Phase 2b confederation re-anchoring blend: 0 = "
                             "off, 1 = adopt the long-window confederation "
                             "levels fully (default: %(default)s)")
        sp.add_argument("--elo-tau", type=float, default=ELO_PRIOR_TAU,
                        help="Phase 3 external Elo prior weight: 0 = off "
                             "(default: %(default)s)")
        sp.add_argument("--elo", default=ELO_PATH,
                        help="dated Elo snapshots CSV (date,team,elo; "
                             "default: %(default)s)")

    sp = sub.add_parser("predict", help="predict upcoming WC fixtures")
    common(sp)
    sp.add_argument("--days", type=int,
                    help="only fixtures within N days of --as-of")
    sp.add_argument("--out", help="save predictions CSV here (a bare filename "
                    f"goes under {PREDICTIONS_DIR}/)")
    sp.add_argument("--extra-time", action="store_true",
                    help="resolve knockout draws through extra time "
                         "(default off: Penka and Superbru score the "
                         "90' result)")
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

    sp = sub.add_parser("simulate", help="simulate the full tournament bracket")
    common(sp)
    sp.add_argument("--sims", type=int, default=100000,
                    help="Monte Carlo simulations (default: 100000)")
    sp.add_argument("--out", help="save per-team probabilities CSV here (a bare "
                    f"filename goes under {SIM_DIR}/)")
    sp.set_defaults(func=cmd_simulate)

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
    sp.add_argument("--bridge-audit", action="store_true",
                    help="also report predicted-vs-realised calibration on "
                         "inter-confederation matches, pooled across the "
                         "backtested tournaments (regional-bias test)")
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("tune", help="grid-search training hyperparameters "
                                     "across all backtest tournaments (no xG)")
    sp.add_argument("--rolling", action="store_true",
                    help="rolling re-fit during the grid (slow; default is a "
                         "single pre-tournament fit per config)")
    sp.add_argument("--shrinkage", action="store_true",
                    help="sweep the Phase 1 cross-confederation shrinkage "
                         "knobs (SHRINKAGE_MODE x SHRINKAGE_WEIGHT) instead "
                         "of the standard hyperparameter grid")
    sp.add_argument("--anchor", action="store_true",
                    help="sweep the Phase 2b confederation re-anchoring "
                         "blend (CONF_ANCHOR_BETA) instead of the standard "
                         "hyperparameter grid")
    sp.add_argument("--elo", action="store_true",
                    help="sweep the Phase 3 external Elo prior weight "
                         "(ELO_PRIOR_TAU) instead of the standard "
                         "hyperparameter grid")
    sp.set_defaults(func=cmd_tune)

    args = p.parse_args()
    if args.cmd == "update-data":
        download_results(args.data)
        return
    args.func(args)


if __name__ == "__main__":
    main()
