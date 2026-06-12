"""Local web app to browse wcpred predictions.

Serves the static frontend in `webapp/static/` plus a small JSON API over the
date-stamped CSVs that `scripts/generate_predictions.sh` writes under `data/`.
Run from the project root:

    uv run uvicorn webapp.server:app --port 8026

The API never caches: every request re-reads the CSVs, so a refresh (or a
manual `generate_predictions.sh` run) is picked up on the next page load.
"""
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

from wcpred.config import (GROUPS_DIR, INPUT_DIR, PREDICTIONS_DIR,
                           RESULTS_PATH, SIM_DIR, WC2026_KNOCKOUT_ROUNDS)
from wcpred.data import load_results, prepare_training, resolve_odds_path
from wcpred.model import DixonColes
from wcpred.predict import _norm_team, home_side, predict_match, wc2026_stage
from wcpred.tournament import OFFICIAL_GROUPS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT, "webapp", "static")
GENERATE_SH = os.path.join(ROOT, "scripts", "generate_predictions.sh")

# Approach label in the CSV filenames -> what the UI's odds toggle selects.
APPROACHES = ("odds", "history")

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

_FILE_RE = {
    "predictions": re.compile(r"picks_(odds|history)_(\d{4}-\d{2}-\d{2})\.csv$"),
    "groups": re.compile(r"groups_(odds|history)_(\d{4}-\d{2}-\d{2})\.csv$"),
    "simulations": re.compile(r"sim_(odds|history)_(\d{4}-\d{2}-\d{2})\.csv$"),
}
_DIRS = {"predictions": PREDICTIONS_DIR, "groups": GROUPS_DIR, "simulations": SIM_DIR}


def _snapshots(kind, approach):
    """Sorted [(date, path)] of the date-stamped CSVs for one approach."""
    rx = _FILE_RE[kind]
    out = []
    for path in glob.glob(os.path.join(ROOT, _DIRS[kind], "*.csv")):
        m = rx.search(os.path.basename(path))
        if m and m.group(1) == approach:
            out.append((m.group(2), path))
    return sorted(out)


def _check_approach(approach):
    if approach not in APPROACHES:
        raise HTTPException(400, f"approach must be one of {APPROACHES}")


def _read_snapshots(kind, approach):
    _check_approach(approach)
    snaps = []
    for date, path in _snapshots(kind, approach):
        df = pd.read_csv(path)
        snaps.append({"date": date, "rows": df.where(df.notna(), None).to_dict("records")})
    return {"snapshots": snaps}


# ---------------------------------------------------------------- endpoints

@app.get("/api/meta")
def meta():
    return {
        "teams": TEAMS,
        "groups": OFFICIAL_GROUPS,
        "snapshots": {
            kind: {ap: [d for d, _ in _snapshots(kind, ap)] for ap in APPROACHES}
            for kind in _DIRS
        },
    }


@app.get("/api/picks")
def picks(approach: str = "odds"):
    return _read_snapshots("predictions", approach)


@app.get("/api/groups")
def groups(approach: str = "odds"):
    return _read_snapshots("groups", approach)


@app.get("/api/sims")
def sims(approach: str = "odds"):
    return _read_snapshots("simulations", approach)


def _load_odds_history():
    """{(date, home, away): [o1, oX, o2]} from odds_history.csv (SofaScore)."""
    by_date = {}
    hist = os.path.join(ROOT, INPUT_DIR, "odds_history.csv")
    if os.path.exists(hist):
        df = pd.read_csv(hist)
        df = df[df["date"] >= WC_START]
        for r in df.itertuples():
            by_date[(r.date, _norm_team(r.home_team), _norm_team(r.away_team))] = \
                [r.odds_1, r.odds_X, r.odds_2]
    return by_date


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
    """Pair-indexed odds in force on `as_of`: the time-capsule snapshot for a
    past date, the live odds.csv otherwise — the same file the prediction
    pipeline would use for that day (wcpred.data.resolve_odds_path)."""
    path = resolve_odds_path(as_of, root=ROOT)
    if path is None:
        return {}
    return _odds_pairs(path, os.path.getmtime(path))


def _match_odds(by_pair, by_date, date, home, away):
    """1X2 odds for a fixture; tolerates the feed listing home/away swapped
    (three host fixtures do — see docs/known-limitations.md)."""
    home, away = _norm_team(home), _norm_team(away)
    for key, swap in (((date, home, away), False), ((date, away, home), True),
                      ((home, away), False), ((away, home), True)):
        odds = (by_date if len(key) == 3 else by_pair).get(key)
        if odds is not None:
            return ([odds[2], odds[1], odds[0]] if swap else odds), swap
    return None, False


