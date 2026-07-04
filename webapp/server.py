"""Local web app to browse wcpred predictions.

Serves the static frontend in `webapp/static/` plus a small JSON API over the
date-stamped CSVs that `scripts/generate_predictions.sh` writes under `data/`.
Run from the project root:

    uv run uvicorn webapp.server:app --port 8026

The API never caches: every request re-reads the CSVs, so a refresh (or a
manual `generate_predictions.sh` run) is picked up on the next page load.
"""
import datetime
import glob
import os
import re
import subprocess
import threading
from collections import deque

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from functools import lru_cache

from wcpred.config import (GROUPS_DIR, INPUT_DIR, MATRICES_DIR, MAX_GOALS,
                           PREDICTIONS_DIR, RANKINGS_DIR, RESULTS_PATH,
                           SIM_DIR, WC2026_KNOCKOUT_ROUNDS)
from wcpred.confederations import infer_confederations
from wcpred.data import load_results, prepare_training, resolve_odds_path
from wcpred.model import DixonColes
from wcpred.predict import _norm_team, home_side, predict_match, wc2026_stage
from wcpred.tournament import OFFICIAL_GROUPS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT, "webapp", "static")
GENERATE_SH = os.path.join(ROOT, "scripts", "generate_predictions.sh")
GENERATE_RANKINGS_SH = os.path.join(ROOT, "scripts", "generate_rankings.sh")

# Public deployment mode. Set WCPRED_PUBLIC=1 on the hosted instance to lock it
# down: no data refresh, no Connectivity tab. Locally the var is unset, so the
# full app runs. The frontend reads `meta.public` to hide the matching UI.
PUBLIC = bool(os.getenv("WCPRED_PUBLIC"))

# Approach label in the CSV filenames -> what the UI's odds toggle selects.
APPROACHES = ("odds", "history")
# Engine label in the CSV filenames -> what the UI's engine picker selects.
# dc is the production model; elo/bayes are the alternative engines (see
# CLAUDE.md). generate_predictions.sh stamps every engine into the filename.
# bayes is served on the public deploy too, even though CmdStan isn't installed
# there: every tab reads committed CSVs, and /api/matrix reads the precomputed
# data/matrices/ CSVs (`wcpred matrices`); the live-fit fallbacks answer 503.
ENGINES = ("dc", "elo", "bayes")
DEFAULT_ENGINE = "dc"

# Scoreline pick strategy -> what the UI's strategy toggle selects. Both live in
# every predictions CSV as separate columns (pick/expected_points for "ev",
# pick_outcome/expected_points_outcome for "outcome"); the toggle just picks the
# column to show — see predict.predict_fixtures and docs/pick-strategy.md.
STRATEGIES = ("ev", "outcome")
DEFAULT_STRATEGY = "outcome"

