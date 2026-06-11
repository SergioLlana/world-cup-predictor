"""Fetch national-team xG and historical 1X2 odds from SofaScore.

SofaScore's API rejects plain HTTP clients (TLS fingerprinting) and
temp-bans IPs that sustain a high request rate -- HTTP 403 with
{"reason": "challenge"}, served by their own edge, while the website keeps
working. curl_cffi's browser impersonation (`pip install curl_cffi`) handles
the first; pacing, courtesy breaks and long cooldowns (below) handle the
second. Endpoint map and verified coverage live in docs/sofascore.md; the
short version:

  * odds -- closing 1X2 from one featured book, back to at least WC2018,
            friendlies included. The dataset The Odds API charges for.
  * xG   -- nothing before ~June 2022 (WC2018/2019/2021 verified absent);
            WC2022 complete; friendlies only from ~2024-25 and partial.
            Complements FotMob (scripts/fetch_xg.py), which has none.
            Statistics are therefore only requested for days >= --xg-since
            (default 2022-06-01) -- earlier requests would be wasted.

Usage:
  python scripts/fetch_sofascore.py --from 2018-01-01 --to 2026-06-11
  python scripts/fetch_sofascore.py --from 2018-06-01 --to 2018-07-15 --skip-xg
  python scripts/fetch_sofascore.py --from 2024-01-10 --to 2024-02-12 --discover

Output (decimal odds; xG in the same format prepare_training expects):
  --xg-out    data/input/xg_sofascore.csv   date,home_team,away_team,home_xg,away_xg
  --odds-out  data/input/odds_history.csv   date,home_team,away_team,odds_1,odds_X,odds_2

Incremental / resumable like fetch_xg.py: fetched days are checkpointed to
--done (default data/input/sofascore.done) and skipped on re-run; rows are
committed atomically and de-duplicated by (date, home, away). The checkpoint
does NOT record whether a day ran with --skip-xg/--skip-odds -- point --done
at a separate file for partial backfills (e.g. an odds-only pre-2022 run).

Ban handling: on 403/429 the script cools down for 1-15 minutes, rotating the
TLS fingerprint each time. If the block survives all cooldowns (~25 min) it
saves progress and exits -- wait an hour or two and re-run the same command;
the checkpoint resumes where it stopped. Hammering a banned IP extends the ban.

Notes:
  * A day needs both the scheduled-events feed and its /inverse complement
    (some matches only appear in the latter; it 503s intermittently and is
    retried with backoff). If either fails the day stays un-done and is
    retried on the next run.
  * Dates are the UTC kickoff day, matching the martj42 convention; events
    are assigned to their startTimestamp's UTC day, not the queried day.
  * Unmapped team names are reported at the end when they don't exist in
    data/input/results.csv -- extend NAME_MAP if a relevant team shows up.
"""
import argparse
import csv
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone

try:
    from curl_cffi import requests as creq
except ImportError:
    sys.exit("curl_cffi is required to get past SofaScore's TLS fingerprinting "
             "(plain HTTP gets 403): pip install curl_cffi")

HEADER_XG = ["date", "home_team", "away_team", "home_xg", "away_xg"]
HEADER_ODDS = ["date", "home_team", "away_team", "odds_1", "odds_X", "odds_2"]

EVENTS_URL = "https://api.sofascore.com/api/v1/sport/football/scheduled-events/{d}"
STATS_URL = "https://api.sofascore.com/api/v1/event/{eid}/statistics"
ODDS_URL = "https://api.sofascore.com/api/v1/event/{eid}/odds/1/all"

# Senior national-team competitions, keyed by SofaScore uniqueTournament.id.
# All ids verified live (June 2026) against scheduled-events. Mirrors the
# FotMob whitelist in fetch_xg.py, plus WCQ OFC which FotMob lacks. Run with
# --discover to find ids for anything missing.
SENIOR_NT_TOURNAMENTS = {
    16: "FIFA World Cup",
    851: "International Friendly Games",
    11: "WCQ UEFA",
    13: "WCQ CAF",
    14: "WCQ CONCACAF",
    295: "WCQ CONMEBOL",
    308: "WCQ AFC",
    309: "WCQ OFC",
    1: "EURO",
    133: "Copa America",
    10783: "UEFA Nations League",
    14100: "CONCACAF Nations League",
    270: "Africa Cup of Nations",
    246: "AFC Asian Cup",
    140: "CONCACAF Gold Cup",
}

