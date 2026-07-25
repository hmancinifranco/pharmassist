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
  --output json 2>/dev/null || echo "")

get() {
  [ -n "$OUTPUTS_JSON" ] && [ "$OUTPUTS_JSON" != "null" ] || { echo -n ""; return; }
  echo "$OUTPUTS_JSON" | python3 -c "
import json, sys
outs = json.load(sys.stdin)
for o in outs:
    if o['OutputKey'] == '$1':
        print(o['OutputValue']); sys.exit(0)
print('', end='')
"
}

if [ -z "$OUTPUTS_JSON" ] || [ "$OUTPUTS_JSON" = "null" ]; then
  echo "  → $STACK_NAME no encontrado todavía (se poblará al deployarlo)"
fi

MINUTAS=$(get MinutasTableName)
API_URL=$(get ApiUrl)
USER_POOL=$(get UserPoolId)
CLIENT_ID=$(get UserPoolClientId)
IDENTITY_POOL=$(get IdentityPoolId)
WS_URL=$(get WebSocketUrl)
AUDIO_BUCKET=$(get AudioBucketName)
CF_DOMAIN=$(get CloudFrontDomain)

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
update_var "CLOUDFRONT_DOMAIN" "$CF_DOMAIN"
[ -n "$CF_DOMAIN" ] && update_var "CLOUDFRONT_URL" "https://$CF_DOMAIN"

# --- Capa de datos: ProduccionPocStack (Aurora). Tolerante si aún no existe. ---
POC_STACK="${POC_STACK_NAME:-ProduccionPocStack}"
# shellcheck disable=SC2086
POC_JSON=$(aws cloudformation describe-stacks \
  --stack-name "$POC_STACK" \
  --region "$AWS_REGION" \
  $PROFILE_FLAG \
  --query "Stacks[0].Outputs" \
  --output json 2>/dev/null || echo "")

if [ -n "$POC_JSON" ] && [ "$POC_JSON" != "null" ]; then
  pget() {
    echo "$POC_JSON" | python3 -c "
import json, sys
for o in json.load(sys.stdin):
    if o['OutputKey'] == '$1':
        print(o['OutputValue']); sys.exit(0)
print('', end='')
"
  }
  POC_ENDPOINT=$(pget AuroraEndpoint)
  POC_SECRET=$(pget AuroraSecretArn)
  POC_VPC=$(pget VpcId)
  POC_SEED=$(pget SeedLambdaArn)
  AGENT_SG=$(pget AgentSecurityGroupId)
  AGENT_SUBNETS=$(pget PrivateSubnetIds)

  update_var "POC_AURORA_ENDPOINT" "$POC_ENDPOINT"
  update_var "POC_AURORA_SECRET_ARN" "$POC_SECRET"
  update_var "DB_SECRET_ARN" "$POC_SECRET"
  update_var "POC_VPC_ID" "$POC_VPC"
  update_var "POC_SEED_LAMBDA_ARN" "$POC_SEED"

  # Networking para AgentCore en modo VPC. Si el stack todavía no expone estos
  # outputs (deploy previo a su incorporación), se derivan de la VPC.
  if [ -z "$AGENT_SG" ] && [ -n "$POC_VPC" ]; then
    # shellcheck disable=SC2086
    AGENT_SG=$(aws ec2 describe-security-groups \
      --filters "Name=vpc-id,Values=$POC_VPC" "Name=description,Values=Security group for Lambda functions accessing Aurora" \
      --region "$AWS_REGION" $PROFILE_FLAG \
      --query "SecurityGroups[0].GroupId" --output text 2>/dev/null | grep -v '^None$' || echo "")
  fi
  if [ -z "$AGENT_SUBNETS" ] && [ -n "$POC_VPC" ]; then
    # shellcheck disable=SC2086
    AGENT_SUBNETS=$(aws ec2 describe-subnets \
      --filters "Name=vpc-id,Values=$POC_VPC" "Name=tag:aws-cdk:subnet-type,Values=Private" \
      --region "$AWS_REGION" $PROFILE_FLAG \
      --query "Subnets[].SubnetId" --output text 2>/dev/null | tr '\t' ',' || echo "")
  fi

  # agentcore espera UNA subnet: tomamos la primera de la lista.
  AGENT_SUBNET=$(echo "$AGENT_SUBNETS" | cut -d, -f1)

  [ -n "$AGENT_SG" ]     && update_var "AGENTCORE_VPC_SG" "$AGENT_SG"
  [ -n "$AGENT_SUBNET" ] && update_var "AGENTCORE_VPC_SUBNET" "$AGENT_SUBNET"

  echo "  → ProduccionPocStack (Aurora) detectado: outputs POC_* escritos a .env"
  echo "     AGENTCORE_VPC_SG     = ${AGENT_SG:-(no resuelto)}"
  echo "     AGENTCORE_VPC_SUBNET = ${AGENT_SUBNET:-(no resuelto)}"
else
  echo "  → ProduccionPocStack no encontrado (deployá la capa de datos con 'make deploy-data-layer')"
fi

echo "✓ .env actualizado con los outputs del stack."
echo ""
echo "  MINUTAS_TABLE_NAME       = $MINUTAS"
echo "  API_URL / VITE_API_URL   = $API_URL"
echo "  USER_POOL_ID             = $USER_POOL"
echo "  VITE_COGNITO_CLIENT_ID   = $CLIENT_ID"
echo "  IDENTITY_POOL_ID         = $IDENTITY_POOL"
echo "  VITE_WS_URL              = $WS_URL"
echo "  AUDIO_BUCKET_NAME        = $AUDIO_BUCKET"
echo "  CLOUDFRONT_DOMAIN        = $CF_DOMAIN"
