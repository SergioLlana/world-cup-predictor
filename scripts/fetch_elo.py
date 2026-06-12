"""Fetch historical World Football Elo ratings into elo.csv.

eloratings.net serves its data as plain TSV: one file per completed year with
the ratings after that year's final match (stamped <year>-12-31 here), plus
World.tsv with the current list (stamped with today's date). Decades of
accumulated inter-confederation results make these ratings the external
cross-bloc anchor of docs/model-robustness-plan.md Phase 3; `data.load_elo`
resolves the snapshot in force at any --as-of causally, so only fetch year
files for *completed* years — a mid-year <year>.tsv mirrors World.tsv and
would be mislabelled as year-end.

Usage:
  python scripts/fetch_elo.py                       # 2010..last year + current
  python scripts/fetch_elo.py --from-year 2015
  python scripts/fetch_elo.py --skip-current        # year-end snapshots only

Output (appended/merged into --out, de-duplicated by (date, team)):
  data/input/elo.csv   date,team,elo

Notes:
  * Team names are mapped to the martj42 dataset (NAME_MAP); names that do
    not exist in data/input/results.csv are reported at the end and written
    anyway — extend the map if a World Cup team shows up there.
  * Re-running is idempotent: existing (date, team) rows are replaced by the
    fresh fetch, everything else is kept.
"""
import argparse
import csv
import os
import ssl
import sys
import time
import urllib.request
from datetime import date

HEADER = ["date", "team", "elo"]

BASE_URL = "https://www.eloratings.net/{name}.tsv"
TEAMS_FILE = "en.teams"

# eloratings.net name -> martj42 dataset name. Only the ones that differ.
NAME_MAP = {
    "Czechia": "Czech Republic",
    "East Timor": "Timor-Leste",
    "Eastern Samoa": "American Samoa",
    "FS Micronesia": "Micronesia",
    "Ireland": "Republic of Ireland",
    "Macao": "Macau",
    "Macedonia": "North Macedonia",
    "Reunion": "Réunion",
    "Saint Barthelemy": "Saint Barthélemy",
    "Sao Tome and Principe": "São Tomé and Príncipe",
    "St Kitts and Nevis": "Saint Kitts and Nevis",
    "St Lucia": "Saint Lucia",
    "St Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Swaziland": "Eswatini",
    "US Virgin Islands": "United States Virgin Islands",
    "Vatican": "Vatican City",
    "Wallis and Futuna": "Wallis Islands and Futuna",
}

# Entities with no martj42 counterpart at all; written as-is (they simply
# never match a trained team) but excluded from the unmapped warning.
NO_COUNTERPART = {"Christmas Island", "Cocos Islands", "Saba",
                  "Sint Eustatius"}

# Historical entities with no martj42 national-team counterpart (or whose
# modern successor is listed separately); skipped without a warning.
SKIP = {"Great Britain", "Soviet Union", "Yugoslavia", "Serbia and Montenegro",
        "Czechoslovakia", "East Germany", "Saarland", "Zanzibar", "Kernow",
        "Commonwealth of Independent States"}


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_tsv(name):
    req = urllib.request.Request(BASE_URL.format(name=name),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
        return r.read().decode("utf-8")


def team_names():
    """code -> canonical eloratings name (first name column of en.teams.tsv;
    `<code>_loc` rows are venue phrasings, not teams)."""
    names = {}
    for line in fetch_tsv(TEAMS_FILE).splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and not cols[0].endswith("_loc"):
            names[cols[0]] = cols[1]
    return names


def parse_ratings(tsv, names):
    """[(team, elo)] from a ratings TSV (year files and World.tsv share the
    layout: team code in column 2, rating in column 3)."""
    rows = []
    for line in tsv.splitlines():
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        name = names.get(cols[2])
        if name is None or name in SKIP:
            continue
        rows.append((NAME_MAP.get(name, name), int(cols[3])))
    return rows


def known_teams(results_path):
    if not os.path.exists(results_path):
        return None
    teams = set()
    with open(results_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            teams.add(r["home_team"])
            teams.add(r["away_team"])
    return teams


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-year", type=int, default=2010)
    ap.add_argument("--to-year", type=int, default=date.today().year - 1,
                    help="last completed year to fetch (default: last year)")
    ap.add_argument("--skip-current", action="store_true",
                    help="skip the live World.tsv snapshot (dated today)")
    ap.add_argument("--out", default="data/input/elo.csv")
    ap.add_argument("--results", default="data/input/results.csv",
                    help="dataset used to sanity-check the name mapping")
    args = ap.parse_args()
    if args.to_year >= date.today().year:
        sys.exit("--to-year must be a completed year; the current year's "
                 "file mirrors World.tsv and would be mislabelled")

    names = team_names()
    snapshots = [(f"{y}-12-31", str(y)) for y in
                 range(args.from_year, args.to_year + 1)]
    if not args.skip_current:
        snapshots.append((str(date.today()), "World"))

    rows = {}   # (date, team) -> elo
    if os.path.exists(args.out):
        with open(args.out, newline="", encoding="utf-8") as f:
            rows = {(r["date"], r["team"]): r["elo"]
                    for r in csv.DictReader(f)}
    before = len(rows)

    for stamp, name in snapshots:
        ratings = parse_ratings(fetch_tsv(name), names)
        for team, elo in ratings:
            rows[(stamp, team)] = elo
        print(f"{name}.tsv -> {len(ratings)} teams (dated {stamp})")
        time.sleep(1)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for (stamp, team), elo in sorted(rows.items()):
            w.writerow([stamp, team, elo])
    print(f"Saved {args.out}: {len(rows)} rows ({len(rows) - before} new)")

    known = known_teams(args.results)
    if known is not None:
        unmapped = sorted({t for _, t in rows} - known - NO_COUNTERPART)
        if unmapped:
            print(f"\nWARNING: {len(unmapped)} team names not found in "
                  f"{args.results} (extend NAME_MAP if any matter):")
            print("  " + ", ".join(unmapped))


if __name__ == "__main__":
    main()
