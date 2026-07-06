#!/usr/bin/env bash
#
# Phase 4 of docs/aws-migration-plan.md: stand up the ECS Fargate infrastructure
# to run the pipeline image (fase 3), and alert by email if a run fails.
# Idempotent — every resource is create-if-missing / register-new-revision, so
# re-running after a code or image change (or to add the alert email later) is safe.
#
# martj42's results don't land at a fixed time, so a fixed morning cron would
# often run before the day's scores are in. The pipeline is therefore triggered
# MANUALLY (scripts/aws/run_pipeline.sh) once the results are up; the daily
# EventBridge schedule is created DISABLED and is opt-in via --enable.
#
# Creates / updates:
#   - IAM execution role  wcpred-pipeline-execution  (ECR pull + CloudWatch Logs)
#   - IAM task role       wcpred-pipeline-task        (S3 rw both buckets +
#                         cloudfront:CreateInvalidation + ssm:GetParameter)
#   - IAM scheduler role  wcpred-scheduler            (ecs:RunTask + iam:PassRole)
#   - ECS cluster         wcpred                      (Fargate only, no instances)
#   - Task definition     wcpred-pipeline             (2 vCPU / 8 GB, ARM64)
#   - EventBridge Scheduler  wcpred-daily             (cron, Europe/Madrid)
#   - SNS topic + rule    wcpred-alerts / wcpred-task-failed  (non-zero exit → email)
#
# Usage:
#   scripts/aws/30_schedule.sh [--alert-email EMAIL]     # set up infra + alert
#   scripts/aws/30_schedule.sh --enable [--cron 'cron(0 8 * * ? *)']  # turn the
#                                                         # daily cron on
#   scripts/aws/30_schedule.sh --disable                 # turn it back off
#
# Day to day you trigger runs by hand with scripts/aws/run_pipeline.sh once
# martj42 has the results; the cron stays off unless you --enable it.
#
# Needs a configured CLI profile (default 'wcpred'; see env.sh) and the fase 3
# image already in ECR (scripts/aws/push_image.sh).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

ALERT_EMAIL=""
CRON="cron(0 8 * * ? *)"          # 08:00 Europe/Madrid — only used if you --enable
# Off by default: martj42 update times vary, so runs are triggered by hand.
SCHEDULE_STATE="DISABLED"
while [ $# -gt 0 ]; do
  case "$1" in
    --alert-email) ALERT_EMAIL="$2"; shift 2 ;;
    --cron) CRON="$2"; shift 2 ;;
    --disable) SCHEDULE_STATE="DISABLED"; shift ;;
    --enable) SCHEDULE_STATE="ENABLED"; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

CLUSTER="wcpred"
TASK_FAMILY="wcpred-pipeline"
EXEC_ROLE="wcpred-pipeline-execution"
TASK_ROLE="wcpred-pipeline-task"
SCHED_ROLE="wcpred-scheduler"
SCHEDULE_NAME="wcpred-daily"
SNS_TOPIC="wcpred-alerts"
RULE_NAME="wcpred-task-failed"
IMAGE="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${TASK_FAMILY}:latest"

echo "Account $ACCOUNT_ID, region $AWS_REGION"

# ------------------------------------------------------------------- IAM roles
ECS_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

ensure_role() {   # ensure_role NAME TRUST_JSON
  local name="$1" trust="$2"
  if aws iam get-role --role-name "$name" > /dev/null 2>&1; then
    echo "role $name: already exists"
  else
    aws iam create-role --role-name "$name" \
      --assume-role-policy-document "$trust" > /dev/null
    echo "role $name: created"
  fi
}

ensure_role "$EXEC_ROLE" "$ECS_TRUST"
# Execution role: the standard AWS-managed policy (ECR pull + write to Logs).
aws iam attach-role-policy --role-name "$EXEC_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
EXEC_ROLE_ARN="$(aws iam get-role --role-name "$EXEC_ROLE" --query Role.Arn --output text)"

ensure_role "$TASK_ROLE" "$ECS_TRUST"
# Task role: exactly what daily_publish.sh touches at runtime — read/write both
# buckets, invalidate CloudFront, read the two SSM parameters (odds key +
# distribution id). Scope CloudFront to the one distribution when we know it.
DIST_ID="$(aws ssm get-parameter --name /wcpred/cloudfront-distribution-id \
  --query Parameter.Value --output text 2>/dev/null || true)"
if [ -n "$DIST_ID" ] && [ "$DIST_ID" != "None" ]; then
  CF_RESOURCE="\"arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DIST_ID}\""
else
  CF_RESOURCE="\"*\""   # distribution not created yet; widen until 20_site.sh runs
