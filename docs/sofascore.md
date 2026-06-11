# SofaScore as a data source

Can SofaScore supply the xG and odds FotMob/The Odds API don't have? First
investigated June 2026 (verdict then: no — Cloudflare 403). **Re-checked live
11 June 2026: the blocker is gone.** `curl_cffi`'s TLS impersonation
(`impersonate="chrome"`) returns HTTP 200 on every endpoint — no headless
browser needed. `scripts/fetch_sofascore.py` implements the scraper.

## Access

- Plain `urllib`/`curl` still get 403 on all three hosts (TLS/JA3
  fingerprinting), even with full browser headers.
- `curl_cffi` (`pip install curl_cffi`) bypasses the fingerprinting cleanly.
- **But there is rate-based banning on top** (learned the hard way, June 2026):
  ~1 request/s sustained for hours earns an IP-level 403 with
  `{"reason": "challenge"}` — served by SofaScore's own edge (Varnish, no
  `cf-ray`), on every host and fingerprint, while the website keeps loading.
  It expires on its own (order of hours); retrying fast extends it. The
  scraper therefore jitters its pacing, takes periodic courtesy breaks,
  cools down minutes on a 403, and aborts (resumably) if the block persists.
- Day feed: `api/v1/sport/football/scheduled-events/{YYYY-MM-DD}` **plus**
  `{date}/inverse` for the rest of that day's events. `/inverse` 503s
  intermittently — retry with backoff; some matches only appear there.
- Match xG: `api/v1/event/{id}/statistics` → period `ALL`, item
  `"Expected goals"`. Odds: `api/v1/event/{id}/odds/1/all` → market
  `"Full time"`, fractional prices.

## What it actually has (verified by sampling matches per period)

### xG — does NOT fix the friendlies gap

| Period | SofaScore xG? |
|---|---|
| WC2018, friendlies 2019/2021/mar-2023/mar-2024 | ❌ None |
| WC2022 | ✅ Complete (FotMob: partial) |
| Friendlies jun-2025 | 🟡 Partial — big games yes, minor ones no |

For context, FotMob's gap is structural: **zero friendlies with xG** (0 of
1,103 since jul-2022, verified against the live API — even
Denmark–N. Ireland-sized games) and only ~28% of qualifiers (mostly UEFA).
SofaScore's friendlies xG starts somewhere in 2024–25 and stays partial.
**No free source has xG for all of results.csv** — for minor internationals
nobody computes it.

### Odds — free historical 1X2 (the real find)

`odds/1/all` returns prices for **past** events back to at least WC2018,
including minor friendlies (verified: France–Australia WC2018, China–Philippines
2019). This is the dataset `docs/data-sources.md` listed as "paid / no free
source". Caveats: a single featured book (not a multi-book median like
The Odds API), fractional format, occasional gaps on very minor games (404),
and possible geo-restriction. Prices on past events are effectively closing
odds — good for backtesting/calibrating the market blend (`--odds-weight`),
not a replacement for live medians at predict time.

## Recommendation (revised)

1. **Historical odds backfill: yes** — the one genuinely new capability;
   enables backtesting the odds blend, impossible before.
2. **xG: marginal** — only worth it to top up WC2022 and 2024+ gaps if xG is
   ever re-enabled for WC2026 (current plan: no xG).
3. **Live odds: no change** — The Odds API medians remain better.

## References

- sofascore-wrapper (PyPI): https://pypi.org/project/sofascore-wrapper/
- LanusStats/sofascore.py: https://github.com/federicorabanos/LanusStats/blob/main/LanusStats/sofascore.py
- victorstdev/sofascore-api-stats: https://github.com/victorstdev/sofascore-api-stats
