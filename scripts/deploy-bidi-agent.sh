#!/usr/bin/env bash
# deploy-bidi-agent.sh — Deploy del BidiAgent (voz) a Bedrock AgentCore

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

# Auto-wiring: obtener TEXT_AGENT_ARN desde .env o agentcore status
TEXT_AGENT_ARN="${AGENTCORE_AGENT_ARN:-}"

if [ -z "$TEXT_AGENT_ARN" ]; then
  echo "→ AGENTCORE_AGENT_ARN vacío en .env. Intentando obtener via 'agentcore status' en agentcore/..."
  TEXT_AGENT_ARN=$(cd "$PROJECT_ROOT/agentcore" && agentcore status 2>/dev/null | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[a-zA-Z0-9_-]+' | head -1 || true)
fi

if [ -z "$TEXT_AGENT_ARN" ]; then
  echo "✗ Text Agent ARN no encontrado."
  echo "  - AGENTCORE_AGENT_ARN no está en .env"
  echo "  - 'agentcore status' en agentcore/ no retornó un ARN"
  echo "  → Deployá el Text Agent primero: make deploy-text-agent"
  exit 1
fi

echo "→ TEXT_AGENT_ARN: $TEXT_AGENT_ARN"

docker info >/dev/null 2>&1 || (echo "✗ Docker daemon no está corriendo. Abrí Docker Desktop." && exit 1)

cd "$PROJECT_ROOT/bidiagent"

# Remove any previous agent yaml that may reference a different AWS account.
if [ -f .bedrock_agentcore.yaml ]; then
  CURRENT_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
  YAML_ACCOUNT=$(grep -E "^\s*account:" .bedrock_agentcore.yaml | head -1 | sed -E "s/.*account:\s*['\"]?//" | tr -d "'\"" | tr -d ' ')
  if [ -n "$YAML_ACCOUNT" ] && [ "$YAML_ACCOUNT" != "$CURRENT_ACCOUNT" ]; then
    echo "→ .bedrock_agentcore.yaml apunta a cuenta $YAML_ACCOUNT pero estás usando $CURRENT_ACCOUNT. Limpiando..."
    rm -f .bedrock_agentcore.yaml
    rm -rf .bedrock_agentcore/
  fi
fi

echo "→ Configurando BidiAgent (container deployment, región $AGENTCORE_REGION)..."
agentcore configure -e agent.py -ni -r "$AGENTCORE_REGION" -dt container --name pharmassist_bidi

echo "→ Deployando BidiAgent..."
agentcore deploy -auc \
  -env TEXT_AGENT_ARN="$TEXT_AGENT_ARN" \
  -env AWS_REGION="$AWS_REGION" \
  -env BEDROCK_REGION="$AWS_REGION" \
  -env BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0

BIDI_ARN=$(agentcore status 2>/dev/null | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[a-zA-Z0-9_-]+' | head -1)

if [ -n "$BIDI_ARN" ]; then
  echo ""
  echo "✓ BidiAgent deployado."
  echo "  ARN: $BIDI_ARN"
  echo ""
  for key in BIDIAGENT_AGENT_ARN VITE_BIDIAGENT_AGENT_ARN; do
    if grep -q "^$key=" "$ENV_FILE"; then
      sed -i.bak "s|^$key=.*|$key=$BIDI_ARN|" "$ENV_FILE"
      rm -f "$ENV_FILE.bak"
    else
      echo "$key=$BIDI_ARN" >> "$ENV_FILE"
    fi
  done
  echo "→ .env actualizado con BIDIAGENT_AGENT_ARN y VITE_BIDIAGENT_AGENT_ARN."
else
  echo "⚠ No se pudo extraer el ARN del BidiAgent. Corré 'agentcore status' en bidiagent/ y copialo a .env."
fi
