#!/usr/bin/env bash
#
# Phase 0 of docs/aws-migration-plan.md: one-off account base. Idempotent —
# every resource is create-if-missing, so re-running after a partial failure
# (or to add the odds key / budget email later) is safe.
#
#   - s3://wcpred-data-<account>  private, versioned (source of truth for data/;
#     lifecycle expires the models/ posterior cache after 60 days)
#   - s3://wcpred-site-<account>  private (CloudFront OAC will read it, phase 2)
#   - SSM SecureString /wcpred/odds-api-key      (only with --odds-api-key)
#   - CloudWatch log group /wcpred/pipeline      (30-day retention)
#   - Budgets alarm at $5/month                  (only with --budget-email)
#
# Usage:
#   scripts/aws/00_setup.sh [--odds-api-key KEY] [--budget-email EMAIL]
#
# Needs a configured CLI profile (default 'wcpred'; see env.sh).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh

ODDS_API_KEY=""
BUDGET_EMAIL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --odds-api-key) ODDS_API_KEY="$2"; shift 2 ;;
    --budget-email) BUDGET_EMAIL="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

echo "Account $ACCOUNT_ID, region $AWS_REGION"

ensure_bucket() {
  local bucket="$1"
  if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    echo "bucket $bucket: already exists"
  else
    aws s3api create-bucket --bucket "$bucket" \
      --create-bucket-configuration "LocationConstraint=$AWS_REGION"
    echo "bucket $bucket: created"
  fi
  aws s3api put-public-access-block --bucket "$bucket" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
}

ensure_bucket "$DATA_BUCKET"
ensure_bucket "$SITE_BUCKET"

# Versioning + lifecycle only on the data bucket: it is the source of truth
# (S3 versioning takes over from git history as the snapshot record). The
# models/ prefix is the regenerable bayes posterior cache (~8 MB/day) — expire
# it, and prune old noncurrent versions bucket-wide.
aws s3api put-bucket-versioning --bucket "$DATA_BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket "$DATA_BUCKET" \
  --lifecycle-configuration '{
    "Rules": [
      {"ID": "expire-posterior-cache", "Status": "Enabled",
       "Filter": {"Prefix": "data/models/"},
       "Expiration": {"Days": 60}},
      {"ID": "prune-noncurrent", "Status": "Enabled",
       "Filter": {"Prefix": ""},
       "NoncurrentVersionExpiration": {"NoncurrentDays": 180}}
    ]}'
echo "bucket $DATA_BUCKET: versioning + lifecycle set"

if [ -n "$ODDS_API_KEY" ]; then
  aws ssm put-parameter --name "$ODDS_KEY_PARAM" --type SecureString \
    --value "$ODDS_API_KEY" --overwrite > /dev/null
  echo "ssm $ODDS_KEY_PARAM: set"
else
  echo "ssm $ODDS_KEY_PARAM: skipped (pass --odds-api-key to set it)"
fi

if ! aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
     --query "logGroups[?logGroupName=='$LOG_GROUP']" --output text | grep -q .; then
  aws logs create-log-group --log-group-name "$LOG_GROUP"
fi
aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 30
echo "log group $LOG_GROUP: ready (30-day retention)"

# $5/month cost alarm — the safety net for the whole plan. Notifies at 80%
# actual and 100% forecast.
if [ -n "$BUDGET_EMAIL" ]; then
  if aws budgets describe-budget --account-id "$ACCOUNT_ID" \
       --budget-name wcpred-monthly > /dev/null 2>&1; then
    echo "budget wcpred-monthly: already exists"
  else
    aws budgets create-budget --account-id "$ACCOUNT_ID" \
      --budget '{"BudgetName": "wcpred-monthly", "BudgetLimit":
                 {"Amount": "5", "Unit": "USD"},
                 "TimeUnit": "MONTHLY", "BudgetType": "COST"}' \
      --notifications-with-subscribers '[
        {"Notification": {"NotificationType": "ACTUAL",
          "ComparisonOperator": "GREATER_THAN", "Threshold": 80},
         "Subscribers": [{"SubscriptionType": "EMAIL",
          "Address": "'"$BUDGET_EMAIL"'"}]},
        {"Notification": {"NotificationType": "FORECASTED",
          "ComparisonOperator": "GREATER_THAN", "Threshold": 100},
         "Subscribers": [{"SubscriptionType": "EMAIL",
          "Address": "'"$BUDGET_EMAIL"'"}]}]'
    echo "budget wcpred-monthly: created (\$5/month, alerts to $BUDGET_EMAIL)"
  fi
else
  echo "budget: skipped (pass --budget-email to create the \$5/month alarm)"
fi

echo "Done."
