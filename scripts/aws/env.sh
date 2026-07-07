#!/usr/bin/env bash
#
# Shared environment for the scripts/aws/ helpers (docs/aws-migration-plan.md).
# Source it, don't run it:   source scripts/aws/env.sh
#
# Overridables:
#   WCPRED_AWS_PROFILE  CLI profile (default: wcpred)
#   WCPRED_AWS_REGION   region (default: eu-south-2, Madrid)
#
# Bucket names carry the account id (S3 names are global): resolved once here
# so every script agrees on them.

# Locally we authenticate through the named 'wcpred' profile. In the Fargate
# container there is no profile — credentials come from the task role — so set
# WCPRED_AWS_PROFILE="" (explicitly empty) to skip AWS_PROFILE entirely.
_profile="${WCPRED_AWS_PROFILE-wcpred}"
[ -n "$_profile" ] && export AWS_PROFILE="$_profile"
export AWS_REGION="${WCPRED_AWS_REGION:-eu-south-2}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" || {
  echo "!! AWS credentials not available for profile '$AWS_PROFILE'." >&2
  echo "   Run: aws configure --profile $AWS_PROFILE   (or configure SSO)" >&2
  return 1 2>/dev/null || exit 1
}

export DATA_BUCKET="wcpred-data-${ACCOUNT_ID}"
export SITE_BUCKET="wcpred-site-${ACCOUNT_ID}"
export LOG_GROUP="/wcpred/pipeline"
export ODDS_KEY_PARAM="/wcpred/odds-api-key"