@app.get("/api/matches")
def matches():
    df = pd.read_csv(os.path.join(ROOT, RESULTS_PATH))
    df = df[(df["tournament"] == "FIFA World Cup") & (df["date"] >= WC_START)]
    df = df.sort_values("date").reset_index(drop=True)

    # Group-stage matchday: nth fixture of that group (0-1 -> J1, 2-3 -> J2 ...).
    team_group = {t: g for g, ts in OFFICIAL_GROUPS.items() for t in ts}
    seen_in_group = {}
    by_date = _load_odds_history()

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
        odds, swapped = _match_odds(pairs_by_date[date], by_date,
                                    date, home, away)
        out.append({
            "date": date, "home": home, "away": away,
            "home_score": int(r.home_score) if played else None,
            "away_score": int(r.away_score) if played else None,
            "played": bool(played), "city": r.city,
            "group": g if same_group else None,
            "round_id": round_id, "round_name": round_name,
            "odds": odds, "odds_swapped": swapped,
        })
    return {"matches": out}


# ------------------------------------------------------------------- matrix

@lru_cache(maxsize=8)
def _model_for(as_of, results_mtime):
    """Dixon-Coles fitted on matches before `as_of` (no xG, like the daily
    pipeline). results_mtime is only part of the key so a data refresh
    invalidates the cache."""
    df = load_results(os.path.join(ROOT, RESULTS_PATH))
    return DixonColes().fit(prepare_training(df, as_of=as_of))


@app.get("/api/matrix")
def matrix(home: str, away: str, date: str, approach: str = "odds"):
    """Full score-probability matrix for one fixture, reproducing the pick
    shown in the calendar: model as of the snapshot in force on the match
    date, with market odds blended in when approach=odds."""
    _check_approach(approach)
    snaps = [d for d, _ in _snapshots("predictions", approach)]
    # No snapshot on/before the match date → fall back to the match date
    # itself, which is still leak-free (training uses matches strictly before
    # it); a later snapshot would train on results from after the match.
    as_of = max((d for d in snaps if d <= date), default=date)

    results_path = os.path.join(ROOT, RESULTS_PATH)
    model = _model_for(as_of, os.path.getmtime(results_path))

    df = pd.read_csv(results_path)
    row = df[(df["date"] == date) & (df["home_team"] == home) & (df["away_team"] == away)]
    venue_country = row.iloc[0]["country"] if len(row) else None
    side = home_side(home, away, venue_country)

    odds = None
    if approach == "odds":
        # Reproduce the pick: the odds file the pipeline used for `as_of`.
        odds, _ = _match_odds(_pairs_in_force(as_of), _load_odds_history(),
                              date, home, away)

    try:
        res = predict_match(model, home, away, side=side,
                            odds=tuple(odds) if odds else None,
                            stage=wc2026_stage(date))
    except KeyError:
        raise HTTPException(404, f"equipo sin datos de entrenamiento: {home} / {away}")
    return {
        "home": home, "away": away, "as_of": as_of, "side": side,
        "odds_used": bool(res["used_odds"]),
        "pick": f"{res['pick'][0]}-{res['pick'][1]}",
        "expected_points": round(res["expected_points"], 3),
        "p1": round(res["p1"], 4), "px": round(res["px"], 4), "p2": round(res["p2"], 4),
        "matrix": [[round(float(p), 5) for p in r] for r in res["P"]],
    }


# ------------------------------------------------------------------ refresh

_refresh_lock = threading.Lock()
_refresh = {"running": False, "returncode": None, "log": deque(maxlen=400)}


def _run_refresh(args):
    proc = subprocess.Popen(
        [GENERATE_SH] + args, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for line in proc.stdout:
        _refresh["log"].append(line.rstrip("\n"))
    proc.wait()
    _refresh["returncode"] = proc.returncode
    _refresh["running"] = False


@app.post("/api/refresh")
def refresh(payload: dict):
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
    # one run per approach so the odds toggle has fresh data on both sides
    approaches = payload.get("approaches") or ["odds", "history"]

    def runner():
        for i, ap in enumerate(approaches):
            ap_args = list(args) if i == 0 else [a for a in args if a != "--refresh"]
            _refresh["log"].append(f">>> generate_predictions.sh --approach {ap}")
            _run_refresh(ap_args + ["--approach", ap])
            if _refresh["returncode"] not in (0, None) or ap == approaches[-1]:
                return
            _refresh["running"] = True

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

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
