#!/usr/bin/env bash
# grant-agent-ddb-access.sh — Adjunta una inline policy al rol de ejecución
# del Text Agent con permisos de lectura/escritura sobre las 5 tablas
# DynamoDB del stack PharmAssist.
#
# El CLI de AgentCore crea automáticamente un rol llamado
# AmazonBedrockAgentCoreSDKRuntime-<region>-<hash>. Este script lo detecta
# leyendo el execution_role del archivo .bedrock_agentcore.yaml y le adjunta
# la policy.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
AGENTCORE_YAML="$PROJECT_ROOT/agentcore/.bedrock_agentcore.yaml"

[ -f "$ENV_FILE" ] || (echo "✗ $ENV_FILE no existe." && exit 1)
[ -f "$AGENTCORE_YAML" ] || (echo "✗ $AGENTCORE_YAML no existe. Deployá el agente primero." && exit 1)

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Extract execution role ARN from .bedrock_agentcore.yaml
ROLE_ARN=$(grep -E "^\s*execution_role:\s*arn:aws:iam::" "$AGENTCORE_YAML" | head -1 | sed -E 's/.*execution_role:\s*//' | tr -d ' ')
ROLE_NAME="${ROLE_ARN##*/}"

if [ -z "$ROLE_NAME" ]; then
  echo "✗ No se pudo extraer el rol de ejecución del agente."
  exit 1
fi

echo "→ Rol de ejecución del agente: $ROLE_NAME"

# Build policy JSON with the 5 table ARNs + GSIs
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
TABLE_ARN_BASE="arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table"

POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PharmAssistDynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "$TABLE_ARN_BASE/$MEDICOS_TABLE_NAME",
        "$TABLE_ARN_BASE/$MEDICOS_TABLE_NAME/index/*",
        "$TABLE_ARN_BASE/$VISITAS_TABLE_NAME",
        "$TABLE_ARN_BASE/$VISITAS_TABLE_NAME/index/*",
        "$TABLE_ARN_BASE/$VENTAS_TABLE_NAME",
        "$TABLE_ARN_BASE/$VENTAS_TABLE_NAME/index/*",
        "$TABLE_ARN_BASE/$PLANIFICADAS_TABLE_NAME",
        "$TABLE_ARN_BASE/$PLANIFICADAS_TABLE_NAME/index/*",
        "$TABLE_ARN_BASE/$MINUTAS_TABLE_NAME",
        "$TABLE_ARN_BASE/$MINUTAS_TABLE_NAME/index/*"
      ]
    }
  ]
}
EOF
)

echo "→ Adjuntando inline policy 'PharmAssistDynamoDBAccess' al rol..."
aws iam put-role-policy \
  --profile "$AWS_PROFILE" \
  --role-name "$ROLE_NAME" \
  --policy-name "PharmAssistDynamoDBAccess" \
  --policy-document "$POLICY"

echo "✓ Permisos DynamoDB concedidos al rol $ROLE_NAME."
