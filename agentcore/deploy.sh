#!/usr/bin/env bash
# ===========================================================================
# agentcore/deploy.sh — Deploy del Unified Agent a Bedrock AgentCore (VPC Mode)
#
# Este script configura y despliega el agente unificado con:
#   - VPC mode (private subnet ENI) para acceso directo a Aurora PostgreSQL
#   - Security group con egress a Aurora RDS:5432
#   - Idle session timeout de 900 segundos (15 minutos)
#   - Todas las variables de entorno requeridas
#
# Prerequisitos:
#   - .env con AWS_PROFILE, AWS_REGION, BEDROCK_MODEL_ID, DB_SECRET_ARN,
#     MINUTAS_TABLE_NAME, AGENTCORE_MEMORY_ID, y las vars de VPC
#   - Docker corriendo (para container deployment)
#   - `agentcore` CLI instalado (pip install bedrock-agentcore-starter-toolkit)
#   - Aurora security group acepta ingress desde AgentCore SG en port 5432
#
# Networking (VPC del POC ProduccionPocStack):
#   - VPC: vpc-09a9d2d63c4486091
#   - Security Group: sg-06a114932a8ffd8be (egress → Aurora RDS:5432, 443 → 0.0.0.0/0)
#   - Subnet (private): subnet-09cde5f1fbdc98fe7
#
# Security Group Rules requeridas:
#   ┌─────────────────────────────────────────────────────────────────┐
#   │ AgentCore SG (sg-06a114932a8ffd8be):                           │
#   │   Egress:                                                       │
#   │     - TCP 5432 → Aurora SG (acceso a Aurora PostgreSQL)         │
#   │     - TCP 443  → 0.0.0.0/0 (Bedrock, DynamoDB, Secrets Mgr,   │
#   │                              CloudWatch via NAT Gateway)        │
#   │                                                                 │
#   │ Aurora SG (del ProduccionPocStack):                             │
#   │   Ingress:                                                      │
#   │     - TCP 5432 from AgentCore SG (sg-06a114932a8ffd8be)        │
#   └─────────────────────────────────────────────────────────────────┘
#
# Requirements: 17.2, 17.3, 18.1, 18.2, 18.4
# ===========================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# --- Load environment ---
[ -f "$ENV_FILE" ] || { echo "✗ $ENV_FILE no existe. Copiá .env.example y completá los valores."; exit 1; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export AWS_PROFILE="${AWS_PROFILE:-default}"

# --- Configuration ---
AGENTCORE_REGION="${AGENTCORE_REGION:-${AWS_REGION:-us-east-1}}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-20250514-v1:0}"

# VPC Configuration (from ProduccionPocStack)
AGENTCORE_VPC_SUBNET="${AGENTCORE_VPC_SUBNET:-subnet-09cde5f1fbdc98fe7}"
AGENTCORE_VPC_SG="${AGENTCORE_VPC_SG:-sg-06a114932a8ffd8be}"

# Idle session timeout: 900 seconds (15 minutes) per Requirement 18.4
IDLE_SESSION_TIMEOUT=900

# --- Validate required env vars ---
REQUIRED_VARS=(
  BEDROCK_MODEL_ID
  AWS_REGION
  DB_SECRET_ARN
  MINUTAS_TABLE_NAME
  AGENTCORE_MEMORY_ID
)

echo "→ Validando variables de entorno requeridas..."
for v in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!v:-}" ]; then
    echo "✗ Variable $v está vacía o no definida en .env"
    echo "  Para DB_SECRET_ARN usar el valor de POC_AURORA_SECRET_ARN del .env"
    echo "  Para AGENTCORE_MEMORY_ID usar el valor creado con agentcore memory"
    exit 1
  fi
done
echo "  ✓ Todas las variables requeridas presentes."

# --- Change to agentcore directory ---
cd "$PROJECT_ROOT/agentcore"

