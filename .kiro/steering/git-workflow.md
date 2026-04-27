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

- Al editar archivos del spec (.kiro/specs/**/requirements.md, design.md, tasks.md)
- Al editar archivos de steering (.kiro/steering/*.md)
- Al editar .config.kiro
- Durante la fase de diseño o planificación (solo documentación)

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
- SÍ commitear `.env.example` actualizado (sin secrets reales)
- Stagear archivos explícitamente (`git add <files>`), evitar `git add .` en flujos productivos
- Revisar `git diff --staged` antes de commitear
- No rebasear branches que ya fueron pusheadas y compartidas
- Verificar con `git status` antes de commitear
