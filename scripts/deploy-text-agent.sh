#!/usr/bin/env bash
# deploy-text-agent.sh — Deploy del Text Agent a Bedrock AgentCore
#
# Requiere:
#   - .env con AWS_PROFILE, AWS_REGION, BEDROCK_MODEL_ID y los *_TABLE_NAME
#     (correr 'make env-from-outputs' antes si acabás de deployar el stack)
#   - Rol de AgentCore con permisos sobre DynamoDB (se configura después con
#     scripts/grant-agent-ddb-access.sh)

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

for v in MEDICOS_TABLE_NAME VISITAS_TABLE_NAME VENTAS_TABLE_NAME PLANIFICADAS_TABLE_NAME MINUTAS_TABLE_NAME; do
  if [ -z "${!v:-}" ]; then
    echo "✗ Variable $v vacía. Corré 'make env-from-outputs' primero."
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

echo "→ Configurando Text Agent (región $AGENTCORE_REGION)..."
# --name "pharmassist_text" would clash with existing legacy "agent" deploys.
# We keep the default "agent" name so the CLI reuses the runtime if it exists.
agentcore configure -e agent.py -ni -r "$AGENTCORE_REGION"

echo "→ Deployando Text Agent..."
agentcore deploy -auc \
  -env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  -env AWS_REGION="$AWS_REGION" \
  -env MEDICOS_TABLE_NAME="$MEDICOS_TABLE_NAME" \
  -env VISITAS_TABLE_NAME="$VISITAS_TABLE_NAME" \
  -env VENTAS_TABLE_NAME="$VENTAS_TABLE_NAME" \
  -env PLANIFICADAS_TABLE_NAME="$PLANIFICADAS_TABLE_NAME" \
  -env MINUTAS_TABLE_NAME="$MINUTAS_TABLE_NAME"

# Extract ARN from agentcore status
AGENT_ARN=$(agentcore status 2>/dev/null | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[a-zA-Z0-9_-]+' | head -1)

if [ -n "$AGENT_ARN" ]; then
  echo ""
  echo "✓ Text Agent deployado."
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
echo "→ Agregando permisos DynamoDB al rol del agente..."
bash "$PROJECT_ROOT/scripts/grant-agent-ddb-access.sh"

echo ""
echo "✓ Text Agent listo. Probalo con:"
echo "  make agents-invoke"
