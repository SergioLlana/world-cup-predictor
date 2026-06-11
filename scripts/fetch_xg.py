"""Fetch national-team xG into xg.csv via FotMob's public JSON API.

Why this exists: FBref lost its Opta feed in January 2026, so the FBref
route described in older docs no longer yields xG (current or historical).
FotMob still publishes its own xG model for international matches through an
unauthenticated JSON endpoint, covering friendlies, qualifiers, continental
cups and the World Cup -- exactly the matches that feed the team ratings.

Usage:
  python scripts/fetch_xg.py --from 2023-01-01 --to 2026-06-09
  python scripts/fetch_xg.py --from 2025-06-01 --to 2025-06-10 --out xg.csv
  python scripts/fetch_xg.py --from 2024-06-01 --to 2024-07-31 --discover

Output (matches the format prepare_training expects):
  date,home_team,away_team,home_xg,away_xg

No API key needed. The script sleeps between requests to stay polite; a wide
range (a few years) is fine but takes a while -- one request per day plus one
per international match found.

Incremental / resumable: progress is checkpointed to `<out>.done` (the set of
days already fetched, including empty ones). Re-running the same command picks
up where it left off -- so if a long backfill dies mid-way, just run it again.
Each day's rows are committed atomically and de-duplicated by
(date, home, away), so resuming never corrupts or duplicates. Use --restart to
ignore the checkpoint and rebuild from scratch.

Notes:
  * Only matches FotMob has actually modelled carry xG; older/minor games are
    skipped automatically.
  * Team names are mapped to the martj42 dataset (see NAME_MAP); unmapped
    names pass through and simply fail to merge if they differ -- extend the
    map if you spot World Cup teams being dropped.
  * Dates are the UTC kickoff day. A handful of late-night games may land one
    day off the dataset's date and not merge; harmless, just lost coverage.
"""
import argparse
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

HEADER = ["date", "home_team", "away_team", "home_xg", "away_xg"]

MATCHES_URL = "https://www.fotmob.com/api/data/matches?date={ymd}"
DETAILS_URL = "https://www.fotmob.com/api/data/matchDetails?matchId={mid}"

# Senior national-team competitions, keyed by FotMob `primaryId`.
# All verified live against the matches feed except where marked. Youth
# competitions (e.g. 344 Friendlies U21, 10437 Euro U21 Q) are deliberately
# excluded. Run with --discover to find ids for anything missing.
SENIOR_NT_LEAGUES = {
    77: "FIFA World Cup",
    114: "Friendlies",
    10195: "WCQ UEFA",
    10196: "WCQ CAF",
    10197: "WCQ AFC",
    10198: "WCQ CONCACAF",
    10199: "WCQ CONMEBOL",
    50: "EURO",
    44: "Copa America",          # well-known id, not re-verified this run
    9806: "UEFA Nations League A",
    9807: "UEFA Nations League B",
    9808: "UEFA Nations League C",
    9809: "UEFA Nations League D",
    9821: "CONCACAF Nations League",
    289: "Africa Cup of Nations",
    290: "AFC Asian Cup",
    298: "CONCACAF Gold Cup",
}

# FotMob name -> martj42 dataset name. Only the ones that actually differ.
NAME_MAP = {
    "USA": "United States",
    "Ireland": "Republic of Ireland",
    "China": "China PR",
    "Czechia": "Czech Republic",
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "DR Congo": "DR Congo",
}

