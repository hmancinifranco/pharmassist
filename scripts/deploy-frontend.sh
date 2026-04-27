#!/usr/bin/env bash
# deploy-frontend.sh — Build and deploy frontend SPA to S3 + CloudFront
#
# Usage:
#   ./scripts/deploy-frontend.sh
#
# Prerequisites:
#   - AWS CLI configured (via AWS_PROFILE in .env or aws configure)
#   - CDK stack deployed (PharmAssistStack)
#   - Node.js and npm installed
#
# The script reads S3 bucket name and CloudFront distribution ID from
# CDK stack outputs, builds the frontend, syncs to S3, and invalidates
# the CloudFront cache.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure frontend/.env exists (Vite only reads .env from its own directory)
if [ ! -e "$PROJECT_ROOT/frontend/.env" ] && [ -f "$PROJECT_ROOT/.env" ]; then
  ln -sf ../.env "$PROJECT_ROOT/frontend/.env"
fi

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${CDK_STACK_NAME:-PharmAssistStack}"
PROFILE_FLAG=""
if [ -n "${AWS_PROFILE:-}" ]; then
  PROFILE_FLAG="--profile $AWS_PROFILE"
fi

echo "==> Fetching CDK stack outputs from $STACK_NAME ..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  $PROFILE_FLAG \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  $PROFILE_FLAG \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text)

CF_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  $PROFILE_FLAG \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" \
  --output text)

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
  echo "ERROR: Could not find FrontendBucketName output in stack $STACK_NAME"
  exit 1
fi

if [ -z "$DISTRIBUTION_ID" ] || [ "$DISTRIBUTION_ID" = "None" ]; then
  echo "ERROR: Could not find CloudFrontDistributionId output in stack $STACK_NAME"
  exit 1
fi

echo "    S3 Bucket:      $BUCKET_NAME"
echo "    Distribution:   $DISTRIBUTION_ID"
echo "    Domain:         $CF_DOMAIN"

# Build frontend
echo ""
echo "==> Building frontend ..."
cd "$PROJECT_ROOT/frontend"
npm run build

# Sync to S3
echo ""
echo "==> Syncing dist/ to s3://$BUCKET_NAME ..."
aws s3 sync dist/ "s3://$BUCKET_NAME" \
  --delete \
  --region "$AWS_REGION" \
  $PROFILE_FLAG

# Invalidate CloudFront cache
echo ""
echo "==> Invalidating CloudFront cache ..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  $PROFILE_FLAG \
  --query "Invalidation.Id" \
  --output text)

echo "    Invalidation ID: $INVALIDATION_ID"
echo ""
echo "==> Deploy complete!"
echo "    Site: https://$CF_DOMAIN"
