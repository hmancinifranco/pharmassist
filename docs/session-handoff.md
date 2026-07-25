# Session Handoff — PharmAssist

## Estado actual: plataforma demo-ready + repo limpio para push

La plataforma está desplegada y validada end-to-end (login → dashboard → chat → data provenance). El repo quedó limpio y con la documentación alineada a la arquitectura real (Aurora + CodeAgent).

Cuenta: `<ACCOUNT_ID>` · Región: `us-east-1`

## Arquitectura (canónica — Opción B)

- **Capa de datos**: Amazon Aurora PostgreSQL Serverless v2 (médicos, visitas, ventas, prescripciones, cartera, ciclos), provisionada por `ProduccionPocStack` (VPC + Aurora + Lambda de seed). DynamoDB queda solo para `MinutasTable` (minutas de voz).
- **Text Agent**: CodeAgent Strands con 5 tools (`query_db` SQL contra Aurora + `buscar_info_publica`, `generar_brief`, `obtener_minutas`, `generar_mensaje_cumpleanos`). Corre en AgentCore modo VPC.
- **BidiAgent (voz)**: Nova Sonic, container deployment en AgentCore, WSS + SigV4 directo desde el browser.
- **App**: `PharmAssistStack` (Cognito, HTTP API, WebSocket API, Lambda proxy, CloudFront, MinutasTable).

## Recursos AWS activos

Los identificadores concretos son propios de cada cuenta y se resuelven en `.env` con
`make env-from-outputs`. No se versionan.

| Recurso | Variable en `.env` |
|---------|--------------------|
| Cognito User Pool | `USER_POOL_ID` / `VITE_COGNITO_USER_POOL_ID` |
| Cognito Identity Pool | `IDENTITY_POOL_ID` / `VITE_IDENTITY_POOL_ID` |
| HTTP API | `API_URL` / `VITE_API_URL` |
| WebSocket API | `VITE_WS_URL` |
| CloudFront | output `CloudFrontDomain` del stack |
| Aurora (ProduccionPocStack) | `POC_AURORA_ENDPOINT`, `DB_SECRET_ARN` |
| Text Agent (AgentCore) | `AGENTCORE_AGENT_ARN` |
| BidiAgent (AgentCore) | `BIDIAGENT_AGENT_ARN` |

## Trabajo de esta sesión

1. **Commit** de la consolidación (spec platform-consolidation) — 122 archivos.
2. **Fix Lambda bundle**: 393 MB → ~27 MB (removidas deps del agente local, import lazy).
3. **Deploy** de infra, Text Agent (VPC), BidiAgent (voz) y frontend.
4. **Fixes de integración** encontrados vía smoke test + Chrome DevTools:
   - `python-multipart` faltante en el Lambda proxy.
   - `apm_id` opcional en `ChatRequest` (se deriva del JWT).
   - `runtimeSessionId` >= 33 chars en el proxy HTTP y en el WS proxy (sanitizado + padding).
   - Refresh del token Cognito en la reconexión WebSocket (evita loop de auth con token vencido).
5. **Data provenance** ("¿De dónde salió esto?"): el toolkit captura el SQL ejecutado, `agent.py` lo adjunta al marcador, el frontend muestra SQL + tablas + operaciones + DataGrid con headers legibles.
6. **Limpieza del repo** (ver Notas de cierre en `specs-roadmap.md`).

## Próximos pasos

- **Push**: bloqueado por `git-defender` corporativo (`mwinit` / `git-defender request-repo`). Resolver manualmente.
- **Voz**: BidiAgent desplegado pero no validado en browser (requiere micrófono).
- **Fallback HTTP del brief**: consultas largas (~27s) exceden el límite de 29s del API Gateway HTTP; por WebSocket funcionan bien.

## Prompt para retomar

```
Retomo PharmAssist. Lee docs/session-handoff.md. La plataforma está desplegada
(Aurora + CodeAgent + BidiAgent) y el repo limpio. Pendiente: push (git-defender),
validar modo voz en browser.
```