# SofaScore name -> martj42 dataset name. Only the ones that differ.
# NB: martj42 uses "China" (not "China PR"), "Taiwan" (not "Chinese Taipei").
NAME_MAP = {
    "USA": "United States",
    "Ireland": "Republic of Ireland",
    "Côte d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Chinese Taipei": "Taiwan",
    "St. Kitts & Nevis": "Saint Kitts and Nevis",
    "St. Lucia": "Saint Lucia",
    "St. Vincent & the Grenadines": "Saint Vincent and the Grenadines",
}


def map_name(name):
    if name in NAME_MAP:
        return NAME_MAP[name]
    return name.replace(" & ", " and ")  # Bosnia, Trinidad, Antigua, ...


class BlockedError(RuntimeError):
    """SofaScore is refusing this IP and the cooldowns didn't clear it."""


class Client:
    """Paced HTTP client. Jitters every sleep, takes a long courtesy break
    every BREAK_EVERY requests, and on 403/429 cools down for minutes while
    rotating the TLS fingerprint. A steady machine-gun cadence is what earns
    the IP ban in the first place."""

    IMPERSONATIONS = ["chrome", "chrome131", "chrome124", "safari17_0",
                      "firefox133"]
    BLOCK_COOLDOWNS = [60, 180, 420, 900]  # seconds; ~25 min total, then give up
    BREAK_EVERY = 250                      # requests between courtesy breaks
    BREAK_RANGE = (45, 90)                 # seconds, one courtesy break

    def __init__(self, base_sleep):
        self.base = base_sleep
        self.requests = 0
        self._imp = 0
        self._new_session()

    def _new_session(self):
        imp = self.IMPERSONATIONS[self._imp % len(self.IMPERSONATIONS)]
        self.session = creq.Session(impersonate=imp)

    def _rotate(self):
        self._imp += 1
        self._new_session()

    def get_json(self, url):
        """Parsed JSON; None on 404 (no data for this event); raises
        BlockedError when the IP block won't clear, RuntimeError on
        persistent server errors."""
        blocks = errors = 0
        while True:
            self.requests += 1
            if self.requests % self.BREAK_EVERY == 0:
                pause = random.uniform(*self.BREAK_RANGE)
                print(f"  ... courtesy break {pause:.0f}s after "
                      f"{self.requests} requests", file=sys.stderr)
                time.sleep(pause)
            try:
                r = self.session.get(url, timeout=20)
            except Exception as e:
                errors += 1
                if errors > 3:
                    raise RuntimeError(f"{type(e).__name__} on {url}: {e}")
                time.sleep(self.base * 2 ** errors)
                continue
            if r.status_code == 200:
                time.sleep(self.base * random.uniform(0.75, 1.5))
                return r.json()
            if r.status_code == 404:
                time.sleep(self.base * random.uniform(0.75, 1.5))
                return None
            if r.status_code in (403, 429):
                if blocks >= len(self.BLOCK_COOLDOWNS):
                    raise BlockedError(
                        f"HTTP {r.status_code} persisted through "
                        f"{len(self.BLOCK_COOLDOWNS)} cooldowns: {url}")
                cool = self.BLOCK_COOLDOWNS[blocks]
                blocks += 1
                print(f"  ... HTTP {r.status_code} (rate-limited), cooling "
                      f"down {cool}s and rotating fingerprint "
                      f"({blocks}/{len(self.BLOCK_COOLDOWNS)})", file=sys.stderr)
                time.sleep(cool)
                self._rotate()
                continue
            errors += 1  # 5xx and anything else: short backoff
            if errors > 4:
                raise RuntimeError(f"HTTP {r.status_code} after {errors} "
                                   f"tries: {url}")
            time.sleep(self.base * 2 ** errors)


def day_events(client, day, all_leagues=False):
    """All events of a UTC day. The main feed is partial; /inverse holds the
    rest. Raises if either page can't be fetched, so the day is retried."""
    events = []
    for suffix in ("", "/inverse"):
        data = client.get_json(EVENTS_URL.format(d=str(day)) + suffix)
        if not data or "events" not in data:
            # the day feed always exists; a 404/empty body here is a transient
            # failure -- treating it as "no matches" would silently drop the
            # inverse-only events (most of the day) and checkpoint the day
            raise RuntimeError(f"empty scheduled-events{suffix} feed")
        events += data["events"]
    out = []
    for e in events:
        ut = (e.get("tournament", {}).get("uniqueTournament") or {})
        if not all_leagues and ut.get("id") not in SENIOR_NT_TOURNAMENTS:
            continue
        if e.get("status", {}).get("type") != "finished":
            continue
        ts = e.get("startTimestamp")
        if ts is None:
            continue
        utc_day = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if utc_day != day:  # the feed leaks adjacent days; avoid double-processing
            continue
        out.append(e)
    return out


