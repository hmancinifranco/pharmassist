# Session Handoff — PharmAssist

## Último spec completado: `platform-consolidation`

### Qué se hizo

Spec de consolidación de la plataforma: migración de endpoints del dashboard a Aurora, eliminación de 4 tablas DynamoDB del CDK, mejoras UX (skeletons, dark mode, suggestion chips, WS fallback), deploy unificado con Makefile, test E2E con Playwright.

**Todas las tareas del spec están marcadas como completadas** en `.kiro/specs/platform-consolidation/tasks.md`.

### Recursos AWS activos (cuenta 709578350924, us-east-1)

| Recurso | Identificador |
|---------|---------------|
| Cognito User Pool | `us-east-1_a7uRRwASe` |
| Cognito Identity Pool | `us-east-1:9b978f20-2daa-4347-99eb-02b12d898269` |
| HTTP API Gateway | `jdae6rt2g9` → `https://jdae6rt2g9.execute-api.us-east-1.amazonaws.com` |
| WebSocket API Gateway | `70zfpnjq56` → `wss://70zfpnjq56.execute-api.us-east-1.amazonaws.com/prod` |
| Aurora PostgreSQL | `produccionpocstack-auroracluster...cluster-cklwkim2wac0.us-east-1.rds.amazonaws.com` |
| Aurora Secret | `arn:aws:secretsmanager:us-east-1:709578350924:secret:AuroraSecret41E6E877-7ZfV2rWMw2wb-xk9flh` |
| Text Agent (AgentCore) | `arn:aws:bedrock-agentcore:us-east-1:709578350924:runtime/agent-YHftSl284V` |
| AgentCore Memory | `pharmassist_memory-V5OWtfDnjg` |
| MinutasTable (DynamoDB) | `PharmAssistStack-MinutasTable843BF39F-1SYXG9Z8EFQBG` |
| Audio Bucket | `pharmassiststack-audiouploadsbucket1979170b-ceg1aos1atlh` |
| Data Lake Bucket | `datalakestack-lakebucket9cd7bbd2-yhmuiqidlita` |

### Archivos clave modificados (no commiteados)

79 archivos con cambios pendientes en branch `feat/produccion-poc-docs`. Incluyen:
- `infrastructure/stacks/pharmassist_stack.py` — fix del _LocalBundler (pip → sys.executable -m pip)
- `infrastructure/cdk.json` — app command cambiado a `bash -c 'source .venv/bin/activate && python app.py'`
- `backend/main.py` — endpoints Aurora (visits-today, birthdays, sla-alerts)
- `backend/db.py` — módulo de conexión Aurora (NUEVO)
- `frontend/src/` — skeletons, SuggestionChips, dark mode, WS fallback
- `Makefile` — deploy-all, destroy, env-from-outputs, seed-peccy
- `e2e/` — Playwright config + dashboard-flow.spec.ts (NUEVO)

---

## Problemas pendientes de integración

### 1. CDK CLI `cdk synth` no produce output (BLOQUEANTE para CI/CD)

**Síntoma**: `cdk synth` termina con exit 1 y 0 bytes de output (stdout/stderr vacíos). Pero `python app.py` genera el template correctamente (exit 0) y `cdk ls` lista los stacks bien.

**Causa probable**: Version mismatch entre CDK CLI (2.1122.0) y aws-cdk-lib (2.199.0). El CLI es mucho más nuevo que la lib. El bundling local se ejecuta bien con `python app.py` pero el CLI tiene un issue al capturar el output del subprocess.

**Workaround actual**: Deployar con `cdk deploy --app "bash -c 'source .venv/bin/activate && python app.py'"` o usar el Makefile (`make deploy-infra`) que activa el venv.

**Fix real**: Alinear versiones. Opciones:
- Downgrade CDK CLI: `npm install -g aws-cdk@2.199.0`
- Upgrade aws-cdk-lib: `pip install aws-cdk-lib==2.1122.0` (pero puede romper cosas)
- Verificar si el fix de `cdk.json` (`bash -c 'source .venv/bin/activate && python app.py'`) resuelve el issue

### 2. Lambda bundling — paquete de 393 MB (límite Lambda = 250 MB)

