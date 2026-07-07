#!/usr/bin/env bash
#
# Phase 1 of docs/aws-migration-plan.md: publish the local data/ tree to the
# (versioned) data bucket. Run after the daily generators — during the
# transition this coexists with the data commits to git; once the scheduled
# pipeline owns generation (phase 4), S3 is the source of truth.
#
# No --delete: snapshots only accumulate, and a locally-pruned file must never
# remove the canonical copy. data/experiments/ and data/tuning/ stay local
# (experiment outputs are not part of the served dataset).
#
# Usage:
#   scripts/aws/push_data.sh [--dry-run]

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

EXTRA=()
[ "${1:-}" = "--dry-run" ] && EXTRA+=(--dryrun)

aws s3 sync data/ "s3://$DATA_BUCKET/data/" \
  --exclude "*.DS_Store" --exclude "*__pycache__*" \
  --exclude "experiments/*" --exclude "tuning/*" \
  ${EXTRA[@]+"${EXTRA[@]}"}

echo "Pushed data/ -> s3://$DATA_BUCKET/data/"
