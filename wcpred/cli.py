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
from .backtest import (TOURNAMENTS, backtest, bridge_audit, elo_report, tune,
                       tune_elo)
from .config import (BAYES_CONNECT_BY, BAYES_CONNECT_MODE,
                     BAYES_CONNECT_OPP_REF, BAYES_CONNECT_REF,
                     BAYES_CONNECT_SHRINK, BAYES_DYNAMIC,
                     BAYES_PROPAGATE, BAYES_SIGMA_CONF_SCALE,
                     BAYES_TIME_BLOCK, CONF_ANCHOR_BETA, ELO_HA,
                     ELO_LONGTERM_YEARS, GROUPS_DIR,
                     ODDS_WEIGHT, PICK_STRATEGY, PREDICTIONS_DIR, RANKINGS_DIR,
                     RESULTS_PATH, SCORING_MODE, SIM_DIR, XG_ALPHA)
from .confederations import infer_confederations
from .data import (PHANTOM_TEAM, download_results, load_odds,
                   load_results, played_world_cup, prepare_training,
                   upcoming_world_cup)
from .groups import simulate_groups
from .model import DixonColes
from .predict import WC2026_R32_START, predict_fixtures
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
        # MLE-only re-anchoring does not apply.
        if args.anchor_beta:
            sys.exit("--anchor-beta is an MLE-engine parameter; it "
                     "has no effect under --engine bayes")
        from .model_bayes import BayesianDixonColes
        model = BayesianDixonColes().fit(train, dynamic=args.bayes_dynamic,
                                         time_block=args.bayes_block,
                                         sigma_conf_scale=args.bayes_sigma_conf,
                                         propagate=args.bayes_propagate,
                                         connect_shrink=args.bayes_connect,
                                         connect_ref=args.bayes_connect_ref,
                                         connect_mode=args.bayes_connect_mode,
                                         connect_by=args.bayes_connect_by,
                                         connect_opp_ref=args.bayes_connect_opp_ref)
        mode = (f"dynamic random-walk, block={args.bayes_block}"
                if args.bayes_dynamic else "static decay weights")
        if args.bayes_propagate:
            mode += ", posterior propagation"
        if args.bayes_connect:
            _ref = (args.bayes_connect_opp_ref if args.bayes_connect_by == "opp"
                    else args.bayes_connect_ref)
            mode += (f", connectivity {args.bayes_connect_mode} shrinkage by "
                     f"{args.bayes_connect_by} (ref={_ref})")
        print(f"Bayesian model sampled on {len(train)} matches "
              f"({mode}; as of {args.as_of}, xG={'yes' if xg else 'no'})")
        return model
    if getattr(args, "bayes_dynamic", False):
        sys.exit("--bayes-dynamic only applies to --engine bayes")
    # --bayes-propagate is default-on (BAYES_PROPAGATE), so it is set even when
    # the user never asked for it; it is a no-op for the non-bayes engines, so
    # ignore it silently here rather than erroring.
    if getattr(args, "bayes_connect", False):
        sys.exit("--bayes-connect only applies to --engine bayes")
    if getattr(args, "engine", "dc") == "elo":
        # The Elo engine trains its own anchor; the MLE-only re-anchoring and
        # the bayes flags do not apply.
        if args.anchor_beta:
            sys.exit("--anchor-beta is an MLE-engine parameter; it has "
                     "no effect under --engine elo (it trains its own Elo)")
        from .model_elo import EloDixonColes
        model = EloDixonColes().fit(train, df=df, as_of=args.as_of)
        print(f"Elo model: eloratings.net (HA={ELO_HA}, "
              f"long-term {ELO_LONGTERM_YEARS}y) calibrated on {len(train)} "
              f"matches (as of {args.as_of}, xG={'yes' if xg else 'no'})")
        return model
    model = DixonColes().fit(train)
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
    # Only group-stage results feed the standings: from the quarter-finals on
    # a knockout rematch can pair two teams of the same group, and
    # groups._group_points would tally it as a fourth group match.
    played = played[played["date"] < pd.Timestamp(WC2026_R32_START)]
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
    ko_note = ("scheduled knockout ties market-priced at their venue, the "
               "rest at a neutral venue" if odds_df is not None
               else "knockouts at a neutral venue")
    print(f"\nFull-tournament Monte Carlo ({args.sims:,} sims{note}) — "
          f"{ko_note}, ties via extra time + penalties\n")
    print(out.to_string(index=False))
    if args.out:
        dest = resolve_out(args.out, SIM_DIR)
        out.to_csv(dest, index=False)
        print(f"\nSaved to {dest}")