def event_xg(client, eid):
    """(home_xg, away_xg) floats, or None if SofaScore has no xG."""
    data = client.get_json(STATS_URL.format(eid=eid))
    if not data:
        return None
    for period in data.get("statistics", []):
        if period.get("period") != "ALL":
            continue
        for grp in period.get("groups", []):
            for item in grp.get("statisticsItems", []):
                if item.get("name") == "Expected goals":
                    try:
                        return float(item["home"]), float(item["away"])
                    except (KeyError, TypeError, ValueError):
                        return None
    return None


def event_odds(client, eid):
    """(odds_1, odds_X, odds_2) decimal, or None if no full-time market."""
    data = client.get_json(ODDS_URL.format(eid=eid))
    if not data:
        return None
    for mk in data.get("markets", []):
        if mk.get("marketName") != "Full time":
            continue
        prices = {}
        for ch in mk.get("choices", []):
            frac = ch.get("fractionalValue", "")
            try:
                num, den = frac.split("/")
                prices[ch.get("name")] = round(1 + float(num) / float(den), 2)
            except (ValueError, ZeroDivisionError):
                pass
        if all(k in prices for k in ("1", "X", "2")):
            return prices["1"], prices["X"], prices["2"]
    return None


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def load_existing(path):
    rows = {}
    if os.path.exists(path):
        with open(path, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
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


def save_progress(xg_out, odds_out, done_path, xg_rows, odds_rows, done):
    _atomic_write(xg_out, lambda f: (
        csv.writer(f).writerow(HEADER_XG),
        csv.writer(f).writerows(xg_rows[k] for k in sorted(xg_rows)),
    ))
    _atomic_write(odds_out, lambda f: (
        csv.writer(f).writerow(HEADER_ODDS),
        csv.writer(f).writerows(odds_rows[k] for k in sorted(odds_rows)),
    ))
    _atomic_write(done_path, lambda f: f.write("\n".join(sorted(done))))


def known_teams():
    """Team set from results.csv, to flag names that won't merge."""
    path = "data/input/results.csv"
    teams = set()
    if os.path.exists(path):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                teams.add(r["home_team"])
                teams.add(r["away_team"])
    return teams


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    today = date.today()
    ap.add_argument("--from", dest="start", default=str(today - timedelta(days=30)),
                    help="start date YYYY-MM-DD (default: 30 days ago)")
    ap.add_argument("--to", dest="end", default=str(today),
                    help="end date YYYY-MM-DD (default: today)")
    ap.add_argument("--xg-out", default="data/input/xg_sofascore.csv")
    ap.add_argument("--odds-out", default="data/input/odds_history.csv")
    ap.add_argument("--done", default="data/input/sofascore.done",
                    help="checkpoint file of completed days")
    ap.add_argument("--xg-since", default="2022-06-01",
                    help="don't request statistics for days before this date "
                         "-- SofaScore has no international xG earlier "
                         "(default: 2022-06-01)")
    ap.add_argument("--skip-xg", action="store_true",
                    help="don't fetch statistics at all (odds only)")
    ap.add_argument("--skip-odds", action="store_true",
                    help="don't fetch odds (xG only)")
    ap.add_argument("--leagues", help="comma-separated uniqueTournament ids to "
                    "override the built-in national-team whitelist")
    ap.add_argument("--discover", action="store_true",
                    help="print (id | name | category) of every tournament "
                         "with finished matches in the range, then exit")
    ap.add_argument("--sleep", type=float, default=1.2,
                    help="base seconds between requests, jittered 0.75-1.5x "
                         "(default: 1.2; going much lower earns an IP ban)")
    ap.add_argument("--restart", action="store_true",
                    help="ignore the --done checkpoint and rebuild from scratch")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    xg_since = date.fromisoformat(args.xg_since)
    if start > end:
        sys.exit("--from must be on or before --to")
    if args.skip_xg and args.skip_odds:
        sys.exit("--skip-xg and --skip-odds together leave nothing to fetch")

    global SENIOR_NT_TOURNAMENTS
    if args.leagues:
        SENIOR_NT_TOURNAMENTS = {int(x): str(x) for x in args.leagues.split(",")}

    client = Client(args.sleep)

    # --- discover mode: enumerate tournament ids, no checkpointing ---
    if args.discover:
        seen = {}
        for day in daterange(start, end):
            try:
                for e in day_events(client, day, all_leagues=True):
                    t = e.get("tournament", {})
                    ut = t.get("uniqueTournament") or {}
                    cat = (t.get("category") or {}).get("name", "?")
                    seen[ut.get("id") or t.get("id")] = (ut.get("name") or
                                                         t.get("name", ""), cat)
            except BlockedError as e:
                sys.exit(f"Blocked by SofaScore ({e}); try again in an hour.")
            except Exception as e:
                print(f"  {day}: skipped ({e})", file=sys.stderr)
        for tid, (name, cat) in sorted(seen.items(), key=lambda kv: str(kv[1])):
            print(f"{tid}\t{name}\t[{cat}]")
        return

    # --- incremental backfill ---
    for out in (args.xg_out, args.odds_out, args.done):
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    xg_rows = {} if args.restart else load_existing(args.xg_out)
    odds_rows = {} if args.restart else load_existing(args.odds_out)
    done = set() if args.restart else load_done(args.done)
    teams = known_teams()
    unmatched = {}
    n_days = (end - start).days + 1
    blocked = None

    try:
        for i, day in enumerate(daterange(start, end), 1):
            if str(day) in done:
                continue
            want_xg = not args.skip_xg and day >= xg_since
            try:
                events = day_events(client, day)
                day_xg, day_odds = [], []
                for e in events:
                    home = map_name(e["homeTeam"]["name"])
                    away = map_name(e["awayTeam"]["name"])
                    label = SENIOR_NT_TOURNAMENTS.get(
                        (e["tournament"].get("uniqueTournament") or {}).get("id"), "?")
                    for name in (home, away):
                        if teams and name not in teams:
                            unmatched[name] = unmatched.get(name, 0) + 1
                    parts = []
                    if want_xg:
                        xg = event_xg(client, e["id"])
                        if xg:
                            day_xg.append([str(day), home, away,
                                           round(xg[0], 2), round(xg[1], 2)])
                            parts.append(f"xG {xg[0]:.2f}-{xg[1]:.2f}")
                    if not args.skip_odds:
                        odds = event_odds(client, e["id"])
                        if odds:
                            day_odds.append([str(day), home, away,
                                             odds[0], odds[1], odds[2]])
                            parts.append(f"1X2 {odds[0]}/{odds[1]}/{odds[2]}")
                    if parts:
                        print(f"  {day}  {home} vs {away}  "
                              f"{', '.join(parts)}  [{label}]")
            except BlockedError as e:
                blocked = e
                break
            except Exception as e:
                # leave the day un-done so a re-run retries it
                print(f"  {day}: failed, will retry on next run ({e})",
                      file=sys.stderr)
                continue

            for row in day_xg:
                xg_rows[(row[0], row[1], row[2])] = row
            for row in day_odds:
                odds_rows[(row[0], row[1], row[2])] = row
            done.add(str(day))
            if i % 10 == 0 or i == n_days:
                save_progress(args.xg_out, args.odds_out, args.done,
                              xg_rows, odds_rows, done)
                print(f"... {i}/{n_days} days, {len(xg_rows)} xG rows, "
                      f"{len(odds_rows)} odds rows", file=sys.stderr)
    finally:
        save_progress(args.xg_out, args.odds_out, args.done,
                      xg_rows, odds_rows, done)

    print(f"\nWrote {len(xg_rows)} xG rows to {args.xg_out} and "
          f"{len(odds_rows)} odds rows to {args.odds_out}")
    if unmatched:
        print("Team names not found in results.csv (extend NAME_MAP if any "
              "matter):", file=sys.stderr)
        for name, n in sorted(unmatched.items(), key=lambda kv: -kv[1]):
            print(f"  {n:3d}  {name}", file=sys.stderr)
    if blocked:
        sys.exit(f"\nStopped early: SofaScore is blocking this IP ({blocked}).\n"
                 "Progress is checkpointed -- wait an hour or two and re-run "
                 "the same command to resume.")


if __name__ == "__main__":
    main()
