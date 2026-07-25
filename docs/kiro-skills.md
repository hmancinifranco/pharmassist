# Trabajar en este repo con Kiro: skills, steering, specs y hooks

Este proyecto se construyó con [Kiro](https://kiro.dev) usando desarrollo dirigido por specs. Ese andamiaje está versionado en `.kiro/` y es parte del producto: es lo que permite que alguien nuevo (o un agente) retome el trabajo sin perder el contexto acumulado.

Hay cuatro mecanismos, con propósitos distintos:

| Mecanismo | Dónde | Cuándo se carga | Para qué |
|---|---|---|---|
| **Steering** | `.kiro/steering/*.md` | Siempre (o por patrón de archivo) | Reglas y contexto que aplican a casi cualquier tarea |
| **Skills** | `.kiro/skills/<nombre>/SKILL.md` | On-demand, cuando la tarea coincide | Guías extensas de un dominio puntual |
| **Specs** | `.kiro/specs/<feature>/` | Al trabajar en esa feature | Requirements → design → tasks de cada feature |
| **Hooks** | `.kiro/hooks/*.json` | Ante un evento del IDE | Automatizaciones |

## Steering vs Skills: por qué separarlos

Un steering file marcado `inclusion: always` entra en el contexto **en cada interacción**, consuma o no. Eso es lo correcto para una regla corta y transversal ("no commitees `.env`"), y es un desperdicio para una guía de 300 líneas sobre cómo deployar (relevante en el 5% de las tareas).

Las **skills** resuelven eso con carga progresiva: al inicio solo se lee la metadata (`name` + `description`, ~100 tokens); el cuerpo completo se carga únicamente cuando el agente determina que la tarea coincide con la descripción, o cuando la invocás explícitamente. Siguen el estándar abierto [Agent Skills](https://agentskills.io/specification), así que son portables a otras herramientas.

El criterio que aplicamos para decidir dónde va cada cosa:

- **Steering** si es una regla de comportamiento corta y transversal, o contexto fundacional del proyecto que casi toda tarea necesita.
- **Skill** si es una guía extensa de un dominio acotado, que solo hace falta cuando se toca esa parte del sistema.

## Las 5 skills del repo

Cada skill vive en `.kiro/skills/<nombre>/SKILL.md` con frontmatter YAML (`name`, `description`) y el cuerpo en Markdown. La `description` es lo que determina cuándo se activa, así que está redactada para incluir los paths y los términos concretos que disparan la activación.

### `agent-development`
Cómo crear y modificar agentes Strands y sus tools.

Cubre el patrón de un tool (`@tool`, docstring descriptivo porque el LLM elige la tool leyéndolo, retorno estandarizado `{success, message, data}`, mensajes en español argentino), cuándo conviene un tool nuevo versus lógica en el system prompt, cuándo un agente nuevo versus tools adicionales, la configuración de `BedrockModel`, el wrapping con `BedrockAgentCoreApp`, y la sincronización `backend/` → `agentcore/` (son copias con imports dual-path, no symlinks: `agentcore deploy` no los resuelve).

**Se activa al** tocar `agentcore/`, `backend/agents/`, `backend/tools/` o el system prompt.

### `deployment`
Build, deploy y configuración: CDK, AgentCore, variables de entorno y permisos IAM mínimos.

Incluye el orden de deploy, la regla de que todo dato sensible va en `.env` y nunca en código, la tabla completa de variables de entorno con su origen, y los gotchas de AgentCore que cuestan horas si no se conocen: el CLI no soporta `--profile` (hay que exportar `AWS_PROFILE`), **no persiste las env vars entre deploys** (si omitís los `-env` el agente arranca con valores por defecto equivocados), y el comando es `agentcore deploy`, no `launch`.

**Se activa al** correr `cdk deploy`, `agentcore deploy`, configurar `.env` o preparar un build de producción.

### `nova-sonic-bidiagent`
La guía más específica y la que más tiempo ahorra: voz bidireccional con Nova Sonic y el `BidiAgent` de Strands sobre AgentCore.

Documenta las restricciones que descubrimos a fuerza de fallar: hay que usar **FastAPI puro y no `BedrockAgentCoreApp`** (su decorador `@app.websocket` choca con el event loop de `awscrt` y produce `InvalidStateError: CANCELLED`), hace falta **container deployment y no `direct_code_deploy`**, un agente creado con un artifact type **no se puede cambiar** a otro (hay que crear uno nuevo con otro nombre), el frontend no debe emitir eventos del protocolo Nova Sonic porque el `BidiAgent` los maneja, y el formato exacto de la presigned URL con SigV4.

**Se activa al** trabajar en el modo voz, `bidiagent/` o el frontend de voz.

### `ddgs-web-search`
Uso de DDGS (metabuscador sin API key) para buscar información pública de un médico.

Parámetros de `text()`, por qué los snippets alcanzan como input para el LLM y no conviene usar `extract()` (trae boilerplate de navegación), comparación de backends, y el patrón de fallback: si la búsqueda falla por rate-limit, el brief se genera igual con datos internos.

**Se activa al** modificar los tools de búsqueda web o de generación de briefs.

### `large-file-writes`
Regla operativa: escribir archivos grandes en chunks incrementales.

Surgió de un fallo concreto y repetido: intentar crear un `requirements.md` de ~370 líneas en una sola escritura hacía que la herramienta fallara. La regla es primer chunk de 30-50 líneas y luego appends de 50-100, verificando con `wc -l`. Incluye qué hacer cuando un chunk falla (reducir a la mitad, no reintentar igual) y la instrucción de propagarla a los subagentes.

**Se activa al** crear o reescribir specs, designs, tasks o cualquier documento de más de 150 líneas.

## Los 8 steering files

| Archivo | Inclusión | Contenido |
|---|---|---|
| `product.md` | always | Visión del producto, usuarios, flujos, reglas de negocio del dominio |
| `tech.md` | always | Stack, IDs válidos de modelos Bedrock, principios CDK, dependencias |
| `structure.md` | always | Estructura de directorios y convenciones de nombres |
| `spec-methodology.md` | always | Cómo se escribe y cierra un spec, orden de tasks, deploy obligatorio |
| `git-workflow.md` | always | Cuándo commitear, formato de mensajes, qué no se versiona |
| `security-review.md` | always | Checklist de seguridad antes de cerrar un cambio |
| `bash-heredoc-warning.md` | always | Restricciones al ejecutar bash (nada de heredocs ni `python3 -c` multilínea) |
| `documentation.md` | auto | Qué documentación actualizar según el tipo de cambio |

## Cómo usar esto

**Si vas a modificar el proyecto**, no necesitas hacer nada especial: abrí el repo con Kiro y el steering se carga solo; las skills se activan cuando la tarea las requiere. Podés invocar una skill a mano escribiendo `/` en el chat.

**Si querés entender una decisión**, el orden útil es: `docs/specs-roadmap.md` (qué se hizo y las notas de cierre de cada spec, con decisiones y gotchas) → `.kiro/specs/<feature>/` (el detalle) → `docs/decisions/` (los ADR).

**Si vas a retomar el trabajo**, `docs/session-handoff.md` tiene el estado actual y un prompt listo para copiar.

## Crear una skill nueva

```
.kiro/skills/mi-skill/
└── SKILL.md
```

```markdown
---
name: mi-skill
description: Qué hace y CUÁNDO usarla, con los paths y términos que la disparan.
---

# Mi skill

Instrucciones...
```

Dos reglas que importan más de lo que parecen:

1. **`name` debe coincidir con el nombre del directorio**, en minúsculas con guiones.
2. **La `description` es el mecanismo de activación.** "Ayuda con deploys" no sirve; "Guía de build y deploy (CDK, AgentCore, .env). Usar cuando se haga `cdk deploy`, `agentcore deploy` o se configuren variables de entorno" sí. Nombrá los archivos, comandos y situaciones concretas.

Mantené el cuerpo por debajo de las ~500 líneas; si crece más, partilo en archivos de referencia que la skill enlace, y que se cargan solo si hacen falta.

## Referencias

- [Agent Skills — especificación](https://agentskills.io/specification)
- [Kiro — Agent Skills](https://kiro.dev/docs/skills/)
- [Kiro — Steering](https://kiro.dev/docs/steering/)