**Síntoma**: El `_LocalBundler` genera un paquete de ~393 MB. Lambda tiene un límite de 250 MB unzipped.

**Causa raíz**: `requirements-lambda.txt` incluye `pandas`, `strands-agents`, `strands-agents-tools`, `lxml` — todos pesados. El `_strip_bloat()` no reduce suficiente.

**Opciones de fix**:
- Usar Docker bundling (CDK lo prefiere si Docker está corriendo) — genera paquete Linux optimizado
- Lambda Layer para dependencias pesadas (pandas, lxml)
- Eliminar `pandas` del Lambda (ya no se usa — la data viene de Aurora)
- Eliminar `strands-agents*` del Lambda si el chat se proxea 100% por AgentCore

### 3. BidiAgent no desplegado

**Síntoma**: `BIDIAGENT_AGENT_ARN=` vacío en `.env`, `VITE_BIDIAGENT_AGENT_ARN=` vacío.

**Impacto**: El modo voz no funciona. El frontend no puede conectar WSS a AgentCore para Nova Sonic.

**Acción**: Ejecutar `make deploy-bidi-agent` después de verificar que el Text Agent está activo.

### 4. Git: 79 cambios sin commitear

**Síntoma**: Branch `feat/produccion-poc-docs` tiene muchos cambios acumulados de múltiples specs sin commit.

**Acción recomendada**: Hacer un commit atómico por spec o un commit grande "consolidation" que agrupe todo lo del spec `platform-consolidation`. Luego PR a main.

### 5. E2E test no verificado contra deploy real

**Síntoma**: `e2e/tests/dashboard-flow.spec.ts` existe pero nunca se corrió contra el entorno desplegado.

**Acción**: Después de resolver #3 y tener todo desplegado, correr `make e2e-test`.

### 6. Infra venv usa Python 3.14 (preview)

**Síntoma**: `.venv/bin/python3` en infrastructure es Python 3.14. Esto puede causar incompatibilidades con jsii, CDK, y wheels.

**Riesgo**: Bajo para desarrollo local, pero Docker bundling generará wheels para 3.12 (runtime Lambda). Si se depende del local bundling, puede haber mismatches.

**Acción**: Considerar recrear el venv con Python 3.12: `python3.12 -m venv .venv`

---

## Próxima sesión — Scope

**Objetivo**: Dejar la plataforma lista para demo end-to-end (login → dashboard → chat → voz).

### Tareas priorizadas

1. **Commit + push** de todos los cambios pendientes
2. **Fix CDK synth** — alinear versiones o confirmar que el workaround de cdk.json funciona con `cdk deploy`
3. **Reducir Lambda bundle size** — eliminar dependencias innecesarias de `requirements-lambda.txt`
4. **Deploy BidiAgent** — `make deploy-bidi-agent`
5. **Smoke test** — verificar manualmente: login Peccy → dashboard cards con datos → chat responde → voz funciona
6. **E2E test** — `make e2e-test` contra el entorno real

### Orden de ejecución

```
git add -A && git commit -m "feat: platform-consolidation spec completo"
# Fix lambda size
make deploy-infra          # re-deploy con Lambda más liviana
make env-from-outputs
make deploy-bidi-agent     # voice agent
make deploy-frontend       # rebuild con VITE_BIDIAGENT_AGENT_ARN
make e2e-test              # validar todo
```

---

## Prompt para retomar

```
Retomo el proyecto PharmAssist. Lee `docs/session-handoff.md` para contexto completo.

Estado: el spec `platform-consolidation` está marcado como completo en tasks.md, pero hay problemas de integración pendientes:

1. CDK CLI `cdk synth` no funciona (version mismatch CLI 2.1122 vs lib 2.199) — `python app.py` genera bien el template
2. Lambda bundle de 393 MB excede el límite de 250 MB — limpiar requirements-lambda.txt
3. BidiAgent no desplegado (BIDIAGENT_AGENT_ARN vacío)
4. 79 cambios sin commitear en branch feat/produccion-poc-docs
5. E2E test no corrido contra deploy real

Quiero dejar la plataforma lista para demo: login → dashboard → chat → voz. 
Priorizá: commit, fix lambda size, deploy todo, smoke test.
```
