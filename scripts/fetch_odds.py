"""Fetch World Cup 1X2 odds into odds.csv via The Odds API.

Setup (one-off):
  1. Get a free API key at https://the-odds-api.com (500 requests/month free)
  2. export ODDS_API_KEY=your_key

Usage:
  python scripts/fetch_odds.py [--out odds.csv] [--merge]

Bookmakers only price near-term fixtures, so a single call never covers all 72
group matches. Re-run with --merge every few days as later matchdays open up: it
upserts the freshly priced matches into odds.csv — adding new matchdays and
refreshing already-stored matches with the sharper, closer-to-kickoff prices —
without dropping the matchdays you collected earlier.

If you prefer not to use the API, fill odds.csv by hand from
oddschecker.com/us/soccer/world-cup (takes ~1 min per matchday).
American (+150/-200) and decimal (2.50) formats both work.
"""
import argparse
import csv
import json
import os
import ssl
import sys
import urllib.request

API = ("https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
       "?regions=eu&markets=h2h&oddsFormat=decimal&apiKey={key}")


def _ssl_context():
    """Verifying TLS context, preferring certifi's CA bundle (macOS python.org
    builds often ship without a usable system bundle). Mirrors fetch_xg.py."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

FIELDS = ["home_team", "away_team", "odds_1", "odds_X", "odds_2"]

# The Odds API team names -> dataset team names (extend as needed)
NAME_MAP = {
    "South Korea": "South Korea", "Korea Republic": "South Korea",
    "Czechia": "Czech Republic", "USA": "United States",
    "Cote d'Ivoire": "Ivory Coast", "Türkiye": "Turkey",
}


def fetch_rows(key):
    """Currently priced fixtures as [home, away, odds_1, odds_X, odds_2] rows,
    each price the median across bookmakers (more robust than a single book)."""
    req = urllib.request.Request(API.format(key=key),
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30,
                                    context=_ssl_context()) as r:
            events = json.load(r)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            sys.exit("TLS certificate verification failed. Install CA certs "
                     "(`pip install certifi`, or run the 'Install Certificates"
                     ".command' bundled with python.org Python on macOS).")
        raise

    rows = []
    for ev in events:
        home = NAME_MAP.get(ev["home_team"], ev["home_team"])
        away = NAME_MAP.get(ev["away_team"], ev["away_team"])
        prices = {"1": [], "X": [], "2": []}
        for bk in ev.get("bookmakers", []):
            for mkt in bk["markets"]:
                if mkt["key"] != "h2h":
                    continue
                for o in mkt["outcomes"]:
                    if o["name"] == ev["home_team"]:
                        prices["1"].append(o["price"])
                    elif o["name"] == ev["away_team"]:
                        prices["2"].append(o["price"])
                    else:
                        prices["X"].append(o["price"])
        if all(prices.values()):
            def med(v):
                return sorted(v)[len(v) // 2]
            rows.append([home, away, med(prices["1"]),
                         med(prices["X"]), med(prices["2"])])
    return rows


def load_existing(path):
    """Existing odds.csv as {(home, away): row}, or empty if the file is absent."""
    try:
        with open(path, newline="") as f:
            return {(r[0], r[1]): r for r in list(csv.reader(f))[1:] if r}
    except FileNotFoundError:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/input/odds.csv")
    ap.add_argument("--merge", action="store_true",
                    help="upsert into an existing odds.csv instead of "
                         "overwriting it (accumulate across matchdays)")
    args = ap.parse_args()

    key = os.environ.get("ODDS_API_KEY")
    if not key:
        sys.exit("Set ODDS_API_KEY first (free key: https://the-odds-api.com)")

    rows = fetch_rows(key)
    table = load_existing(args.out) if args.merge else {}
    before = len(table)
    for row in rows:
        table[(row[0], row[1])] = row
    added = len(table) - before
    refreshed = len(rows) - added

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(table.values())

    if args.merge:
        print(f"Fetched {len(rows)} priced matches: {added} new, "
              f"{refreshed} refreshed. {args.out} now holds {len(table)}.")
    else:
        print(f"Wrote {len(rows)} matches to {args.out}")


if __name__ == "__main__":
    main()