fi
TASK_POLICY="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "DataAndSiteBuckets", "Effect": "Allow",
     "Action": ["s3:ListBucket"],
     "Resource": ["arn:aws:s3:::${DATA_BUCKET}", "arn:aws:s3:::${SITE_BUCKET}"]},
    {"Sid": "DataAndSiteObjects", "Effect": "Allow",
     "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": ["arn:aws:s3:::${DATA_BUCKET}/*", "arn:aws:s3:::${SITE_BUCKET}/*"]},
    {"Sid": "Invalidate", "Effect": "Allow",
     "Action": ["cloudfront:CreateInvalidation"],
     "Resource": [${CF_RESOURCE}]},
    {"Sid": "ReadParameters", "Effect": "Allow",
     "Action": ["ssm:GetParameter"],
     "Resource": [
       "arn:aws:ssm:${AWS_REGION}:${ACCOUNT_ID}:parameter/wcpred/odds-api-key",
       "arn:aws:ssm:${AWS_REGION}:${ACCOUNT_ID}:parameter/wcpred/cloudfront-distribution-id"]}
  ]
}
JSON
)"
aws iam put-role-policy --role-name "$TASK_ROLE" \
  --policy-name wcpred-task --policy-document "$TASK_POLICY"
TASK_ROLE_ARN="$(aws iam get-role --role-name "$TASK_ROLE" --query Role.Arn --output text)"
echo "role $TASK_ROLE: inline policy set"

# ------------------------------------------------------------------- ECS cluster
if aws ecs describe-clusters --clusters "$CLUSTER" \
     --query "clusters[?status=='ACTIVE'].clusterName" --output text | grep -qx "$CLUSTER"; then
  echo "cluster $CLUSTER: already active"
else
  aws ecs create-cluster --cluster-name "$CLUSTER" > /dev/null
  echo "cluster $CLUSTER: created"
fi
CLUSTER_ARN="$(aws ecs describe-clusters --clusters "$CLUSTER" \
  --query "clusters[0].clusterArn" --output text)"

# --------------------------------------------------------------- task definition
# 2 vCPU / 8 GB gives headroom for the 4 MCMC chains; the whole run is ~15-25 min.
# ARM64 to match the Graviton image. A new revision is registered every run
# (cheap, and keeps the def in sync with any container tweak).
TASKDEF="$(cat <<JSON
{
  "family": "${TASK_FAMILY}",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "2048",
  "memory": "8192",
  "runtimePlatform": {"cpuArchitecture": "ARM64", "operatingSystemFamily": "LINUX"},
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [{
    "name": "pipeline",
    "image": "${IMAGE}",
    "essential": true,
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "${LOG_GROUP}",
        "awslogs-region": "${AWS_REGION}",
        "awslogs-stream-prefix": "daily"
      }
    }
  }]
}
JSON
)"
TASKDEF_ARN="$(aws ecs register-task-definition --cli-input-json "$TASKDEF" \
  --query "taskDefinition.taskDefinitionArn" --output text)"
echo "task definition: $TASKDEF_ARN"

# --------------------------------------------------------------------- networking
# Fargate needs subnets + a security group. Use the default VPC with a public IP
# so the task reaches ECR, S3, SSM, The Odds API and CloudFront without a NAT
# gateway (which would cost more than the whole pipeline).
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query "Vpcs[0].VpcId" --output text)"
if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
  echo "!! No default VPC in $AWS_REGION — create one or set subnets/SG manually." >&2
  exit 1
fi
SUBNETS="$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  Name=default-for-az,Values=true --query "Subnets[].SubnetId" --output text)"
[ -z "$SUBNETS" ] && SUBNETS="$(aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=$VPC_ID --query "Subnets[].SubnetId" --output text)"
SG_ID="$(aws ec2 describe-security-groups \
  --filters Name=vpc-id,Values=$VPC_ID Name=group-name,Values=default \
  --query "SecurityGroups[0].GroupId" --output text)"
# JSON arrays of the space-separated ids.
SUBNETS_JSON="$(printf '"%s",' $SUBNETS | sed 's/,$//')"
echo "network: vpc $VPC_ID, subnets [$SUBNETS], sg $SG_ID"

# -------------------------------------------------------------- scheduler role
SCHED_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
ensure_role "$SCHED_ROLE" "$SCHED_TRUST"
# RunTask on this family, and pass the two ECS roles to the ecs-tasks service.
SCHED_POLICY="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "RunTask", "Effect": "Allow", "Action": ["ecs:RunTask"],
     "Resource": ["arn:aws:ecs:${AWS_REGION}:${ACCOUNT_ID}:task-definition/${TASK_FAMILY}:*"],
     "Condition": {"ArnLike": {"ecs:cluster": "${CLUSTER_ARN}"}}},
    {"Sid": "PassRoles", "Effect": "Allow", "Action": ["iam:PassRole"],
     "Resource": ["${EXEC_ROLE_ARN}", "${TASK_ROLE_ARN}"],
     "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}}
  ]
}
JSON
)"
aws iam put-role-policy --role-name "$SCHED_ROLE" \
  --policy-name wcpred-scheduler --policy-document "$SCHED_POLICY"
SCHED_ROLE_ARN="$(aws iam get-role --role-name "$SCHED_ROLE" --query Role.Arn --output text)"
echo "role $SCHED_ROLE: inline policy set"