def cmd_ratings(args):
    df = load_results(args.data)
    model = build_model(df, args)
    overall = {t: float(model.atk[i] - model.dfn[i])
               for t, i in model.idx.items() if t != PHANTOM_TEAM}
    elo_cur = getattr(model, "elo_cur", None)   # only the Elo engine has it
    # Rank by the engine's headline number: raw Elo for the Elo engine (matches
    # the webapp), attack-minus-defence rating for the coefficient engines.
    sort_key = ((lambda t: -float(elo_cur[model.idx[t]])) if elo_cur is not None
                else (lambda t: -overall[t]))
    teams = sorted(overall, key=sort_key)
    print(f"\n{'#':>3} {'Team':22s} {'Attack':>7s} {'Defence':>8s} {'Overall':>8s}")
    for i, t in enumerate(teams[:args.top], 1):
        k = model.idx[t]
        print(f"{i:3d} {t:22s} {model.atk[k]:7.2f} {model.dfn[k]:8.2f} "
              f"{model.atk[k] - model.dfn[k]:8.2f}")

    if not args.out:
        return
    # Full ranking CSV for the daily snapshots (scripts/generate_rankings.sh):
    # every team's coefficients plus its confederation and the weighted mean
    # opponent rating (schedule difficulty), so the evolution can be tracked.
    xg = args.xg if args.approach in ("xg", "full") else None
    train = prepare_training(df, as_of=args.as_of, xg_path=xg,
                             xg_alpha=args.xg_alpha)
    confs = infer_confederations(train)
    opp_w, w_tot = {}, {}
    for r in train.itertuples():
        w = float(r.w)
        for team, opp in ((r.home_team, r.away_team), (r.away_team, r.home_team)):
            if team in model.idx and opp in overall:
                opp_w[team] = opp_w.get(team, 0.0) + w * overall[opp]
                w_tot[team] = w_tot.get(team, 0.0) + w
    rows = []
    for rank, t in enumerate(teams, 1):
        k = model.idx[t]
        row = {
            "as_of": args.as_of, "engine": args.engine, "rank": rank,
            "team": t, "confederation": confs.get(t),
            "attack": round(float(model.atk[k]), 4),
            "defence": round(float(model.dfn[k]), 4),
            "rating": round(overall[t], 4),
            "opp_rating": (round(opp_w[t] / w_tot[t], 4)
                           if w_tot.get(t) else None),
        }
        if elo_cur is not None:
            row["elo"] = round(float(elo_cur[k]), 1)
        rows.append(row)
    dest = resolve_out(args.out, RANKINGS_DIR)
    pd.DataFrame(rows).to_csv(dest, index=False)
    print(f"\nSaved {len(rows)} ratings to {dest}")


