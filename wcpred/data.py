"""Data acquisition and preparation."""
import glob
import os
import shutil
import ssl
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

from .config import (CROSS_CONF_WEIGHT, FRIENDLY_WEIGHT, GD_CAP,
                     GOALSCORERS_PATH, GOALSCORERS_URL, HALF_LIFE_DAYS,
                     MIN_MATCHES, ODDS_CUTOVER, ODDS_PATH, ODDS_SNAPSHOT_DIR,
                     RESULTS_PATH, RESULTS_URL, SHOOTOUTS_PATH, SHOOTOUTS_URL,
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


def _download(url, path):
    print(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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


def download_results(path=RESULTS_PATH):
    """Download the latest international results dataset (updated daily),
    plus the sibling goalscorers/shootouts files that let `load_results`
    rebuild 90-minute scores for matches that went to extra time."""
    base = os.path.dirname(path) or "."
    os.makedirs(base, exist_ok=True)
    _download(RESULTS_URL, path)
    _download(GOALSCORERS_URL, os.path.join(base, os.path.basename(GOALSCORERS_PATH)))
    _download(SHOOTOUTS_URL, os.path.join(base, os.path.basename(SHOOTOUTS_PATH)))
    df = load_results(path)
    played = df.dropna(subset=["home_score"])
    n90 = int(((df["home_score"] != df["home_score_ft"])
               | (df["away_score"] != df["away_score_ft"]))
              .where(df["home_score"].notna(), False).sum())
    print(f"Saved {path}: {len(df)} rows, latest played match "
          f"{played['date'].max().date()}; {n90} extra-time scores "
          f"rewritten to the 90' result")
    return df


def load_results(path=RESULTS_PATH):
    """results.csv with knockout scores rewritten to the 90-minute result.

    `home_score`/`away_score` are what Penka/Superbru and the odds market
    settle on: the score after 90 minutes. The dataset's original convention
    (score after extra time, pens excluded) is preserved in
    `home_score_ft`/`away_score_ft`, and `shootout_winner` names the winner
    of a penalty shootout — consumers that need the *real* outcome (bracket
    advancement, result display) read those. See `_ninety_minute_scores`.
    """
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return _ninety_minute_scores(df, os.path.dirname(path) or ".")


def _ninety_minute_scores(df, input_dir):
    """Rebuild the 90' score from goalscorers.csv + shootouts.csv (same
    dataset, expected next to results.csv).

    Convention audit (2026-07, all goals dated 2006+): stoppage-time goals
    are recorded as the base minute (Kroos 90+5 → 90, Weghorst 90+11 → 90),
    so minute >= 91 unambiguously means extra time — every one of the 26
    goals at minutes 91-99 belongs to a genuine extra-time match. A match is
    a correction candidate when it has an ET goal or appears in
    shootouts.csv, and is corrected only when its scorer rows are complete
    and consistent (per-team goal totals equal the recorded score, no NA
    minutes); the 90' score is then the goals at minute <= 90. Candidates
    without scorer coverage keep the recorded score: shootout matches are
    draws either way, and ET-decided matches without coverage are
    undetectable (minor tournaments only; see docs/data-sources.md).
    """
    df["home_score_ft"] = df["home_score"]
    df["away_score_ft"] = df["away_score"]
    df["shootout_winner"] = np.nan
    gs_path = os.path.join(input_dir, os.path.basename(GOALSCORERS_PATH))
    so_path = os.path.join(input_dir, os.path.basename(SHOOTOUTS_PATH))
    if not (os.path.exists(gs_path) and os.path.exists(so_path)):
        print("WARNING: goalscorers.csv/shootouts.csv missing — scores keep "
              "the dataset's after-extra-time convention. Run "
              "`wcpred update-data`.")
        return df

    key = ["date", "home_team", "away_team"]
    gs = pd.read_csv(gs_path)
    gs["date"] = pd.to_datetime(gs["date"])
    gs["minute"] = pd.to_numeric(gs["minute"], errors="coerce")
    gs["is_home"] = gs["team"] == gs["home_team"]
    gs["is_away"] = ~gs["is_home"]
    gs["h90"] = gs["is_home"] & (gs["minute"] <= 90)
    gs["a90"] = gs["is_away"] & (gs["minute"] <= 90)
    gs["et"] = gs["minute"] > 90
    gs["na_min"] = gs["minute"].isna()
    agg = gs.groupby(key, as_index=False)[
        ["is_home", "is_away", "h90", "a90", "et", "na_min"]].sum()

    so = pd.read_csv(so_path)
    so["date"] = pd.to_datetime(so["date"])
    so = so[key + ["winner"]].drop_duplicates(subset=key)

    m = df.merge(agg, on=key, how="left").merge(so, on=key, how="left")
    df["shootout_winner"] = m["winner"].to_numpy()
    candidate = (m["et"] > 0) | m["winner"].notna()
    consistent = ((m["is_home"] == m["home_score"])
                  & (m["is_away"] == m["away_score"])
                  & (m["na_min"] == 0))
    fix = (candidate & consistent).to_numpy()
    df.loc[fix, "home_score"] = m.loc[fix, "h90"].astype(float).to_numpy()
    df.loc[fix, "away_score"] = m.loc[fix, "a90"].astype(float).to_numpy()
    return df


def load_odds(path):
    """CSV columns: home_team, away_team, odds_1, odds_X, odds_2.
    Odds may be American (-235, +375) or decimal (1.45, 4.20); autodetected."""
    return pd.read_csv(path, dtype={"odds_1": str, "odds_X": str, "odds_2": str})


def resolve_odds_path(as_of, root=""):
    """Odds file in force at `as_of`'s generation time — the frozen-in-time
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


def _shrinkage_rows(m, as_of, mode, weight):
    """Synthetic fractional 1-1 draws that shrink the weakly-identified
    cross-confederation rating offsets toward a common center (the
    pseudo-game / phantom-player augmentation of arXiv 2606.03805; rejected,
    see docs/known-limitations.md). Real matches are untouched.

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
    without leaking what happened on or after that date.

    Rows whose teams are still undecided are dropped: once a knockout round is
    scheduled, the dataset lists its matches with the venue set but the teams
    as NA until the feeding round is played. They are not predictable targets,
    and the bracket simulation fills those slots itself."""
    wc = df[(df["tournament"] == "FIFA World Cup")
            & (df["date"] >= from_date)
            & df["home_team"].notna() & df["away_team"].notna()]
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