# ----------------------------------------------------------- EventBridge Scheduler
# cron in Europe/Madrid → RunTask (Fargate) with the current task definition.
SCHED_TARGET="$(cat <<JSON
{
  "Arn": "${CLUSTER_ARN}",
  "RoleArn": "${SCHED_ROLE_ARN}",
  "EcsParameters": {
    "TaskDefinitionArn": "${TASKDEF_ARN}",
    "LaunchType": "FARGATE",
    "PlatformVersion": "LATEST",
    "TaskCount": 1,
    "NetworkConfiguration": {"awsvpcConfiguration": {
      "Subnets": [${SUBNETS_JSON}],
      "SecurityGroups": ["${SG_ID}"],
      "AssignPublicIp": "ENABLED"}}
  },
  "RetryPolicy": {"MaximumRetryAttempts": 0}
}
JSON
)"
if aws scheduler get-schedule --name "$SCHEDULE_NAME" > /dev/null 2>&1; then
  aws scheduler update-schedule --name "$SCHEDULE_NAME" \
    --schedule-expression "$CRON" --schedule-expression-timezone "Europe/Madrid" \
    --flexible-time-window '{"Mode":"OFF"}' --state "$SCHEDULE_STATE" \
    --target "$SCHED_TARGET" > /dev/null
  echo "schedule $SCHEDULE_NAME: updated ($CRON, $SCHEDULE_STATE)"
else
  aws scheduler create-schedule --name "$SCHEDULE_NAME" \
    --schedule-expression "$CRON" --schedule-expression-timezone "Europe/Madrid" \
    --flexible-time-window '{"Mode":"OFF"}' --state "$SCHEDULE_STATE" \
    --target "$SCHED_TARGET" > /dev/null
  echo "schedule $SCHEDULE_NAME: created ($CRON, $SCHEDULE_STATE)"
fi

# ------------------------------------------------------- failure alert (SNS + rule)
# Without this, a broken pipeline goes unnoticed until the site looks stale.
TOPIC_ARN="$(aws sns create-topic --name "$SNS_TOPIC" --query TopicArn --output text)"
echo "sns topic $SNS_TOPIC: $TOPIC_ARN"

RULE_ARN="arn:aws:events:${AWS_REGION}:${ACCOUNT_ID}:rule/${RULE_NAME}"
# Let EventBridge publish to the topic (scoped to this one rule).
TOPIC_POLICY="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowEventBridgePublish",
    "Effect": "Allow",
    "Principal": {"Service": "events.amazonaws.com"},
    "Action": "sns:Publish",
    "Resource": "${TOPIC_ARN}",
    "Condition": {"ArnEquals": {"aws:SourceArn": "${RULE_ARN}"}}
  }]
}
JSON
)"
aws sns set-topic-attributes --topic-arn "$TOPIC_ARN" \
  --attribute-name Policy --attribute-value "$TOPIC_POLICY"

# Fire when a wcpred-pipeline task stops with a non-zero exit or fails to start.
EVENT_PATTERN="$(cat <<JSON
{
  "source": ["aws.ecs"],
  "detail-type": ["ECS Task State Change"],
  "detail": {
    "clusterArn": ["${CLUSTER_ARN}"],
    "lastStatus": ["STOPPED"],
    "group": ["family:${TASK_FAMILY}"],
    "\$or": [
      {"containers": {"exitCode": [{"anything-but": 0}]}},
      {"stopCode": ["TaskFailedToStart"]}
    ]
  }
}
JSON
)"
aws events put-rule --name "$RULE_NAME" --event-pattern "$EVENT_PATTERN" \
  --state ENABLED > /dev/null
# Input transformer: a short readable email instead of the raw 4 KB event.
aws events put-targets --rule "$RULE_NAME" --targets "$(cat <<JSON
[{
  "Id": "sns",
  "Arn": "${TOPIC_ARN}",
  "InputTransformer": {
    "InputPathsMap": {"task": "\$.detail.taskArn", "reason": "\$.detail.stoppedReason"},
    "InputTemplate": "\"wcpred daily pipeline FAILED. Task: <task>. Reason: <reason>. Check CloudWatch log group ${LOG_GROUP}.\""
  }
}]
JSON
)" > /dev/null
echo "rule $RULE_NAME: publishes failures to $SNS_TOPIC"

if [ -n "$ALERT_EMAIL" ]; then
  # Skip if this email is already subscribed (avoids a duplicate confirmation).
  existing="$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" \
    --query "Subscriptions[?Endpoint=='$ALERT_EMAIL'].SubscriptionArn | [0]" --output text)"
  if [ -n "$existing" ] && [ "$existing" != "None" ]; then
    echo "sns subscription $ALERT_EMAIL: already present ($existing)"
  else
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email \
      --notification-endpoint "$ALERT_EMAIL" > /dev/null
    echo "sns subscription $ALERT_EMAIL: pending — confirm the email AWS just sent"
  fi
else
  echo "alert email: skipped (pass --alert-email to subscribe)"
fi

echo
if [ "$SCHEDULE_STATE" = "ENABLED" ]; then
  echo "Done. Daily cron ENABLED at ${CRON} Europe/Madrid."
else
  echo "Done. Infra ready; daily cron is DISABLED (trigger runs by hand)."
fi
echo "Trigger a run once martj42 has the day's results:"
echo "  scripts/aws/run_pipeline.sh          # launches the task + prints the log tail cmd"
