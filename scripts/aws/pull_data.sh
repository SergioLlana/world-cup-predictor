#!/usr/bin/env bash
#
# Phase 1 of docs/aws-migration-plan.md: bring the canonical data/ tree down
# from S3 — for local development once data/ leaves git (phase 5), and as the
# first step of the scheduled pipeline container (phase 3).
#
# No --delete by default: local extras (experiments, work in progress) survive.
# --exact mirrors the bucket, removing local files that are not in S3 — what
# the pipeline container wants for a clean slate.
#
# Usage:
#   scripts/aws/pull_data.sh [--exact] [--dry-run]

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --exact)   EXTRA+=(--delete) ;;
    --dry-run) EXTRA+=(--dryrun) ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Same excludes as push_data.sh: they never travel, and with --exact the
# exclusion also shields the local-only trees from deletion.
aws s3 sync "s3://$DATA_BUCKET/data/" data/ \
  --exclude "experiments/*" --exclude "tuning/*" \
  ${EXTRA[@]+"${EXTRA[@]}"}

echo "Pulled s3://$DATA_BUCKET/data/ -> data/"