# name in the martj42 dataset -> flag file (webapp/static/flags/) + Spanish name
TEAMS = {
    "Mexico":                 {"code": "mx",     "es": "México"},
    "South Africa":           {"code": "za",     "es": "Sudáfrica"},
    "South Korea":            {"code": "kr",     "es": "Corea del Sur"},
    "Czech Republic":         {"code": "cz",     "es": "Chequia"},
    "Canada":                 {"code": "ca",     "es": "Canadá"},
    "Bosnia and Herzegovina": {"code": "ba",     "es": "Bosnia y Herzegovina"},
    "Qatar":                  {"code": "qa",     "es": "Catar"},
    "Switzerland":            {"code": "ch",     "es": "Suiza"},
    "Brazil":                 {"code": "br",     "es": "Brasil"},
    "Morocco":                {"code": "ma",     "es": "Marruecos"},
    "Haiti":                  {"code": "ht",     "es": "Haití"},
    "Scotland":               {"code": "gb-sct", "es": "Escocia"},
    "United States":          {"code": "us",     "es": "Estados Unidos"},
    "Paraguay":               {"code": "py",     "es": "Paraguay"},
    "Australia":              {"code": "au",     "es": "Australia"},
    "Turkey":                 {"code": "tr",     "es": "Turquía"},
    "Germany":                {"code": "de",     "es": "Alemania"},
    "Curaçao":                {"code": "cw",     "es": "Curazao"},
    "Ivory Coast":            {"code": "ci",     "es": "Costa de Marfil"},
    "Ecuador":                {"code": "ec",     "es": "Ecuador"},
    "Netherlands":            {"code": "nl",     "es": "Países Bajos"},
    "Japan":                  {"code": "jp",     "es": "Japón"},
    "Sweden":                 {"code": "se",     "es": "Suecia"},
    "Tunisia":                {"code": "tn",     "es": "Túnez"},
    "Belgium":                {"code": "be",     "es": "Bélgica"},
    "Egypt":                  {"code": "eg",     "es": "Egipto"},
    "Iran":                   {"code": "ir",     "es": "Irán"},
    "New Zealand":            {"code": "nz",     "es": "Nueva Zelanda"},
    "Spain":                  {"code": "es",     "es": "España"},
    "Cape Verde":             {"code": "cv",     "es": "Cabo Verde"},
    "Saudi Arabia":           {"code": "sa",     "es": "Arabia Saudí"},
    "Uruguay":                {"code": "uy",     "es": "Uruguay"},
    "France":                 {"code": "fr",     "es": "Francia"},
    "Senegal":                {"code": "sn",     "es": "Senegal"},
    "Iraq":                   {"code": "iq",     "es": "Irak"},
    "Norway":                 {"code": "no",     "es": "Noruega"},
    "Argentina":              {"code": "ar",     "es": "Argentina"},
    "Algeria":                {"code": "dz",     "es": "Argelia"},
    "Austria":                {"code": "at",     "es": "Austria"},
    "Jordan":                 {"code": "jo",     "es": "Jordania"},
    "Portugal":               {"code": "pt",     "es": "Portugal"},
    "DR Congo":               {"code": "cd",     "es": "RD Congo"},
    "Uzbekistan":             {"code": "uz",     "es": "Uzbekistán"},
    "Colombia":               {"code": "co",     "es": "Colombia"},
    "England":                {"code": "gb-eng", "es": "Inglaterra"},
    "Croatia":                {"code": "hr",     "es": "Croacia"},
    "Ghana":                  {"code": "gh",     "es": "Ghana"},
    "Panama":                 {"code": "pa",     "es": "Panamá"},
}

# Knockout rounds by date range, from the shared calendar in wcpred.config —
# the same boundaries predict.wc2026_stage maps to Penka tiers. Group-stage
# matchdays are derived per group from the fixture order instead, which is
# robust to schedule quirks.
ROUND_NAMES = {
    "r32": "Dieciseisavos de final",
    "r16": "Octavos de final",
    "qf":  "Cuartos de final",
    "sf":  "Semifinales",
    "p3":  "Tercer puesto",
    "f":   "Final",
}
KNOCKOUT_ROUNDS = [(lo, hi, rid, ROUND_NAMES[rid])
                   for lo, hi, rid in WC2026_KNOCKOUT_ROUNDS]
KNOCKOUT_START = KNOCKOUT_ROUNDS[0][0]

WC_START = "2026-06-01"

app = FastAPI(title="wcpred web")

# ---------------------------------------------------------------- snapshots

# generate_predictions.sh labels every engine into the filename, so each CSV
# carries an _<engine> segment (_dc/_elo/_bayes); the UI's engine picker selects
# which one the dashboard reads.
_FILE_RE = {
    "predictions": re.compile(r"picks_(odds|history)_(dc|elo|bayes)_(\d{4}-\d{2}-\d{2})\.csv$"),
    "groups": re.compile(r"groups_(odds|history)_(dc|elo|bayes)_(\d{4}-\d{2}-\d{2})\.csv$"),
    "simulations": re.compile(r"sim_(odds|history)_(dc|elo|bayes)_(\d{4}-\d{2}-\d{2})\.csv$"),
}
_DIRS = {"predictions": PREDICTIONS_DIR, "groups": GROUPS_DIR, "simulations": SIM_DIR}


def _snapshots(kind, approach, engine=DEFAULT_ENGINE):
    """Sorted [(date, path)] of the date-stamped CSVs for one approach+engine."""
    rx = _FILE_RE[kind]
    out = []
    for path in glob.glob(os.path.join(ROOT, _DIRS[kind], "*.csv")):
        m = rx.search(os.path.basename(path))
        if m and m.group(1) == approach and m.group(2) == engine:
            out.append((m.group(3), path))
    return sorted(out)


def _check_approach(approach):
    if approach not in APPROACHES:
        raise HTTPException(400, f"approach must be one of {APPROACHES}")


def _check_engine(engine):
    if engine not in ENGINES:
        raise HTTPException(400, f"engine must be one of {ENGINES}")


