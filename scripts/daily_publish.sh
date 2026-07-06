#!/usr/bin/env bash
#
# Entrypoint of the scheduled pipeline container (docs/aws-migration-plan.md
# fase 3): the six steps of the target architecture, end to end. Reuses the
# same scripts the local workflow and POST /api/refresh already run, so the
# container is not a second code path — just an unattended driver.
#
#   1. pull data/ from S3 (the source of truth)
#   2. update_data.sh --skip-xg   (ODDS_API_KEY from SSM; xG excluded for WC2026)
#   3. generate_predictions.sh  x {odds, history} x {dc, elo, bayes}
#   4. generate_rankings.sh     x {dc, elo, bayes}
#   5. export_static.py         (inside publish_site.sh)
#   6. push data/ back to S3, sync the site, invalidate CloudFront
#
# Credentials come from the Fargate task role (env.sh skips the named profile
# when WCPRED_AWS_PROFILE is empty, which the image sets).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/aws/env.sh

ENGINES="dc,elo,bayes"

echo "=== 1/6  pull data/ from s3://$DATA_BUCKET ==="
scripts/aws/pull_data.sh --exact

echo "=== 2/6  update_data.sh --skip-xg ==="
# Decrypt the odds key into the environment (never logged). update_data reads it.
export ODDS_API_KEY="$(aws ssm get-parameter --name "$ODDS_KEY_PARAM" \
  --with-decryption --query Parameter.Value --output text)"
# A data-source failure degrades gracefully: generate with whatever we have.
scripts/update_data.sh --skip-xg || echo "!! update_data.sh reported a failure; continuing"

echo "=== 3/6  generate predictions (odds, history) x ($ENGINES) ==="
for ap in odds history; do
  scripts/generate_predictions.sh --approach "$ap" --engines "$ENGINES"
done

echo "=== 4/6  generate rankings ($ENGINES) ==="
scripts/generate_rankings.sh --engines "$ENGINES"

echo "=== 5-6/6  push data + publish site ==="
scripts/aws/push_data.sh
scripts/aws/publish_site.sh

echo "=== daily_publish done ==="
