#!/usr/bin/env bash
#
# Manually trigger one run of the daily pipeline on ECS Fargate — the everyday
# way to publish (docs/aws-migration-plan.md fase 4). martj42's results don't
# land at a fixed time, so instead of a morning cron you run this yourself once
# the day's scores are up. Same task definition, roles and failure alert as the
# (opt-in) scheduled run set up by scripts/aws/30_schedule.sh.
#
# Discovers the default-VPC network config and calls ecs:RunTask, then prints
# the commands to follow the run (it takes ~15-25 min; this returns immediately).
#
# Usage: scripts/aws/run_pipeline.sh [--wait]
#   --wait   block until the task stops (up to 45 min) and exit with its code
#
# Needs 30_schedule.sh to have run once (cluster + task definition must exist).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

WAIT=""
[ "${1:-}" = "--wait" ] && WAIT=1

CLUSTER="wcpred"
TASK_FAMILY="wcpred-pipeline"
WAIT_POLL=30        # seconds between --wait status checks
WAIT_TIMEOUT=2700   # give up waiting after 45 min (a run takes 15-25)

# Same network resolution as 30_schedule.sh: default VPC, public IP, no NAT.
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query "Vpcs[0].VpcId" --output text)"
SUBNETS="$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  Name=default-for-az,Values=true --query "Subnets[].SubnetId" --output text)"
[ -z "$SUBNETS" ] && SUBNETS="$(aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=$VPC_ID --query "Subnets[].SubnetId" --output text)"
SG_ID="$(aws ec2 describe-security-groups \
  --filters Name=vpc-id,Values=$VPC_ID Name=group-name,Values=default \
  --query "SecurityGroups[0].GroupId" --output text)"
# --output text separates ids with tabs; normalise the whitespace to commas.
SUBNETS_CSV="$(echo $SUBNETS | tr -s '[:space:]' ',')"
NET="awsvpcConfiguration={subnets=[$SUBNETS_CSV],securityGroups=[$SG_ID],assignPublicIp=ENABLED}"

echo ">>> ecs run-task ($TASK_FAMILY on $CLUSTER)"
TASK_ARN="$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$TASK_FAMILY" \
  --launch-type FARGATE --network-configuration "$NET" \
  --query "tasks[0].taskArn" --output text)"
if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
  echo "!! run-task returned no task (check failures above)." >&2
  exit 1
fi
TASK_ID="${TASK_ARN##*/}"
echo "task started: $TASK_ID"
echo
echo "Follow the logs:"
echo "  aws logs tail $LOG_GROUP --follow --since 1m"
echo "Check status:"
echo "  aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ID \\"
echo "    --query 'tasks[0].{status:lastStatus,exit:containers[0].exitCode}'"

if [ -n "$WAIT" ]; then
  echo
  echo ">>> waiting for the task to stop (~15-25 min)…"
  # Poll rather than `aws ecs wait tasks-stopped`: that waiter gives up after
  # 100 tries x 6 s = 10 min, well short of a normal run, and reports the
  # timeout as a failure even though the pipeline is still going fine.
  deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
  while :; do
    read -r state code reason < <(aws ecs describe-tasks --cluster "$CLUSTER" \
      --tasks "$TASK_ID" --query \
      "tasks[0].[lastStatus,containers[0].exitCode,stoppedReason]" --output text)
    [ "$state" = "STOPPED" ] && break
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "!! still $state after $((WAIT_TIMEOUT / 60)) min; giving up on waiting" >&2
      echo "   (the task may still be running — check it with the command above)" >&2
      exit 1
    fi
    sleep "$WAIT_POLL"
  done
  echo "task $state, exit code $code — $reason"
  [ "$code" = "0" ] || exit 1
fi
