---
inclusion: always
---

# Metodología Spec-Driven Development

## Estructura de un spec

Cada feature es un spec con tres archivos en `.kiro/specs/{feature-name}/`:

| Archivo | Contenido |
|---------|-----------|
| `requirements.md` | User stories + acceptance criteria |
| `design.md` | Diseño técnico, data models, API contracts |
| `tasks.md` | Checklist ejecutable de implementación |

## Roadmap

`docs/specs-roadmap.md` trackea todos los specs con status, dependencias y fases.
Mantenerlo actualizado en todo momento.

### Cuándo actualizar el roadmap

- Al arrancar un spec: 🔴 → 🟡
- Al cerrar un spec (tasks completadas y validadas): 🟡 → 🟢
- Al pausar: → ⚪ con razón del bloqueo
- Al cancelar: → ⚫ con razón
- Al descubrir un spec nuevo: agregar fila con dependencias

## Orden de tasks — reglas clave

### Entry point CDK va temprano

Si el spec incluye una stack CDK, el entry point se crea **inmediatamente después del skeleton de la stack**. Sin entry point, `cdk synth` no puede validar checkpoints intermedios.

```
✅ Correcto:
  Task 5: Skeleton stack
  Task 6: Entry point (instancia la stack)  ← temprano
  Task 7: Recursos (synth funciona)
  Task 8: Checkpoint synth ← validación real

❌ Incorrecto:
  Task 5: Skeleton stack
  Task 6: Recursos ← sin synth posible
  Task 14: Entry point ← demasiado tarde
```

### Validar dependencias de checkpoints

Para cada task de checkpoint (`cdk synth`, tests, deploy), verificar que los prerequisitos técnicos estén en tasks anteriores. Si no, reordenar ANTES de empezar a ejecutar.

## Regla de dos intentos

Si un approach falla dos veces, parar. Diagnosticar la causa raíz y probar un enfoque fundamentalmente diferente. Documentar el cambio de estrategia en `tasks.md`.

## Pendientes detectados durante ejecución

Si un checkpoint no puede validarse por prerequisitos faltantes:
1. Adelantar el prerequisito (preferido)
2. O saltar y documentar qué queda sin validar
3. NUNCA ignorar — el checkpoint existe por una razón

## Documentos de referencia por spec

Cada spec del roadmap road-to-prod tiene documentación de soporte:
- `docs/road-to-prod.md` — arquitectura objetivo y principios de diseño
- `docs/research-external-schemas.md` — schemas de fuentes externas y queries de validación
- `docs/specs-roadmap.md` — tracker central de progreso
- `docs/session-handoff.md` — estado actual y prompt para retomar

## Deploy obligatorio antes de cerrar un spec

Si el spec incluye infraestructura CDK, AgentCore, o cualquier recurso desplegable:

1. **El deploy es una task del spec** — no se cierra un spec solo con `cdk synth`. El `cdk deploy` (o `agentcore deploy`, o lo que corresponda) es parte de la implementación.
2. **Troubleshooting incluido** — si el deploy falla, se diagnostica y resuelve antes de cerrar. No se deja al usuario resolver errores de deploy manualmente.
3. **Verificación post-deploy** — después del deploy exitoso, ejecutar al menos una validación mínima (ej: verificar que los recursos existen, ejecutar una named query, invocar un endpoint).

### Cuándo aplica

- Specs con stacks CDK → `cdk deploy` obligatorio
- Specs con agentes → `agentcore deploy` obligatorio
- Specs con Lambda/API → verificar que el endpoint responde
- Specs que solo producen código local (scripts, docs, tests) → no aplica

### En el `tasks.md`

Todo spec con infraestructura debe incluir una task explícita de deploy antes del checkpoint final:

```
- [ ] N. Deploy a AWS
  - Ejecutar `cdk deploy --app '...' --profile $AWS_PROFILE --require-approval never`
  - Verificar que el deploy completa sin errores
  - Validar que los recursos nuevos existen (ej: named queries en Athena, tablas en DynamoDB)
  - Si falla: diagnosticar, corregir, y re-intentar antes de continuar
```

---

## Session Handoff (obligatorio al cerrar un spec)

Al completar un spec, hacer dos cosas:

### 1. Notas de cierre en `docs/specs-roadmap.md`

Agregar una entrada bajo "Notas de cierre por spec" con:
- **Decisiones tomadas**: qué se eligió y por qué (alternativas descartadas)
- **Desvíos del plan**: qué cambió respecto al design original y por qué
- **Gotchas para specs siguientes**: trampas, dependencias ocultas, cosas que el próximo spec necesita saber

Estas notas son permanentes — quedan como registro histórico del proyecto.

### 2. Actualizar `docs/session-handoff.md`

Sobreescribir con:
- **Último spec completado**: qué se hizo, recursos AWS activos, archivos clave
- **Próximo spec**: scope, dependencias, qué bloquea
- **Prompt para retomar**: texto copy-paste para arrancar la próxima sesión con contexto

El handoff es efímero — se sobreescribe con cada spec nuevo. Las notas de cierre son permanentes.

### 3. Actualizar `.env` y `.env.example` con outputs del deploy

Si el spec incluyó un `cdk deploy` exitoso:
- Agregar los CloudFormation Outputs al `.env` como variables (ej: `INGESTION_STATE_MACHINE_ARN=arn:...`)
- Agregar las mismas variables con valores placeholder al `.env.example`
- Agregar las variables de input del stack si son nuevas (ej: `RDS_SECRET_ARN`, `LAKE_BUCKET_NAME`)
- Seguir la convención: sección con comentario `# === {StackName} outputs (from CDK deploy) ===`

Esto asegura que el próximo spec que dependa de estos recursos pueda referenciarlos via `.env` sin buscar en la consola de AWS.

## Persistencia de información entre specs

El `session-handoff.md` se **sobreescribe** con cada spec nuevo — es efímero por diseño. Toda información que deba sobrevivir entre specs va en las **Notas de cierre** del roadmap.

### Qué va en las Notas de cierre (permanente)

- Decisiones de diseño y por qué se tomaron
- Desvíos del plan original y la causa raíz
- Gotchas técnicos (errores de deploy, limitaciones de servicios AWS descubiertas)
- ARNs y nombres de recursos desplegados que otros specs necesitan
- Variables de entorno nuevas y sus valores/fuentes
- Workarounds aplicados (ej: "DMS requiere regional principal, no global")

### Qué va en el Session Handoff (efímero)

- Estado actual: qué está desplegado, qué falta
- Próximo spec: scope, dependencias, bloqueantes
- Prompt copy-paste para retomar con contexto

### Regla clave

Si un dato es necesario para que el **próximo spec funcione** (un ARN, un nombre de recurso, un gotcha técnico), debe estar en las Notas de cierre del roadmap. El session-handoff puede referenciarlo pero no ser la única fuente.
