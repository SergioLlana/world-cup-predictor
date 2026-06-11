"""Data acquisition and preparation."""
import os
import shutil
import ssl
import urllib.request

import numpy as np
import pandas as pd

from .config import (FRIENDLY_WEIGHT, GD_CAP, HALF_LIFE_DAYS, MIN_MATCHES,
                     RESULTS_PATH, RESULTS_URL, TRAIN_START, XG_ALPHA)


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


def prepare_training(df, as_of, xg_path=None, xg_alpha=XG_ALPHA,
                     half_life=HALF_LIFE_DAYS, friendly_weight=FRIENDLY_WEIGHT,
                     train_start=TRAIN_START, gd_cap=GD_CAP):
    """Played matches before `as_of`, with time/tournament weights.

    If xg_path is given (CSV: date, home_team, away_team, home_xg, away_xg),
    goals are blended with xG: g_eff = alpha*goals + (1-alpha)*xG.
    If gd_cap is set, the winner's goals are capped at loser + gd_cap so
    blowouts against minnows are not over-credited.
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
    return m.reset_index(drop=True)


def upcoming_world_cup(df, from_date, to_date=None):
    """World Cup fixtures not yet played, from `from_date` onward."""
    wc = df[(df["tournament"] == "FIFA World Cup")
            & (df["home_score"].isna())
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
