#!/usr/bin/env python3
"""Phase 2 of docs/aws-migration-plan.md: freeze the public web app to a folder
of static files (`build/site/`) that CloudFront can serve with no server.

Runs the FastAPI app in public mode (WCPRED_PUBLIC=1) and dumps every response
the frontend fetches to `build/site/api/*.json`, then copies the static assets
(index.html/app.js/style.css/flags/fonts) alongside — with a small flag injected
into index.html so the frontend rewrites its `/api/...` calls to those files.

We call the route functions directly instead of going through an HTTP client:
they return the same JSON-serialisable dicts FastAPI would encode, and it avoids
pulling httpx into the build/container image. HTTPException (e.g. a bayes matrix
with no precomputed CSV on a machine without CmdStan) means "skip this file".

    python scripts/export_static.py            # -> build/site/
    python scripts/export_static.py --out DIR
"""
import argparse
import json
import os
import shutil
import sys
import unicodedata

# Public mode must be set before importing the app: server.PUBLIC is read at
# import time (it disables refresh and switches the calendar to pick_mode —
# exactly the deploy we are freezing). Connectivity is frozen to a static file
# below, so it stays available on the hosted site.
os.environ["WCPRED_PUBLIC"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402

import webapp.server as srv  # noqa: E402
import numpy as np  # noqa: E402


def team_slug(name):
    """lowercase, strip diacritics, spaces -> '-'. Kept byte-identical to the
    JS `slug()` in app.js so the frontend maps /api/matrix to the right file
    (e.g. 'Curaçao' -> 'curacao', 'United States' -> 'united-states')."""
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed
                       if unicodedata.category(c) != "Mn")
    return stripped.lower().replace(" ", "-")


def _json_default(o):
    # pandas records carry numpy scalars; encode them like FastAPI would.
    if isinstance(o, (np.integer, np.floating, np.bool_)):
        return o.item()
    raise TypeError(f"not JSON-serialisable: {type(o)}")


def write_json(out_dir, rel_path, payload):
    path = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        # allow_nan=False mirrors Starlette's strict encoder: a stray NaN fails
        # here (loudly) rather than emitting invalid JSON the browser rejects.
        json.dump(payload, f, ensure_ascii=False, allow_nan=False,
                  default=_json_default, separators=(",", ":"))
    return path


def copy_site_assets(out_dir):
    """Copy webapp/static/ into out_dir and inject the static-mode flag into
    index.html so app.js rewrites /api/... to the exported JSON files."""
    static = srv.STATIC_DIR
    for name in os.listdir(static):
        src = os.path.join(static, name)
        dst = os.path.join(out_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif name != "index.html":
            shutil.copy2(src, dst)

    with open(os.path.join(static, "index.html"), encoding="utf-8") as f:
        html = f.read()
    flag = '<script>window.__WCPRED_STATIC__=true;</script>\n'
    marker = '<script src="/i18n.js"></script>'
    if marker not in html:
        raise SystemExit("index.html: expected i18n.js script tag not found")
    html = html.replace(marker, flag + marker, 1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def export(out_dir):
    n = 0
    n += bool(write_json(out_dir, "api/meta.json", srv.meta()))
    matches = srv.matches()
    write_json(out_dir, "api/matches.json", matches)
    n += 1

    for ap in srv.APPROACHES:
        for eng in srv.ENGINES:
            write_json(out_dir, f"api/picks_{ap}_{eng}.json", srv.picks(ap, eng))
            write_json(out_dir, f"api/groups_{ap}_{eng}.json", srv.groups(ap, eng))
            write_json(out_dir, f"api/sims_{ap}_{eng}.json", srv.sims(ap, eng))
            n += 3

    # Connectivity is model-only (pinned to dc, no approach/engine): one file.
    write_json(out_dir, "api/connectivity.json", srv.connectivity())
    n += 1

    for eng in srv.ENGINES:
        write_json(out_dir, f"api/rankings_history_{eng}.json",
                   srv.rankings_history(eng))
        n += 1
        # /api/rankings is the live-fit fallback: the frontend only hits it when
        # an engine has no history snapshots. Export it when it fits (skip an
        # engine this machine can't fit, e.g. bayes without CmdStan).
        try:
            write_json(out_dir, f"api/rankings_{eng}.json", srv.rankings(eng))
            n += 1
        except HTTPException as e:
            print(f"  skip rankings_{eng}: {e.detail}")

    # One matrix file per fixture x approach x engine. Public mode never
    # highlights the Penka pick (showPick=false), so the default 'outcome'
    # strategy is enough; the probabilities are strategy-independent anyway.
    skipped = 0
    for m in matches["matches"]:
        for ap in srv.APPROACHES:
            for eng in srv.ENGINES:
                try:
                    r = srv.matrix(m["home"], m["away"], m["date"], ap, eng,
                                   srv.DEFAULT_STRATEGY)
                except HTTPException:
                    skipped += 1
                    continue
                rel = (f"api/matrix/{m['date']}_{team_slug(m['home'])}"
                       f"_{team_slug(m['away'])}_{ap}_{eng}.json")
                write_json(out_dir, rel, r)
                n += 1
    if skipped:
        print(f"  {skipped} matrix files skipped (no data / engine not fittable)")

    copy_site_assets(out_dir)
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=os.path.join(ROOT, "build", "site"),
                   help="output directory (default: build/site/)")
    args = p.parse_args()

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out, exist_ok=True)

    n = export(args.out)
    print(f"Exported {n} JSON files + site assets -> {args.out}")


if __name__ == "__main__":
    main()
