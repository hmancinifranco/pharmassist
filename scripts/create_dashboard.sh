#!/usr/bin/env bash
# ==============================================================================
# create_dashboard.sh — Deploy CloudWatch Dashboard for PharmAssist GenAI Metrics
#
# Usage:
#   ./scripts/create_dashboard.sh [LOG_GROUP_NAME]
#
# If LOG_GROUP_NAME is not provided, it defaults to the AgentCore runtime log group
# pattern. Set AWS_REGION and AWS_PROFILE in .env or as environment variables.
#
# Requirements: 7.5, 15.1
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration
DASHBOARD_NAME="PharmAssist-GenAI"
REGION="${AWS_REGION:-us-east-1}"
LOG_GROUP="${1:-/aws/bedrock-agentcore/pharmassist-agent}"
TEMPLATE_FILE="$PROJECT_ROOT/infrastructure/dashboards/genai_dashboard.json"

if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "❌ Dashboard template not found: $TEMPLATE_FILE"
    exit 1
fi

echo "📊 Deploying CloudWatch Dashboard: $DASHBOARD_NAME"
echo "   Region:    $REGION"
echo "   Log Group: $LOG_GROUP"
echo ""

# Substitute placeholders in the template
DASHBOARD_BODY=$(sed \
    -e "s|\${AWS_REGION}|$REGION|g" \
    -e "s|\${LOG_GROUP_NAME}|$LOG_GROUP|g" \
    "$TEMPLATE_FILE")

# Deploy via AWS CLI
aws cloudwatch put-dashboard \
    --dashboard-name "$DASHBOARD_NAME" \
    --dashboard-body "$DASHBOARD_BODY" \
    --region "$REGION"

echo ""
echo "✅ Dashboard '$DASHBOARD_NAME' deployed successfully."
echo "   View at: https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards:name=$DASHBOARD_NAME"
