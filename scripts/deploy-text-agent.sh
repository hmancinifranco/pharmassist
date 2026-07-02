#!/usr/bin/env bash
# deploy-text-agent.sh — Deploy del Unified Agent a Bedrock AgentCore (VPC Mode)
#
# Requiere:
#   - .env con AWS_PROFILE, AWS_REGION, BEDROCK_MODEL_ID, DB_SECRET_ARN,
#     MINUTAS_TABLE_NAME, AGENTCORE_MEMORY_ID, y las vars de VPC
#     (correr 'make env-from-outputs' antes si acabás de deployar el stack)
#   - Docker corriendo (container deployment en VPC mode)
#   - Rol de AgentCore con permisos sobre DynamoDB, Secrets Manager, Bedrock, Aurora
#
# VPC Networking:
#   - Subnet: AGENTCORE_VPC_SUBNET (private, from ProduccionPocStack)
#   - Security Group: AGENTCORE_VPC_SG (egress → Aurora:5432, 443 → 0.0.0.0/0)
#   - Aurora SG debe aceptar ingress TCP 5432 from AGENTCORE_VPC_SG
#
# Requirements: 17.2, 17.3, 18.1, 18.2, 18.4

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

[ -f "$ENV_FILE" ] || (echo "✗ $ENV_FILE no existe." && exit 1)

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export AWS_PROFILE="${AWS_PROFILE:-default}"
AGENTCORE_REGION="${AGENTCORE_REGION:-${AWS_REGION:-us-east-1}}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-opus-4-6-v1}"

# VPC Configuration (from ProduccionPocStack / .env)
AGENTCORE_VPC_SUBNET="${AGENTCORE_VPC_SUBNET:-subnet-09cde5f1fbdc98fe7}"
AGENTCORE_VPC_SG="${AGENTCORE_VPC_SG:-sg-06a114932a8ffd8be}"

# Validate required env vars for VPC deployment
REQUIRED_VARS=(DB_SECRET_ARN MINUTAS_TABLE_NAME AGENTCORE_MEMORY_ID)
for v in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!v:-}" ]; then
    echo "✗ Variable $v vacía. Verificá .env (DB_SECRET_ARN = POC_AURORA_SECRET_ARN)."
    exit 1
  fi
done

cd "$PROJECT_ROOT/agentcore"

# Remove any previous agent yaml that may reference a different AWS account.
# The CLI will create a fresh one during 'agentcore configure'.
if [ -f .bedrock_agentcore.yaml ]; then
  CURRENT_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
  YAML_ACCOUNT=$(grep -E "^\s*account:" .bedrock_agentcore.yaml | head -1 | sed -E "s/.*account:\s*['\"]?//" | tr -d "'\"" | tr -d ' ')
  if [ -n "$YAML_ACCOUNT" ] && [ "$YAML_ACCOUNT" != "$CURRENT_ACCOUNT" ]; then
    echo "→ .bedrock_agentcore.yaml apunta a cuenta $YAML_ACCOUNT pero estás usando $CURRENT_ACCOUNT. Limpiando..."
    rm -f .bedrock_agentcore.yaml
    rm -rf .bedrock_agentcore/
  fi
fi

echo "→ Configurando Unified Agent (región $AGENTCORE_REGION, VPC mode)..."
agentcore configure -e agent.py -ni -r "$AGENTCORE_REGION"

echo "→ Deployando Unified Agent (VPC mode)..."
echo "  Subnet: $AGENTCORE_VPC_SUBNET"
echo "  Security Group: $AGENTCORE_VPC_SG"
echo "  Model: $BEDROCK_MODEL_ID"
echo ""

agentcore deploy -auc \
  --network-mode VPC \
  --subnets "$AGENTCORE_VPC_SUBNET" \
  --security-groups "$AGENTCORE_VPC_SG" \
  -env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  -env AWS_REGION="$AWS_REGION" \
  -env DB_SECRET_ARN="$DB_SECRET_ARN" \
  -env MINUTAS_TABLE_NAME="$MINUTAS_TABLE_NAME" \
  -env AGENTCORE_MEMORY_ID="$AGENTCORE_MEMORY_ID"

# Extract ARN from agentcore status
AGENT_ARN=$(agentcore status 2>/dev/null | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[a-zA-Z0-9_-]+' | head -1)

if [ -n "$AGENT_ARN" ]; then
  echo ""
  echo "✓ Unified Agent deployado (VPC mode)."
  echo "  ARN: $AGENT_ARN"
  echo ""
  # Update .env
  if grep -q "^AGENTCORE_AGENT_ARN=" "$ENV_FILE"; then
    sed -i.bak "s|^AGENTCORE_AGENT_ARN=.*|AGENTCORE_AGENT_ARN=$AGENT_ARN|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    echo "AGENTCORE_AGENT_ARN=$AGENT_ARN" >> "$ENV_FILE"
  fi
  echo "→ .env actualizado con AGENTCORE_AGENT_ARN."
else
  echo "⚠ No se pudo extraer el ARN automáticamente. Corré 'agentcore status' y copialo a .env."
fi

echo ""
echo "→ Agregando permisos al rol del agente..."
if [ -f "$PROJECT_ROOT/scripts/grant-agent-ddb-access.sh" ]; then
  bash "$PROJECT_ROOT/scripts/grant-agent-ddb-access.sh"
fi

echo ""
echo "✓ Unified Agent listo (VPC mode). Probalo con:"
echo "  make agents-invoke"
