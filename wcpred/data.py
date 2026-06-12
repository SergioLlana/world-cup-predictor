"""Data acquisition and preparation."""
import glob
import os
import shutil
import ssl
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

from .config import (CROSS_CONF_WEIGHT, ELO_PATH, FRIENDLY_WEIGHT, GD_CAP,
                     HALF_LIFE_DAYS, MIN_MATCHES, ODDS_CUTOVER, ODDS_PATH,
                     ODDS_SNAPSHOT_DIR, RESULTS_PATH, RESULTS_URL,
                     SHRINKAGE_MODE, SHRINKAGE_WEIGHT, TRAIN_START, XG_ALPHA)
from .confederations import cross_conf_mask, infer_confederations

# Synthetic anchor opponent for SHRINKAGE_MODE="phantom". Never a real pick:
# fixtures only name real teams, but `ratings` must skip it (cli.cmd_ratings).
PHANTOM_TEAM = "__phantom__"


def _ssl_context():
    """Verifying TLS context, preferring certifi's CA bundle (macOS python.org
    builds often ship without a usable system bundle). Mirrors fetch_xg.py."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def download_results(path=RESULTS_PATH):
    """Download the latest international results dataset (updated daily)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    print(f"Downloading {RESULTS_URL} ...")
    req = urllib.request.Request(RESULTS_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30,
                                    context=_ssl_context()) as r, \
                open(path, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            raise SystemExit(
                "TLS certificate verification failed. Install CA certs "
                "(`pip install certifi`, or run the 'Install Certificates"
                ".command' bundled with python.org Python on macOS).")
        raise
    df = load_results(path)
    played = df.dropna(subset=["home_score"])
    print(f"Saved {path}: {len(df)} rows, latest played match "
          f"{played['date'].max().date()}")
    return df


def load_results(path=RESULTS_PATH):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_odds(path):
    """CSV columns: home_team, away_team, odds_1, odds_X, odds_2.
    Odds may be American (-235, +375) or decimal (1.45, 4.20); autodetected."""
    return pd.read_csv(path, dtype={"odds_1": str, "odds_X": str, "odds_2": str})


def resolve_odds_path(as_of, root=""):
    """Odds file in force at `as_of`'s generation time — the time-capsule
    counterpart of the training cutoff, so past runs regenerate without
    leaking later market moves.

    For an `as_of` of today or later this is the live odds.csv. For a past
    date it is the latest snapshot in ODDS_SNAPSHOT_DIR (odds_<ts>.csv,
    written by scripts/fetch_odds.py on every fetch) stamped no later than
    `as_of` + ODDS_CUTOVER, the latest fetch time that still precedes every
    kickoff of that day. Returns None when nothing qualifies. `root` prefixes
    the config-relative paths for callers not running from the project root
    (e.g. the webapp).
    """
    if str(as_of) >= str(date.today()):
        live = os.path.join(root, ODDS_PATH)
        return live if os.path.exists(live) else None
    cutoff = f"odds_{as_of}T{ODDS_CUTOVER.replace(':', '')}.csv"
    snap_dir = os.path.join(root, ODDS_SNAPSHOT_DIR)
    snaps = sorted(os.path.basename(p) for p in
                   glob.glob(os.path.join(snap_dir, "odds_*.csv")))
    eligible = [s for s in snaps if s <= cutoff]   # fixed-width timestamps
    return os.path.join(snap_dir, eligible[-1]) if eligible else None


def load_elo(as_of, path=ELO_PATH):
    """{team: elo} from the latest Elo snapshot dated <= `as_of` — the
    external-anchor counterpart of resolve_odds_path (model-robustness-plan
    Phase 3). elo.csv (date,team,elo; scripts/fetch_elo.py) holds year-end
    snapshots plus a fetch-day one; a snapshot dated D reflects matches
    through D, so taking the latest date <= as_of matches the training
    cutoff's information set (same same-day pre-kickoff discipline as
    ODDS_CUTOVER for a snapshot fetched on as_of itself). Returns {} when the
    file is missing or no snapshot qualifies."""
    if not os.path.exists(path):
        return {}
    e = pd.read_csv(path)
    e = e[e["date"] <= str(as_of)[:10]]
    if e.empty:
        return {}
    e = e[e["date"] == e["date"].max()]
    return dict(zip(e["team"], e["elo"].astype(float)))


def _shrinkage_rows(m, as_of, mode, weight):
    """Synthetic fractional 1-1 draws that shrink the weakly-identified
    cross-confederation rating offsets toward a common center (the
    pseudo-game / phantom-player augmentation of arXiv 2606.03805; see
    docs/model-robustness-plan.md Phase 1). Real matches are untouched.

    "phantom": every team draws 1-1 once vs PHANTOM_TEAM at weight `weight`.
    "pseudo": 1-1 draws between every cross-confederation team pair; each
    pair's weight is split so every team carries ≈`weight` total (exactly so
    when cross-pair counts are equal). Teams whose confederation cannot be
    inferred from the window get no pseudo rows.
    """
    teams = np.array(sorted(set(m["home_team"]) | set(m["away_team"])))
    if mode == "phantom":
        rows = pd.DataFrame({"home_team": teams, "away_team": PHANTOM_TEAM,
                             "w": weight})
    elif mode == "pseudo":
        confs = infer_confederations(m)
        teams = teams[[t in confs for t in teams]]
        conf = np.array([confs[t] for t in teams])
        ii, jj = np.triu_indices(len(teams), k=1)
        cross = conf[ii] != conf[jj]
        ii, jj = ii[cross], jj[cross]
        deg = np.zeros(len(teams))           # cross-bloc pairs per team
        np.add.at(deg, ii, 1)
        np.add.at(deg, jj, 1)
        rows = pd.DataFrame({"home_team": teams[ii], "away_team": teams[jj],
                             "w": weight * 0.5 * (1 / deg[ii] + 1 / deg[jj])})
    else:
        raise ValueError(f"unknown shrinkage mode: {mode!r}")
    rows["date"] = pd.Timestamp(as_of)
    rows["home_score"] = 1.0
    rows["away_score"] = 1.0
    rows["neutral"] = True
    rows["tournament"] = "__shrinkage__"
    return rows


def prepare_training(df, as_of, xg_path=None, xg_alpha=XG_ALPHA,
                     half_life=HALF_LIFE_DAYS, friendly_weight=FRIENDLY_WEIGHT,
                     train_start=TRAIN_START, gd_cap=GD_CAP,
                     cross_conf_weight=CROSS_CONF_WEIGHT,
                     shrinkage_mode=SHRINKAGE_MODE,
                     shrinkage_weight=SHRINKAGE_WEIGHT):
    """Played matches before `as_of`, with time/tournament weights.

    If xg_path is given (CSV: date, home_team, away_team, home_xg, away_xg),
    goals are blended with xG: g_eff = alpha*goals + (1-alpha)*xG.
    If gd_cap is set, the winner's goals are capped at loser + gd_cap so
    blowouts against minnows are not over-credited.
    cross_conf_weight > 1 upweights inter-confederation matches — the bridge
    games that anchor weakly-connected confederations to the global scale.
    shrinkage_mode (off by default) appends the synthetic draws of
    `_shrinkage_rows` after the MIN_MATCHES filter, so they neither rescue
    thin teams from the filter nor count as real appearances.
    """
    m = df.dropna(subset=["home_score", "away_score"]).copy()
    m = m[(m["date"] >= train_start) & (m["date"] < as_of)]
    if gd_cap is not None:
        hw = m["home_score"] - m["away_score"] > gd_cap
        aw = m["away_score"] - m["home_score"] > gd_cap
        m.loc[hw, "home_score"] = m.loc[hw, "away_score"] + gd_cap
        m.loc[aw, "away_score"] = m.loc[aw, "home_score"] + gd_cap
    age_days = (pd.Timestamp(as_of) - m["date"]).dt.days
    m["w"] = np.exp(-np.log(2) / half_life * age_days)
    m.loc[m["tournament"] == "Friendly", "w"] *= friendly_weight
    if cross_conf_weight != 1.0:
        confs = infer_confederations(m)
        m.loc[cross_conf_mask(m, confs), "w"] *= cross_conf_weight

    if xg_path:
        xg = pd.read_csv(xg_path, parse_dates=["date"])
        m = m.merge(xg, on=["date", "home_team", "away_team"], how="left")
        has = m["home_xg"].notna()
        for side in ("home", "away"):
            m.loc[has, f"{side}_score"] = (
                xg_alpha * m.loc[has, f"{side}_score"]
                + (1 - xg_alpha) * m.loc[has, f"{side}_xg"])
        print(f"xG blended into {has.sum()} of {len(m)} training matches")

    counts = pd.concat([m["home_team"], m["away_team"]]).value_counts()
    keep = set(counts[counts >= MIN_MATCHES].index)
    m = m[m["home_team"].isin(keep) & m["away_team"].isin(keep)]
    if shrinkage_mode:
        m = pd.concat([m, _shrinkage_rows(m, as_of, shrinkage_mode,
                                          shrinkage_weight)],
                      ignore_index=True)
    return m.reset_index(drop=True)


def upcoming_world_cup(df, from_date, to_date=None):
    """World Cup fixtures from `from_date` onward — the prediction targets of
    an `--as-of = from_date` run. Matches that by now have a real result are
    still included (the result itself is ignored): the as-of cutoff alone
    decides what is known, so past snapshots can be regenerated retroactively
    without leaking what happened on or after that date."""
    wc = df[(df["tournament"] == "FIFA World Cup")
            & (df["date"] >= from_date)]
    if to_date:
        wc = wc[wc["date"] <= to_date]
    return wc.sort_values("date").reset_index(drop=True)


def played_world_cup(df, year, as_of=None):
    """World Cup matches of the `year` edition that already have a result
    (before `as_of` when given, matching the training cutoff convention)."""
    wc = df[(df["tournament"] == "FIFA World Cup")
            & df["home_score"].notna()
            & (df["date"].dt.year == year)]
    if as_of:
        wc = wc[wc["date"] < as_of]
    return wc.sort_values("date").reset_index(drop=True)
