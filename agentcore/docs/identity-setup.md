# AgentCore Identity — Cognito JWT Configuration

## Overview

Este documento describe la configuración de AgentCore Identity para validar tokens JWT emitidos por el Cognito User Pool existente de PharmAssist. La integración permite que AgentCore verifique la identidad del APM antes de procesar requests.

## Arquitectura de Autenticación

```
Browser (APM)
    │
    ├─► Cognito Login → obtiene ID Token (JWT)
    │
    ├─► WebSocket $connect (token como query param)
    │         │
    │         ▼
    │   Lambda Proxy (ws_handler.py)
    │         │
    │         ├─► Valida JWT via JWKS (kid, iss, exp)
    │         ├─► Extrae custom:apm_id del token
    │         └─► Pasa apm_id + session_id al payload del agent
    │
    └─► AgentCore Runtime (CUSTOM_JWT authorizer opcional)
              │
              └─► Verifica JWT via OIDC Discovery URL de Cognito
```

## Cognito User Pool — Datos de Configuración

| Campo | Valor | Fuente |
|-------|-------|--------|
| User Pool Name | `PharmAssistUsers` | CDK PharmAssistStack |
| User Pool ID | `${VITE_COGNITO_USER_POOL_ID}` | `.env` (from CDK output) |
| App Client ID | `${VITE_COGNITO_CLIENT_ID}` | `.env` (from CDK output) |
| Region | `us-east-1` | `.env` AWS_REGION |
| Custom Attribute | `custom:apm_id` | CDK UserPool config |

## OIDC Discovery URL

La URL de descubrimiento OIDC de Cognito sigue el formato estándar:

```
https://cognito-idp.{region}.amazonaws.com/{userPoolId}/.well-known/openid-configuration
```

Para este proyecto:

```
https://cognito-idp.us-east-1.amazonaws.com/${VITE_COGNITO_USER_POOL_ID}/.well-known/openid-configuration
```

Esta URL expone:
- `issuer`: `https://cognito-idp.us-east-1.amazonaws.com/{userPoolId}`
- `jwks_uri`: `https://cognito-idp.us-east-1.amazonaws.com/{userPoolId}/.well-known/jwks.json`
- `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`

## Configuración de AgentCore Identity — CUSTOM_JWT Authorizer

Si se configura el AgentCore Runtime o Gateway con un authorizer CUSTOM_JWT apuntando a Cognito:

### Parámetros de Configuración

```json
{
  "authorizer_type": "CUSTOM_JWT",
  "authorizer_configuration": {
    "customJWTAuthorizer": {
      "discoveryUrl": "https://cognito-idp.us-east-1.amazonaws.com/${USER_POOL_ID}/.well-known/openid-configuration",
      "allowedClients": ["${APP_CLIENT_ID}"],
      "allowedAudience": ["${APP_CLIENT_ID}"]
    }
  }
}
```

### Campos Detallados

| Campo | Descripción | Valor |
|-------|-------------|-------|
| `discoveryUrl` | OIDC Discovery endpoint del Cognito User Pool | `https://cognito-idp.us-east-1.amazonaws.com/{USER_POOL_ID}/.well-known/openid-configuration` |
| `allowedClients` | App Client IDs que pueden emitir tokens válidos | `[VITE_COGNITO_CLIENT_ID]` |
| `allowedAudience` | Audience esperada en el token (coincide con client ID en Cognito) | `[VITE_COGNITO_CLIENT_ID]` |

### CLI: Configurar CUSTOM_JWT en un Gateway AgentCore

```bash
# Si se usa AgentCore Gateway (MCP protocol):
# El gateway se crea con authorizer_type CUSTOM_JWT

# Nota: Para el MVP actual, la Lambda Proxy ya valida JWTs directamente.
# CUSTOM_JWT en AgentCore es un layer adicional de seguridad para proteger
# el runtime de invocaciones no autorizadas.
```

## Estado Actual (MVP)

### Validación JWT — Lambda Proxy (implementada)

El archivo `backend/ws_proxy/ws_handler.py` ya implementa validación JWT completa:

1. **En `$connect`**: Valida el token JWT del query param
   - Verifica issuer (`iss`) contra el User Pool ID
   - Verifica expiración (`exp`)
   - Verifica `token_use` es `id` o `access`
   - Verifica `kid` existe en JWKS del pool
   
2. **En `sendMessage`**: Extrae `custom:apm_id` del payload del cliente
   - Fallback: re-valida token del query param si `apm_id` no viene en payload

### Variables de Entorno Requeridas en Lambda Proxy

```bash
USER_POOL_ID=${VITE_COGNITO_USER_POOL_ID}    # Cognito User Pool ID
USER_POOL_REGION=us-east-1                     # Region del User Pool
AGENTCORE_AGENT_ARN=${AGENTCORE_AGENT_ARN}     # ARN del runtime unificado
AGENTCORE_REGION=us-east-1                     # Region de AgentCore
```

## Configuración Opcional: Resource Policy en AgentCore Runtime

Para restringir quién puede invocar el AgentCore Runtime (además de la validación JWT en la Lambda):

### Via CLI

```bash
# Restringir invocación solo al rol de la Lambda Proxy
aws bedrock-agentcore put-resource-policy \
  --resource-arn "arn:aws:bedrock-agentcore:us-east-1:${AWS_ACCOUNT_ID}:runtime/${AGENT_NAME}" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/WsProxyLambdaRole"
        },
        "Action": "bedrock-agentcore:InvokeAgentRuntime",
        "Resource": "*"
      }
    ]
  }'
```

### Beneficio

Con un resource policy, incluso si alguien obtiene las credenciales del rol de la Lambda, solo ese rol específico puede invocar el runtime. Esto complementa la validación JWT del Cognito token.

## Claims JWT Relevantes

El ID Token de Cognito contiene estos claims usados por el sistema:

| Claim | Uso | Ejemplo |
|-------|-----|---------|
| `sub` | UUID único del usuario | `a1b2c3d4-...` |
| `custom:apm_id` | Identificador del APM (scoping de datos) | `"Demo APM"` |
| `email` | Email del usuario | `demo@example.com` |
| `iss` | Issuer (para validación) | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXX` |
| `exp` | Expiración del token (Unix timestamp) | `1700000000` |
| `token_use` | Tipo de token | `id` |
| `aud` | Audience (App Client ID) | `abc123def456` |

## Flujo de Datos de Identidad

1. APM se loguea via Cognito → recibe ID Token JWT
2. Frontend envía token como query param en WebSocket `$connect`
3. Lambda Proxy valida JWT (issuer, exp, kid en JWKS)
4. En `sendMessage`, el frontend envía `apm_id` en el payload
5. Lambda Proxy pasa `apm_id` al AgentCore Runtime en el invoke payload
6. El Agent inyecta `apm_id` en el system prompt para scoping SQL
7. Todas las queries filtran por `id_apm = '{apm_id}'`

## Próximos Pasos (Post-MVP)

- [ ] Configurar CUSTOM_JWT authorizer directamente en el AgentCore Runtime/Gateway para double validation
- [ ] Implementar token refresh automático en el frontend (antes de expiración)
- [ ] Agregar resource policy restrictiva al runtime para defense-in-depth
- [ ] Considerar migrar a AgentCore Gateway con authorizer nativo (elimina Lambda Proxy manual)
