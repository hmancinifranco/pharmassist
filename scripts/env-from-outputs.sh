#!/usr/bin/env bash
# env-from-outputs.sh — Escribe los outputs del CDK stack en .env
# Uso:
#   bash scripts/env-from-outputs.sh
#
# Requiere que el stack PharmAssistStack esté desplegado y que AWS_PROFILE
# esté configurado en .env o en el entorno.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
STACK_NAME="${CDK_STACK_NAME:-PharmAssistStack}"

[ -f "$ENV_FILE" ] || (echo "✗ $ENV_FILE no existe. Copialo desde .env.example primero." && exit 1)

# Load existing .env to get AWS_PROFILE and AWS_REGION
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

AWS_REGION="${AWS_REGION:-us-east-1}"
PROFILE_FLAG=""
[ -n "${AWS_PROFILE:-}" ] && PROFILE_FLAG="--profile $AWS_PROFILE"

echo "→ Leyendo outputs del stack $STACK_NAME (región $AWS_REGION)..."

# shellcheck disable=SC2086
OUTPUTS_JSON=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  $PROFILE_FLAG \
  --query "Stacks[0].Outputs" \
  --output json)

get() {
  echo "$OUTPUTS_JSON" | python3 -c "
import json, sys
outs = json.load(sys.stdin)
for o in outs:
    if o['OutputKey'] == '$1':
        print(o['OutputValue']); sys.exit(0)
print('', end='')
"
}

MEDICOS=$(get MedicosTableName)
VISITAS=$(get VisitasTableName)
VENTAS=$(get VentasTableName)
PLANIFICADAS=$(get PlanificadasTableName)
MINUTAS=$(get MinutasTableName)
API_URL=$(get ApiUrl)
USER_POOL=$(get UserPoolId)
CLIENT_ID=$(get UserPoolClientId)
IDENTITY_POOL=$(get IdentityPoolId)
WS_URL=$(get WebSocketUrl)
AUDIO_BUCKET=$(get AudioBucketName)

# Trim trailing slash from API URLs so curl-style concatenation works
API_URL="${API_URL%/}"
WS_URL="${WS_URL%/}"

# Update .env in-place (preserve existing values for variables not in outputs)
update_var() {
  local key="$1"
  local value="$2"
  if [ -z "$value" ]; then
    return
  fi
  if grep -q "^$key=" "$ENV_FILE"; then
    # macOS sed needs '' after -i; GNU sed doesn't but accepts it
    sed -i.bak "s|^$key=.*|$key=$value|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    echo "$key=$value" >> "$ENV_FILE"
  fi
}

update_var "MEDICOS_TABLE_NAME" "$MEDICOS"
update_var "VISITAS_TABLE_NAME" "$VISITAS"
update_var "VENTAS_TABLE_NAME" "$VENTAS"
update_var "PLANIFICADAS_TABLE_NAME" "$PLANIFICADAS"
update_var "MINUTAS_TABLE_NAME" "$MINUTAS"
update_var "API_URL" "$API_URL"
update_var "VITE_API_URL" "$API_URL"
update_var "USER_POOL_ID" "$USER_POOL"
update_var "VITE_COGNITO_USER_POOL_ID" "$USER_POOL"
update_var "VITE_COGNITO_CLIENT_ID" "$CLIENT_ID"
update_var "VITE_AWS_REGION" "$AWS_REGION"
update_var "IDENTITY_POOL_ID" "$IDENTITY_POOL"
update_var "VITE_IDENTITY_POOL_ID" "$IDENTITY_POOL"
update_var "VITE_WS_URL" "$WS_URL"
update_var "AUDIO_BUCKET_NAME" "$AUDIO_BUCKET"

echo "✓ .env actualizado con los outputs del stack."
echo ""
echo "  MEDICOS_TABLE_NAME       = $MEDICOS"
echo "  VISITAS_TABLE_NAME       = $VISITAS"
echo "  VENTAS_TABLE_NAME        = $VENTAS"
echo "  PLANIFICADAS_TABLE_NAME  = $PLANIFICADAS"
echo "  MINUTAS_TABLE_NAME       = $MINUTAS"
echo "  API_URL / VITE_API_URL   = $API_URL"
echo "  USER_POOL_ID             = $USER_POOL"
echo "  VITE_COGNITO_CLIENT_ID   = $CLIENT_ID"
echo "  IDENTITY_POOL_ID         = $IDENTITY_POOL"
echo "  VITE_WS_URL              = $WS_URL"
echo "  AUDIO_BUCKET_NAME        = $AUDIO_BUCKET"