def _ssl_context():
    """A verifying TLS context. Prefer certifi's CA bundle, since macOS
    python.org builds often ship without a usable system bundle."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        return urllib.request.urlopen(req, timeout=20, context=_SSL_CTX)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            sys.exit("TLS certificate verification failed. Install CA certs "
                     "(`pip install certifi`, or run the 'Install Certificates"
                     ".command' bundled with python.org Python on macOS).")
        raise


def fetch_json(url):
    with _open(url) as r:
        return json.load(r)


def team_xg(match_id):
    """Return (home_xg, away_xg) as floats, or None if FotMob has no xG."""
    data = fetch_json(DETAILS_URL.format(mid=match_id))
    try:
        groups = data["content"]["stats"]["Periods"]["All"]["stats"]
    except (KeyError, TypeError):
        return None
    for grp in groups:
        for stat in grp.get("stats", []):
            if stat.get("key") == "expected_goals":
                vals = stat.get("stats")
                if vals and all(v not in (None, "") for v in vals):
                    return float(vals[0]), float(vals[1])
    return None


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def load_existing(out):
    """Read an existing xg.csv into a {(date, home, away): row} dict."""
    rows = {}
    if os.path.exists(out):
        with open(out, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            for row in reader:
                if len(row) >= 5:
                    rows[(row[0], row[1], row[2])] = row
    return rows


def load_done(path):
    if os.path.exists(path):
        with open(path) as f:
            return set(f.read().split())
    return set()


def _atomic_write(path, write_fn):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        write_fn(f)
    os.replace(tmp, path)


def save_progress(out, done_path, rows, done):
    _atomic_write(out, lambda f: (
        csv.writer(f).writerow(HEADER),
        csv.writer(f).writerows(rows[k] for k in sorted(rows)),
    ))
    _atomic_write(done_path, lambda f: f.write("\n".join(sorted(done))))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    today = date.today()
    ap.add_argument("--from", dest="start", default=str(today - timedelta(days=365 * 3)),
                    help="start date YYYY-MM-DD (default: 3 years ago)")
    ap.add_argument("--to", dest="end", default=str(today),
                    help="end date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default="data/input/xg.csv")
    ap.add_argument("--leagues", help="comma-separated FotMob primaryIds to "
                    "override the built-in national-team whitelist")
    ap.add_argument("--discover", action="store_true",
                    help="just print the (id | name) of every league seen in "
                         "the range, then exit (use to extend the whitelist)")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="seconds to wait between requests (default: 0.4)")
    ap.add_argument("--restart", action="store_true",
                    help="ignore the <out>.done checkpoint and rebuild from "
                         "scratch")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        sys.exit("--from must be on or before --to")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    if args.leagues:
        wanted = {int(x) for x in args.leagues.split(",")}
    else:
        wanted = set(SENIOR_NT_LEAGUES)

    # --- discover mode: just enumerate league ids, no checkpointing ---
    if args.discover:
        discovered = {}
        for day in daterange(start, end):
            try:
                feed = fetch_json(MATCHES_URL.format(ymd=day.strftime("%Y%m%d")))
            except Exception as e:
                print(f"  {day}: skipped ({e})", file=sys.stderr)
            else:
                for league in feed.get("leagues", []):
                    lid = league.get("primaryId") or league.get("id")
                    discovered[lid] = league.get("name", "")
            time.sleep(args.sleep)
        for lid, name in sorted(discovered.items(), key=lambda kv: str(kv[1])):
            print(f"{lid}\t{name}")
        return

    # --- incremental backfill ---
    done_path = args.out + ".done"
    rows = {} if args.restart else load_existing(args.out)
    done = set() if args.restart else load_done(done_path)
    n_days = (end - start).days + 1

    try:
        for i, day in enumerate(daterange(start, end), 1):
            ymd = day.strftime("%Y%m%d")
            if ymd in done:
                continue
            try:
                feed = fetch_json(MATCHES_URL.format(ymd=ymd))
                day_rows = []
                for league in feed.get("leagues", []):
                    lid = league.get("primaryId") or league.get("id")
                    if lid not in wanted:
                        continue
                    label = SENIOR_NT_LEAGUES.get(lid, lid)
                    for m in league.get("matches", []):
                        if not m.get("status", {}).get("finished"):
                            continue
                        home = NAME_MAP.get(m["home"]["name"], m["home"]["name"])
                        away = NAME_MAP.get(m["away"]["name"], m["away"]["name"])
                        xg = team_xg(m["id"])
                        time.sleep(args.sleep)
                        if xg is None:
                            continue
                        day_rows.append([str(day), home, away,
                                         round(xg[0], 2), round(xg[1], 2)])
                        print(f"  {day}  {home} {xg[0]:.2f}-{xg[1]:.2f} "
                              f"{away}  [{label}]")
            except Exception as e:
                # leave the day un-done so a re-run retries it
                print(f"  {day}: failed, will retry on next run ({e})",
                      file=sys.stderr)
                time.sleep(args.sleep)
                continue

            # day completed cleanly: commit its rows and mark it done
            for row in day_rows:
                rows[(row[0], row[1], row[2])] = row
            done.add(ymd)
            if i % 20 == 0 or i == n_days:
                save_progress(args.out, done_path, rows, done)
                print(f"... {i}/{n_days} days, {len(rows)} matches with xG",
                      file=sys.stderr)
            time.sleep(args.sleep)
    finally:
        save_progress(args.out, done_path, rows, done)

    print(f"\nWrote {len(rows)} matches with xG to {args.out}")


if __name__ == "__main__":
    main()