# --- Clean stale config if account mismatch ---
if [ -f .bedrock_agentcore.yaml ]; then
  CURRENT_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
  YAML_ACCOUNT=$(grep -E "^\s*account:" .bedrock_agentcore.yaml | head -1 | sed -E "s/.*account:\s*['\"]?//" | tr -d "'\"" | tr -d ' ')
  if [ -n "$YAML_ACCOUNT" ] && [ "$YAML_ACCOUNT" != "$CURRENT_ACCOUNT" ]; then
    echo "→ Config apunta a cuenta $YAML_ACCOUNT pero estás en $CURRENT_ACCOUNT. Limpiando..."
    rm -f .bedrock_agentcore.yaml
    rm -rf .bedrock_agentcore/
  fi
fi

# --- Configure AgentCore ---
echo ""
echo "→ Configurando Unified Agent (región: $AGENTCORE_REGION, VPC mode)..."
agentcore configure \
  -e agent.py \
  -ni \
  -r "$AGENTCORE_REGION" \
  --vpc \
  --subnets "$AGENTCORE_VPC_SUBNET" \
  --security-groups "$AGENTCORE_VPC_SG" \
  --idle-timeout "$IDLE_SESSION_TIMEOUT"

# --- Deploy with VPC mode and all required env vars ---
echo ""
echo "→ Deployando Unified Agent en VPC mode..."
echo "  Subnet: $AGENTCORE_VPC_SUBNET"
echo "  Security Group: $AGENTCORE_VPC_SG"
echo "  Idle timeout: ${IDLE_SESSION_TIMEOUT}s"
echo "  Model: $BEDROCK_MODEL_ID"
echo ""

agentcore deploy -auc \
  -env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  -env AWS_REGION="$AWS_REGION" \
  -env DB_SECRET_ARN="$DB_SECRET_ARN" \
  -env MINUTAS_TABLE_NAME="$MINUTAS_TABLE_NAME" \
  -env AGENTCORE_MEMORY_ID="$AGENTCORE_MEMORY_ID"

# --- Extract and save ARN ---
echo ""
echo "→ Extrayendo ARN del agente deployado..."
AGENT_ARN=$(agentcore status 2>/dev/null | grep -oE 'arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/[a-zA-Z0-9_-]+' | head -1)

if [ -n "$AGENT_ARN" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  ✓ Unified Agent deployado exitosamente (VPC mode)          ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  ARN: $AGENT_ARN"
  echo "  Region: $AGENTCORE_REGION"
  echo "  Network: VPC (private subnet)"
  echo "  Idle timeout: ${IDLE_SESSION_TIMEOUT}s"
  echo ""

  # Update .env with new ARN
  if grep -q "^AGENTCORE_AGENT_ARN=" "$ENV_FILE"; then
    sed -i.bak "s|^AGENTCORE_AGENT_ARN=.*|AGENTCORE_AGENT_ARN=$AGENT_ARN|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    echo "AGENTCORE_AGENT_ARN=$AGENT_ARN" >> "$ENV_FILE"
  fi
  echo "  → .env actualizado con AGENTCORE_AGENT_ARN."
else
  echo ""
  echo "⚠ No se pudo extraer el ARN. Ejecutá 'agentcore status' y actualizá .env manualmente."
fi

# --- Grant IAM permissions ---
echo ""
echo "→ Verificando permisos IAM del rol de ejecución..."
if [ -f "$PROJECT_ROOT/scripts/grant-agent-ddb-access.sh" ]; then
  bash "$PROJECT_ROOT/scripts/grant-agent-ddb-access.sh"
fi

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Deploy completado. Próximos pasos:"
echo ""
echo "  1. Verificar que Aurora SG acepta ingress desde $AGENTCORE_VPC_SG:5432"
echo "  2. Testear con:"
echo "     cd agentcore && agentcore invoke '{\"prompt\": \"Hola\", \"apm_id\": \"Peccy\"}'"
echo ""
echo "  3. Si funciona, actualizar Lambda Proxy con el nuevo ARN:"
echo "     make deploy-infra"
echo "═══════════════════════════════════════════════════════════════════"