def _check_strategy(strategy):
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"strategy must be one of {STRATEGIES}")


def _records(df):
    """NaN-safe records: missing cells become None (JSON null). A plain
    `df.where(df.notna(), None)` leaves NaN in object columns, which Starlette's
    strict JSON encoder (allow_nan=False) then rejects with a 500 — so cast to
    object first."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _read_snapshots(kind, approach, engine):
    _check_approach(approach)
    _check_engine(engine)
    snaps = []
    for date, path in _snapshots(kind, approach, engine):
        snaps.append({"date": date, "rows": _records(pd.read_csv(path))})
    return {"snapshots": snaps}


# ---------------------------------------------------------------- endpoints

@app.get("/api/meta")
def meta():
    return {
        "teams": TEAMS,
        "groups": OFFICIAL_GROUPS,
        "engines": list(ENGINES),
        "default_engine": DEFAULT_ENGINE,
        "strategies": list(STRATEGIES),
        "default_strategy": DEFAULT_STRATEGY,
        "public": PUBLIC,
        "snapshots": {
            kind: {ap: {eng: [d for d, _ in _snapshots(kind, ap, eng)]
                        for eng in ENGINES}
                   for ap in APPROACHES}
            for kind in _DIRS
        },
    }


@app.get("/api/picks")
def picks(approach: str = "odds", engine: str = DEFAULT_ENGINE):
    return _read_snapshots("predictions", approach, engine)


@app.get("/api/groups")
def groups(approach: str = "odds", engine: str = DEFAULT_ENGINE):
    return _read_snapshots("groups", approach, engine)


@app.get("/api/sims")
def sims(approach: str = "odds", engine: str = DEFAULT_ENGINE):
    return _read_snapshots("simulations", approach, engine)


@lru_cache(maxsize=64)
def _odds_pairs(path, mtime):
    """{(home, away): [o1, oX, o2]} from one odds CSV. Snapshots are
    immutable; mtime keys the cache so a refreshed live odds.csv reloads."""
    out = {}
    for r in pd.read_csv(path).itertuples():
        out[(_norm_team(r.home_team), _norm_team(r.away_team))] = \
            [r.odds_1, r.odds_X, r.odds_2]
    return out


def _pairs_in_force(as_of):
    """Pair-indexed odds in force on `as_of`: the frozen-in-time snapshot for a
    past date, the live odds.csv otherwise — the same file the prediction
    pipeline would use for that day (wcpred.data.resolve_odds_path)."""
    path = resolve_odds_path(as_of, root=ROOT)
    if path is None:
        return {}
    return _odds_pairs(path, os.path.getmtime(path))


def _match_odds(by_pair, home, away):
    """1X2 odds for a fixture from the in-force odds snapshot; tolerates the
    feed listing home/away swapped (three host fixtures do — see
    docs/known-limitations.md)."""
    home, away = _norm_team(home), _norm_team(away)
    for key, swap in (((home, away), False), ((away, home), True)):
        odds = by_pair.get(key)
        if odds is not None:
            return ([odds[2], odds[1], odds[0]] if swap else odds), swap
    return None, False


@app.get("/api/matches")
def matches():
    # load_results rewrites home_score/away_score to the 90' result (what the
    # picks are scored on) and keeps the real outcome in *_ft/shootout_winner.
    df = load_results(os.path.join(ROOT, RESULTS_PATH))
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df[(df["tournament"] == "FIFA World Cup") & (df["date"] >= WC_START)]
    df = df.sort_values("date").reset_index(drop=True)

    # Group-stage matchday: nth fixture of that group (0-1 -> J1, 2-3 -> J2 ...).
    team_group = {t: g for g, ts in OFFICIAL_GROUPS.items() for t in ts}
    seen_in_group = {}

    out = []
    pairs_by_date = {}   # resolve the in-force odds file once per match day
    for r in df.itertuples():
        home, away, date = r.home_team, r.away_team, r.date
        played = pd.notna(r.home_score) and pd.notna(r.away_score)
        g = team_group.get(home)
        same_group = g is not None and team_group.get(away) == g
        if same_group and date < KNOCKOUT_START:
            n = seen_in_group[g] = seen_in_group.get(g, 0) + 1
            round_id, round_name = f"j{(n + 1) // 2}", f"Fase de grupos · Jornada {(n + 1) // 2}"
        else:
            round_id, round_name = "ko", "Eliminatorias"
            for lo, hi, rid, name in KNOCKOUT_ROUNDS:
                if lo <= date <= hi:
                    round_id, round_name = rid, name
                    break
        # Odds in force on the match day (snapshot for played days, live for
        # upcoming), so past matches keep the prices their pick was based on.
        if date not in pairs_by_date:
            pairs_by_date[date] = _pairs_in_force(date)
        odds, swapped = _match_odds(pairs_by_date[date], home, away)
        out.append({
            "date": date, "home": home, "away": away,
            # displayed result: the real one (after extra time) …
            "home_score": int(r.home_score_ft) if played else None,
            "away_score": int(r.away_score_ft) if played else None,
            # … while picks are judged on the 90' score (Penka convention)
            "home_score_90": int(r.home_score) if played else None,
            "away_score_90": int(r.away_score) if played else None,
            "shootout_winner": (r.shootout_winner
                                if isinstance(r.shootout_winner, str) else None),
            "played": bool(played), "city": r.city,
            "group": g if same_group else None,
            "round_id": round_id, "round_name": round_name,
            "odds": odds, "odds_swapped": swapped,
        })
    return {"matches": out}


# ------------------------------------------------------------------- matrix

@lru_cache(maxsize=24)
def _model_for(as_of, results_mtime, engine=DEFAULT_ENGINE):
    """Model fitted on matches before `as_of` (no xG, like the daily pipeline),
    using the requested engine (dc/elo/bayes). results_mtime is only part of the
    key so a data refresh invalidates the cache. bayes loads its posterior from
    data/models/ when the daily pipeline already sampled it (bit-identical,
    <1 s); only a snapshot date no fit ever ran for samples MCMC here."""
    df = load_results(os.path.join(ROOT, RESULTS_PATH))
    train = prepare_training(df, as_of=as_of)
    if engine == "elo":
        from wcpred.model_elo import EloDixonColes
        return EloDixonColes().fit(train, df=df, as_of=as_of)
    if engine == "bayes":
        from wcpred.model_bayes import BayesianDixonColes
        return BayesianDixonColes().fit(train)
    return DixonColes().fit(train)


@lru_cache(maxsize=48)
def _matrices_rows(path, mtime):
    """{(date, home, away): row} from one precomputed matrices CSV
    (`wcpred matrices`, data/matrices/). mtime keys the cache like the other
    CSV caches."""
    return {(r.date, r.home, r.away): r
            for r in pd.read_csv(path).itertuples()}


def _precomputed_matrix(approach, engine, as_of, date, home, away, strategy):
    """/api/matrix response from the precomputed CSV for `as_of`, or None.
    The CSV stores full float precision, so rounding here returns exactly what
    the live path would — the deploy without the engine installed (bayes on
    Render) serves identical responses."""
    path = os.path.join(ROOT, MATRICES_DIR,
                        f"matrices_{approach}_{engine}_{as_of}.csv")
    if not os.path.exists(path):
        return None
    r = _matrices_rows(path, os.path.getmtime(path)).get((date, home, away))
    if r is None:
        return None
    pick, ep = ((r.pick_outcome, r.expected_points_outcome)
                if strategy == "outcome" else (r.pick, r.expected_points))
    return {
        "home": home, "away": away, "as_of": as_of,
        "side": r.side if isinstance(r.side, str) else None,
        "engine": engine, "strategy": strategy,
        "odds_used": bool(r.odds_used),
        "pick": pick,
        "expected_points": round(float(ep), 3),
        "p1": round(float(r.p1), 4), "px": round(float(r.px), 4),
        "p2": round(float(r.p2), 4),
        "matrix": [[round(float(getattr(r, f"p_{h}_{a}")), 5)
                    for a in range(MAX_GOALS + 1)]
                   for h in range(MAX_GOALS + 1)],
    }


@app.get("/api/matrix")
def matrix(home: str, away: str, date: str, approach: str = "odds",
           engine: str = DEFAULT_ENGINE, strategy: str = DEFAULT_STRATEGY):
    """Full score-probability matrix for one fixture, reproducing the pick
    shown in the calendar: model as of the snapshot in force on the match
    date, with market odds blended in when approach=odds. `strategy` (ev/
    outcome) selects which scoreline pick to highlight. Served from the
    precomputed data/matrices/ CSV when one exists; otherwise fitted live."""
    _check_approach(approach)
    _check_engine(engine)
    _check_strategy(strategy)
    snaps = [d for d, _ in _snapshots("predictions", approach, engine)]
    # No snapshot on/before the match date → fall back to the match date
    # itself, which is still leak-free (training uses matches strictly before
    # it); a later snapshot would train on results from after the match.
    as_of = max((d for d in snaps if d <= date), default=date)

    pre = _precomputed_matrix(approach, engine, as_of, date, home, away,
                              strategy)
    if pre is not None:
        return pre

    results_path = os.path.join(ROOT, RESULTS_PATH)
    try:
        model = _model_for(as_of, os.path.getmtime(results_path), engine)
    except ImportError:
        # bayes without CmdStan (the public deploy) and no precomputed CSV for
        # this as_of: regenerate data/matrices/ locally and push.
        raise HTTPException(503, f"matriz no precalculada para {as_of} y el "
                            f"motor {engine} no puede ajustarse en este deploy")

    df = pd.read_csv(results_path)
    row = df[(df["date"] == date) & (df["home_team"] == home) & (df["away_team"] == away)]
    venue_country = row.iloc[0]["country"] if len(row) else None
    side = home_side(home, away, venue_country)

    odds = None
    if approach == "odds":
        # Reproduce the pick: the odds file the pipeline used for `as_of`.
        odds, _ = _match_odds(_pairs_in_force(as_of), home, away)

    try:
        res = predict_match(model, home, away, side=side,
                            odds=tuple(odds) if odds else None,
                            stage=wc2026_stage(date), pick_strategy=strategy)
    except KeyError:
        raise HTTPException(404, f"equipo sin datos de entrenamiento: {home} / {away}")
    return {
        "home": home, "away": away, "as_of": as_of, "side": side,
        "engine": engine, "strategy": strategy,
        "odds_used": bool(res["used_odds"]),
        "pick": f"{res['pick'][0]}-{res['pick'][1]}",
        "expected_points": round(res["expected_points"], 3),
        "p1": round(res["p1"], 4), "px": round(res["px"], 4), "p2": round(res["p2"], 4),
        "matrix": [[round(float(p), 5) for p in r] for r in res["P"]],
    }


# ------------------------------------------------------------- connectivity

CONF_ORDER = ["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"]


@lru_cache(maxsize=4)
def _connectivity(as_of, results_mtime):
    """Inter-confederation connectivity of the training set.

    Bridge matches (between confederations) are the only games anchoring the
    confederations to a common rating scale; pools with few bridges shift —
    the schedule-inflation caveat in docs/known-limitations.md. Returns the
    conf x conf matrix of training weight (time decay included, the same `w`
    the model fits on) plus per-WC-team bridge stats. results_mtime is only
    part of the key so a data refresh invalidates the cache.

    Pinned to the dc engine regardless of DEFAULT_ENGINE: the tab reproduces
    the dc-based analysis in docs/connectivity.md, and the elo engine's
    atk/dfn are display-only quantities (docs/next-steps.md §5)."""
    df = load_results(os.path.join(ROOT, RESULTS_PATH))
    m = prepare_training(df, as_of=as_of)
    confs = infer_confederations(m)
    model = _model_for(as_of, results_mtime, engine="dc")
    overall = {t: float(model.atk[i] - model.dfn[i]) for t, i in model.idx.items()}

    idx = {c: i for i, c in enumerate(CONF_ORDER)}
    n = len(CONF_ORDER)
    weight = [[0.0] * n for _ in range(n)]
    count = [[0] * n for _ in range(n)]

    wc_teams = {t for ts in OFFICIAL_GROUPS.values() for t in ts}
    stats = {t: {"w": 0.0, "bridge_w": 0.0, "opp_rating_w": 0.0, "n": 0,
                 "by_conf": dict.fromkeys(CONF_ORDER, 0.0)} for t in wc_teams}

    for r in m.itertuples():
        hc, ac = confs.get(r.home_team), confs.get(r.away_team)
        w = float(r.w)
        if hc in idx and ac in idx:
            i, j = idx[hc], idx[ac]
            weight[i][j] += w
            count[i][j] += 1
            if i != j:
                weight[j][i] += w
                count[j][i] += 1
        for team, opp, oc in ((r.home_team, r.away_team, ac),
                              (r.away_team, r.home_team, hc)):
            s = stats.get(team)
            if s is None:
                continue
            s["w"] += w
            s["n"] += 1
            # opp is always in the model: prepare_training drops matches of
            # sub-MIN_MATCHES teams before the fit, and the fit uses this
            # same frame
            s["opp_rating_w"] += w * overall[opp]
            tc = confs.get(team)
            if oc in idx:
                s["by_conf"][oc] += w
                if tc is not None and oc != tc:
                    s["bridge_w"] += w

    teams = []
    for t, s in sorted(stats.items()):
        if not s["w"]:
            continue
        teams.append({
            "team": t, "conf": confs.get(t), "matches": s["n"],
            "rating": round(overall[t], 3),
            "bridge_share": round(s["bridge_w"] / s["w"], 4),
            "opp_rating": round(s["opp_rating_w"] / s["w"], 3),
            # shares can sum to <1: opponents with no continental appearance
            # in the window have no confederation
            "by_conf": {c: round(v / s["w"], 4) for c, v in s["by_conf"].items()},
        })
    teams.sort(key=lambda x: -x["rating"])
    return {
        "as_of": as_of,
        "confederations": CONF_ORDER,
        "matrix_weight": [[round(v, 1) for v in row] for row in weight],
        "matrix_count": count,
        "teams": teams,
    }


@app.get("/api/connectivity")
def connectivity():
    if PUBLIC:
        raise HTTPException(404, "no disponible en la versión pública")
    as_of = datetime.date.today().isoformat()
    return _connectivity(as_of, os.path.getmtime(os.path.join(ROOT, RESULTS_PATH)))


# --------------------------------------------------------------- rankings

@lru_cache(maxsize=12)
def _rankings(as_of, results_mtime, engine):
    """Per-team strength ratings of the requested engine, for the 48 WC2026
    teams. Returns the model's attack/defence coefficients and overall rating
    (atk - dfn), each team's confederation, the weighted mean opponent rating
    (average difficulty of its training schedule) and, for the Elo engine, its
    current Elo. results_mtime is only part of the key so a data refresh
    invalidates the cache."""
    df = load_results(os.path.join(ROOT, RESULTS_PATH))
    m = prepare_training(df, as_of=as_of)
    confs = infer_confederations(m)
    model = _model_for(as_of, results_mtime, engine)
    overall = {t: float(model.atk[i] - model.dfn[i]) for t, i in model.idx.items()}

    # weighted mean opponent rating per team (same `w` the model fits on)
    opp_w = {}
    w_tot = {}
    for r in m.itertuples():
        w = float(r.w)
        for team, opp in ((r.home_team, r.away_team), (r.away_team, r.home_team)):
            if team in model.idx and opp in model.idx:
                opp_w[team] = opp_w.get(team, 0.0) + w * overall[opp]
                w_tot[team] = w_tot.get(team, 0.0) + w

    wc_teams = {t for ts in OFFICIAL_GROUPS.values() for t in ts}
    elo_cur = getattr(model, "elo_cur", None)
    teams = []
    for t in wc_teams:
        i = model.idx.get(t)
        if i is None:
            continue
        entry = {
            "team": t, "conf": confs.get(t),
            "atk": round(float(model.atk[i]), 3),
            "dfn": round(float(model.dfn[i]), 3),
            "rating": round(overall[t], 3),
            "opp_rating": round(opp_w[t] / w_tot[t], 3) if w_tot.get(t) else None,
        }
        if elo_cur is not None:
            entry["elo"] = round(float(elo_cur[i]), 1)
        teams.append(entry)
    # Elo engine: rank by the raw Elo; coefficient engines: by overall rating.
    teams.sort(key=lambda x: -(x.get("elo") if elo_cur is not None else x["rating"]))
    return {"as_of": as_of, "engine": engine, "has_elo": elo_cur is not None,
            "teams": teams}


@app.get("/api/rankings")
def rankings(engine: str = DEFAULT_ENGINE):
    _check_engine(engine)
    as_of = datetime.date.today().isoformat()
    try:
        return _rankings(as_of,
                         os.path.getmtime(os.path.join(ROOT, RESULTS_PATH)),
                         engine)
    except ImportError:
        # Live-fit fallback for a deploy that can't fit this engine (bayes
        # without CmdStan). The frontend only calls this when there are no
        # ratings_<engine>_*.csv snapshots, which the daily pipeline commits.
        raise HTTPException(503, f"el motor {engine} no puede ajustarse en "
                            "este deploy; genera los rankings con "
                            "scripts/generate_rankings.sh")


# Date-stamped ranking snapshots written by scripts/generate_rankings.sh.
# Rankings don't depend on the odds (the `approach`), so the filename has no
# approach segment — just ratings_<engine>_<date>.csv (a --label run adds an
# extra segment that this regex deliberately skips, like the picks regex).
_RANK_RE = re.compile(r"ratings_(dc|elo|bayes)_(\d{4}-\d{2}-\d{2})\.csv$")


def _ranking_snapshots(engine):
    """Sorted [(date, path)] of the ranking CSVs for one engine."""
    out = []
    for path in glob.glob(os.path.join(ROOT, RANKINGS_DIR, "*.csv")):
        m = _RANK_RE.search(os.path.basename(path))
        if m and m.group(1) == engine:
            out.append((m.group(2), path))
    return sorted(out)


@app.get("/api/rankings/history")
def rankings_history(engine: str = DEFAULT_ENGINE):
    """Every date-stamped ranking snapshot for one engine, so the Rankings tab
    can show the latest table and chart how the ratings evolve. Empty when
    generate_rankings.sh has not run yet — the UI then falls back to the live
    /api/rankings fit."""
    _check_engine(engine)
    snaps = []
    for date, path in _ranking_snapshots(engine):
        snaps.append({"date": date, "rows": _records(pd.read_csv(path))})
    return {"engine": engine, "snapshots": snaps}


# ------------------------------------------------------------------ refresh

_refresh_lock = threading.Lock()
_refresh = {"running": False, "returncode": None, "log": deque(maxlen=400)}


def _run_proc(cmd):
    """Stream one subprocess's output into the refresh log and record its exit
    code. Does NOT flip `running` — the runner owns that, so a multi-step
    refresh isn't reported as finished between steps."""
    proc = subprocess.Popen(
        cmd, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for line in proc.stdout:
        _refresh["log"].append(line.rstrip("\n"))
    proc.wait()
    _refresh["returncode"] = proc.returncode


@app.post("/api/refresh")
def refresh(payload: dict = None):
    # payload optional so the public lock answers 403 even for a body-less probe
    # (FastAPI validates a required body before the handler runs → 422 instead).
    if PUBLIC:
        raise HTTPException(403, "deshabilitado en la versión pública")
    payload = payload or {}
    with _refresh_lock:
        if _refresh["running"]:
            raise HTTPException(409, "ya hay un refresco en marcha")
        _refresh.update(running=True, returncode=None)
        _refresh["log"].clear()
    args = []
    if payload.get("refresh_inputs", True):
        args.append("--refresh")
    sims = payload.get("sims")
    if sims:
        args += ["--sims", str(int(sims))]
    # engines to (re)generate so the engine picker has fresh data on each side
    engines = [e for e in (payload.get("engines") or [DEFAULT_ENGINE])
               if e in ENGINES] or [DEFAULT_ENGINE]
    args += ["--engines", ",".join(engines)]
    # one run per approach so the odds toggle has fresh data on both sides
    approaches = payload.get("approaches") or ["odds", "history"]

    def runner():
        try:
            for i, ap in enumerate(approaches):
                ap_args = list(args) if i == 0 else [a for a in args if a != "--refresh"]
                _refresh["log"].append(f">>> generate_predictions.sh --approach {ap}")
                _run_proc([GENERATE_SH] + ap_args + ["--approach", ap])
                if _refresh["returncode"] not in (0, None):
                    return
            # Rankings are approach-independent: one run for the chosen engines
            # (data already refreshed above, so no --refresh here).
            _refresh["log"].append(">>> generate_rankings.sh")
            _run_proc([GENERATE_RANKINGS_SH, "--engines", ",".join(engines)])
        finally:
            _refresh["running"] = False

    threading.Thread(target=runner, daemon=True).start()
    return {"started": True}


@app.get("/api/refresh/status")
def refresh_status():
    return {
        "running": _refresh["running"],
        "returncode": _refresh["returncode"],
        "log": list(_refresh["log"]),
    }


# ------------------------------------------------------------------- static

class NoCacheStaticFiles(StaticFiles):
    """Serve the frontend with `Cache-Control: no-cache` so browsers revalidate
    (via ETag) before reusing app.js/i18n.js/style.css. They still get a cheap
    304 when nothing changed, but never serve a stale bundle after a deploy —
    which otherwise left users on old strings (e.g. "Cerca", "Clasificación")."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"),
                        headers={"Cache-Control": "no-cache"})


app.mount("/", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