def cmd_backtest(args):
    # Validate engine/flag combinations up front so a usage slip prints a clean
    # message instead of an uncaught ValueError traceback from backtest().
    if args.engine == "bayes" and not args.static:
        sys.exit("--engine bayes is static only; add --static "
                 "(a per-matchday MCMC re-fit is prohibitively slow)")
    if args.engine == "bayes" and args.anchor_beta:
        sys.exit("--anchor-beta is an MLE-engine parameter; it has no "
                 "effect under --engine bayes")
    # --bayes-propagate is default-on (BAYES_PROPAGATE) and a no-op for the
    # non-bayes engines, so don't error on it here — only the off-by-default
    # bayes flags signal a genuine engine mismatch.
    if args.engine != "bayes" and (args.bayes_dynamic or args.bayes_connect):
        sys.exit("--bayes-dynamic / --bayes-connect only "
                 "apply to --engine bayes")
    if args.engine == "elo" and args.anchor_beta:
        sys.exit("--anchor-beta is an MLE-engine parameter; it has no "
                 "effect under --engine elo (it trains its own Elo)")
    df = load_results(args.data)
    names = list(TOURNAMENTS) if args.tournament == "all" else [args.tournament]
    audit = [] if args.bridge_audit else None
    for name in names:
        r = backtest(df, name, rolling=not args.static,
                     xg_path=args.xg if args.approach in ("xg", "full") else None,
                     xg_alpha=args.xg_alpha, scoring=args.scoring, audit=audit,
                     anchor_beta=args.anchor_beta,
                     engine=args.engine, dynamic=args.bayes_dynamic,
                     time_block=args.bayes_block,
                     sigma_conf_scale=args.bayes_sigma_conf,
                     propagate=args.bayes_propagate,
                     connect_shrink=args.bayes_connect,
                     connect_ref=args.bayes_connect_ref,
                     connect_mode=args.bayes_connect_mode,
                     connect_by=args.bayes_connect_by,
                     connect_opp_ref=args.bayes_connect_opp_ref,
                     pick_strategy=args.pick_strategy)
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
    if args.elo_engine:
        # Elo engine (--engine elo): coordinate tuning of the long-term
        # window, home advantage and the per-confederation K (RPS-driven), then
        # a rolling re-fit re-validation of the winner vs the default config.
        scalar_df, conf_df, best = tune_elo(df, rolling=args.rolling)
        print("\nStep 1 — scalar grid (conf-K=1.0), sorted by pooled RPS:\n")
        print(scalar_df.to_string(index=False))
        print("\nStep 2 — per-confederation K coordinate sweep, by pooled RPS:\n")
        print(conf_df.to_string(index=False))
        print(f"\nBest static config: longterm_years={best['longterm_years']} "
              f"ha={best['ha']} conf_k={best['conf_k']} (rps {best['rps']:.4f})")
        print("\nRe-validating default vs best with the rolling re-fit "
              "(the live --as-of protocol)...\n")
        for label, ck, ly, ha in (
                ("default (10y, HA=100, K=1.0)", None, None, None),
                ("best", best["conf_k"], best["longterm_years"], best["ha"])):
            per, pooled = elo_report(df, conf_k=ck, longterm_years=ly, ha=ha,
                                     rolling=True)
            print(f"[rolling] {label}: {pooled['points']:.0f} pts "
                  f"({pooled['pts_per_match']:.3f}/match), "
                  f"rps {pooled['rps']:.4f}, ll {pooled['log_loss']:.4f}")
        print("\nDefaults stay at the published eloratings rule (K=1.0) unless "
              "the rolling re-validation clearly beats them (config.py).")
        return
    if args.shrinkage:
        # Shrinkage grid (docs/known-limitations.md): sweep the shrinkage
        # parameters alone, other hyperparameters held at today's defaults.
        table = tune(df, rolling=args.rolling, gd_caps=(None,),
                     half_lives=(730,), friendly_weights=(1.0,),
                     shrinkages=[(None, 0.0)]
                                + [(m, e) for m in ("phantom", "pseudo")
                                   for e in (0.25, 0.5, 1.0, 2.0)])
    elif args.anchor:
        # Re-anchoring grid (docs/known-limitations.md): sweep the
        # confederation re-anchoring blend alone, other hyperparameters held
        # at today's defaults.
        table = tune(df, rolling=args.rolling, gd_caps=(None,),
                     half_lives=(730,), friendly_weights=(1.0,),
                     anchor_betas=(0.0, 0.25, 0.5, 0.75, 1.0))
    else:
        table = tune(df, rolling=args.rolling)
    print("\nGrid sorted by pooled RPS (lower is better):\n")
    print(table.to_string(index=False))
    b = table.iloc[0]
    print(f"\nBest by RPS: gd_cap={b.gd_cap} half_life={int(b.half_life)} "
          f"friendly_w={b.friendly_w} cross_conf_w={b.cross_conf_w} "
          f"shrinkage={b.shrink_mode}:{b.shrink_w} anchor={b.anchor_beta} "
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
        sp.add_argument("--engine", choices=("dc", "bayes", "elo"), default="dc",
                        help="rating model: 'dc' = MLE Dixon-Coles (default, "
                             "the regenerable production model), 'bayes' = "
                             "Stan Dixon-Coles with a hierarchical "
                             "confederation-offset prior (needs the bayes "
                             "extra; backtest static only), 'elo' = "
                             "Elo (eloratings.net rule + per-confederation K + "
                             "long-term Elo covariate) feeding a GAM-Poisson "
                             "Dixon-Coles")
        sp.add_argument("--bayes-dynamic", action="store_true",
                        default=BAYES_DYNAMIC,
                        help="under --engine bayes, evolve team "
                             "strengths as a random walk over time blocks "
                             "(replacing the decay weighting) and predict from "
                             "the most recent block (default: off)")
        sp.add_argument("--bayes-block", choices=("year", "halfyear", "quarter"),
                        default=BAYES_TIME_BLOCK,
                        help="random-walk block granularity for --bayes-dynamic "
                             "(default: %(default)s)")
        sp.add_argument("--bayes-sigma-conf", type=float,
                        default=BAYES_SIGMA_CONF_SCALE,
                        help="under --engine bayes, the "
                             "half-normal prior scale on the between-"
                             "confederation offset spread (default: %(default)s "
                             "= today's model; shrink toward 0 to pin the bloc "
                             "offsets near 0)")
        sp.add_argument("--bayes-propagate", action=argparse.BooleanOptionalAction,
                        default=BAYES_PROPAGATE,
                        help="under --engine bayes, build the score "
                             "matrix as the posterior mean of the per-draw "
                             "Dixon-Coles matrices (full posterior propagation) "
                             "instead of plugging in the posterior-mean ratings "
                             "(default: on; --no-bayes-propagate for plug-in)")
        sp.add_argument("--bayes-connect", action="store_true",
                        default=BAYES_CONNECT_SHRINK,
                        help="under --engine bayes, scale each team's "
                             "confederation offset by its bridge-match share so "
                             "weakly-connected teams (AFC/OFC minnows) anchor to "
                             "the global scale instead of their bloc's level "
                             "(default: off; static only)")
        sp.add_argument("--bayes-connect-ref", type=float,
                        default=BAYES_CONNECT_REF,
                        help="bridge share earning the full confederation offset "
                             "for --bayes-connect: c = min(1, share/ref) "
                             "(default: %(default)s)")
        sp.add_argument("--bayes-connect-mode",
                        choices=("offset", "deviation"),
                        default=BAYES_CONNECT_MODE,
                        help="what --bayes-connect scales: 'offset' (A, anchor "
                             "isolated teams toward the global scale; rejected) "
                             "or 'deviation' (B, partial-pool them toward the "
                             "bloc mean) (default: %(default)s)")
        sp.add_argument("--bayes-connect-by", choices=("bridge", "opp"),
                        default=BAYES_CONNECT_BY,
                        help="predictor for the --bayes-connect weight: 'bridge' "
                             "(bridge-match share; rejected) or 'opp' "
                             "(schedule difficulty = weighted mean opponent "
                             "rating, so soft-schedule teams shrink) "
                             "(default: %(default)s)")
        sp.add_argument("--bayes-connect-opp-ref", type=float,
                        default=BAYES_CONNECT_OPP_REF,
                        help="opp_rating earning the full weight for "
                             "--bayes-connect-by opp: c = min(1, opp/ref) "
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
        sp.add_argument("--pick-strategy", choices=("ev", "outcome"),
                        default=PICK_STRATEGY,
                        help="how a score matrix becomes a pick: 'ev' = "
                             "maximise expected points (regenerable default), "
                             "'outcome' = strategy C, most likely outcome then "
                             "most likely scoreline within it (+8%% Penka on "
                             "the backtest; default: %(default)s)")
        sp.add_argument("--anchor-beta", type=float, default=CONF_ANCHOR_BETA,
                        help="two-timescale confederation re-anchoring blend: "
                             "0 = off, 1 = adopt the long-window confederation "
                             "levels fully (default: %(default)s)")

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
    sp.add_argument("--out", help="save the full ranking CSV here (team, "
                    "confederation, attack/defence, rating, opponent difficulty "
                    f"and Elo when available); a bare filename goes under "
                    f"{RANKINGS_DIR}/")
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
                    help="sweep the cross-confederation shrinkage "
                         "parameters (SHRINKAGE_MODE x SHRINKAGE_WEIGHT) instead "
                         "of the standard hyperparameter grid")
    sp.add_argument("--anchor", action="store_true",
                    help="sweep the two-timescale confederation re-anchoring "
                         "blend (CONF_ANCHOR_BETA) instead of the standard "
                         "hyperparameter grid")
    sp.add_argument("--elo-engine", action="store_true",
                    help="coordinate-tune the Elo engine "
                         "(--engine elo): long-term window, home advantage and "
                         "the per-confederation K (ELO_CONF_K)")
    sp.set_defaults(func=cmd_tune)

    args = p.parse_args()
    if args.cmd == "update-data":
        download_results(args.data)
        return
    args.func(args)


if __name__ == "__main__":
    main()
