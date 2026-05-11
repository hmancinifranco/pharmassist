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
