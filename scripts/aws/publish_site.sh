#!/usr/bin/env bash
#
# Phase 2 of docs/aws-migration-plan.md: publish the static site. Freezes the
# public app to build/site/ (export_static.py), mirrors it to the wcpred-site
# bucket, and invalidates the CloudFront cache so the new JSON is served at once.
#
# Run after the daily generators (the data the export reads must be current).
# During the transition this is a manual local step; phase 3 moves it into the
# scheduled container.
#
# Usage: scripts/aws/publish_site.sh [--dry-run]
#
# Needs 20_site.sh to have run once (it writes the distribution id to SSM).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="--dryrun"

SITE_DIR="build/site"
DIST_PARAM="/wcpred/cloudfront-distribution-id"

# 1. Freeze the public app to build/site/.
echo ">>> export_static.py"
python scripts/export_static.py --out "$SITE_DIR"

# 2. Mirror to the site bucket. --delete: the site is a full rebuild each time,
#    so stale files (e.g. a fixture that changed slug) must not linger. api/ is
#    JSON with default (no) content-type from sync — fine, CloudFront serves it.
echo ">>> s3 sync -> s3://$SITE_BUCKET/"
aws s3 sync "$SITE_DIR/" "s3://$SITE_BUCKET/" --delete $DRY

if [ -n "$DRY" ]; then
  echo "(dry-run: skipping CloudFront invalidation)"
  exit 0
fi

# 3. Invalidate everything (counts as one path; free tier is 1000/month).
dist_id="$(aws ssm get-parameter --name "$DIST_PARAM" \
  --query "Parameter.Value" --output text 2>/dev/null || true)"
if [ -z "$dist_id" ] || [ "$dist_id" = "None" ]; then
  echo "!! $DIST_PARAM not set — run scripts/aws/20_site.sh first." >&2
  exit 1
fi
inv_id="$(aws cloudfront create-invalidation --distribution-id "$dist_id" \
  --paths "/*" --query "Invalidation.Id" --output text)"
echo "invalidation $inv_id on $dist_id: created"
echo "Published."
