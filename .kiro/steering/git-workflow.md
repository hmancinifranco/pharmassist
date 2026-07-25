---
inclusion: always
---

# Git Workflow

## Commits obligatorios

Después de completar cada tarea o grupo de tareas que resulte en un cambio funcional verificado, hacer un commit de git con un mensaje descriptivo en español.

### Cuándo hacer commit

- Al completar una tarea del spec que modifica código, infraestructura o frontend
- Después de un deploy exitoso a AWS (CDK, frontend, AgentCore)
- Antes de empezar un cambio arquitectónico grande (checkpoint de seguridad)
- Cuando el usuario confirme que un feature funciona correctamente

### Cuándo NO hacer commit

- Durante la fase de diseño o planificación (solo documentación), salvo que el usuario pida explícitamente cerrar ese avance
- Al editar `.kiro/settings/mcp.json` (contiene `AWS_PROFILE` real, ver regla de `.kiro` más abajo)
- Al editar `.kiro/agents/*.md` (no se versionan)

### Qué del `.kiro` folder SÍ se versiona

A diferencia de código de aplicación, los cambios en `.kiro/specs/**`, `.kiro/steering/*.md`, `.kiro/skills/**` y `.kiro/hooks/*.json` **sí se commitean** — son parte del historial del proyecto (metodología spec-driven, guías de contexto, skills, automatizaciones). Reglas específicas:

- `.kiro/specs/**` — commitear junto con el código que implementan, o en un commit `docs` dedicado si el spec avanza sin código todavía (requirements/design)
- `.kiro/steering/*.md` — commitear cuando se agregan, editan o eliminan reglas de steering
- `.kiro/skills/**/SKILL.md` — commitear como cualquier otro archivo de skill
- `.kiro/hooks/*.json` — commitear cuando se crean o modifican hooks
- `.kiro/settings/mcp.json` **NO se commitea** — contiene `AWS_PROFILE` real y configuración local de MCP servers. Está en `.gitignore`
- `.kiro/agents/*.md` **NO se commitean** — quedan como configuración local, están en `.gitignore`
- `.kiro/kiro-aws-blueprint/` **NO se commitea** — repo de referencia externo, está en `.gitignore`
- Revisar `git diff --staged` con especial atención cuando se stagea `.kiro/` — verificar que ningún archivo nuevo dentro de specs/steering/skills/hooks haya introducido ARNs, account IDs o profile names (aplica el checklist de `security-review.md`)

### Formato del mensaje de commit

```
<tipo>(<scope opcional>): <descripción corta en imperativo y en español>

<cuerpo opcional — explicá el por qué, no el qué>

<footer opcional — referencias a issues, breaking changes>
```

Reglas de formato:
- La primera línea (subject) no debe superar los **72 caracteres**
- Usar imperativo: "agregar", "corregir", "refactorear" (no "agregado", "corregido")
- El scope entre paréntesis es opcional pero ayuda: `(frontend)`, `(agentcore)`, `(cdk)`, `(backend)`, `(docs)`
- Agregar un cuerpo cuando el cambio no sea obvio, explicando el razonamiento
- Referenciar issues en el footer: `Refs #42`, `Closes #17`

Tipos válidos:
- `feat`: nuevo feature o funcionalidad
- `fix`: corrección de bug
- `infra`: cambio de infraestructura (CDK, deploy)
- `refactor`: refactoreo sin cambio funcional
- `perf`: mejora de performance
- `test`: agregar o corregir tests
- `docs`: documentación
- `chore`: tooling, build, dependencias
- `checkpoint`: estado estable antes de un cambio grande

### Ejemplos

```
feat(agentcore): agregar generación de mensajes de cumpleaños con IA
infra(cdk): deploy Lambda + API Gateway
fix(backend): corregir búsqueda de médico por nombre completo
refactor(frontend): extraer ChatPanel a componente independiente
docs: agregar README con arquitectura y setup
checkpoint: MVP completo antes de migración a AgentCore
```

### Reglas

- NO commitear `.env`, `.env.local`, ni `.bedrock_agentcore.yaml` (tienen ARNs con account IDs)
- NO commitear `node_modules/`, `.venv/`, `__pycache__/`, `cdk.out/`, `dist/`
- NO commitear `infrastructure/cdk.context.json` (contiene AWS account ID)
- NO commitear `.kiro/settings/mcp.json` ni `.kiro/agents/*.md` (ver detalle arriba)
- SÍ commitear `.env.example` actualizado (sin secrets reales)
- SÍ commitear `.kiro/specs/**`, `.kiro/steering/*.md`, `.kiro/skills/**`, `.kiro/hooks/*.json`
- Stagear archivos explícitamente (`git add <files>`), evitar `git add .` en flujos productivos
- Revisar `git diff --staged` antes de commitear
- No rebasear branches que ya fueron pusheadas y compartidas
- Verificar con `git status` antes de commitear
