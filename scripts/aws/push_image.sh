#!/usr/bin/env bash
#
# Phase 3 of docs/aws-migration-plan.md: build the pipeline image (ARM64) and
# push it to ECR. Idempotent — creates the repo only if missing.
#
# Built natively on Apple Silicon (no emulation) for Fargate Graviton.
#
# Usage: scripts/aws/push_image.sh [--tag TAG]   (default tag: latest)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

TAG="latest"
[ "${1:-}" = "--tag" ] && TAG="$2"

REPO="wcpred-pipeline"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="$REGISTRY/$REPO:$TAG"

if ! aws ecr describe-repositories --repository-names "$REPO" > /dev/null 2>&1; then
  aws ecr create-repository --repository-name "$REPO" \
    --image-scanning-configuration scanOnPush=true > /dev/null
  echo "ecr repo $REPO: created"
else
  echo "ecr repo $REPO: already exists"
fi

echo ">>> docker login $REGISTRY"
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"

echo ">>> docker build (linux/arm64) -> $IMAGE"
docker build --platform linux/arm64 -f Dockerfile.pipeline -t "$IMAGE" .

echo ">>> docker push $IMAGE"
docker push "$IMAGE"

echo "Pushed $IMAGE"
