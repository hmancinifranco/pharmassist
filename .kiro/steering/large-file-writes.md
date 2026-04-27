# Escritura de archivos grandes — regla obligatoria

Aprendizaje del spec #7 (`workout-logging`): al intentar crear `requirements.md` (~370 líneas) en una sola llamada a `fsWrite`, el tool falló repetidamente con `text: null` en el payload. Quedé en retry loop varias veces antes de cambiar de estrategia. Lesson: **nunca escribir archivos grandes en una sola llamada**.

## Regla

Cualquier archivo de más de ~150 líneas (specs, designs, tasks, runbooks, system prompts largos, documentación extensa) se escribe en chunks:

1. **Primer chunk con `fsWrite`**: header + overview corto, ~30-50 líneas como máximo.
2. **Chunks subsiguientes con `fsAppend`**: ~50-100 líneas cada uno, secciones coherentes (una sección o grupo de requirements por chunk).
3. **Después de cada chunk**, validar que el append funcionó leyendo el file size (`wc -l`) o releyendo la última sección.

## Casos típicos donde aplica

- `.kiro/specs/*/requirements.md` — suelen tener 300-500 líneas con N user stories × M acceptance criteria
- `.kiro/specs/*/design.md` — puede superar las 2000 líneas con mermaid, data models, API contracts, PBT properties
- `.kiro/specs/*/tasks.md` — 100-300 líneas con checklist ejecutable
- `agentcore/*/system_prompt.md` — system prompts bilingües con reglas detalladas
- `docs/session-handoff.md` — handoff entre specs con estado completo del proyecto
- Policies IAM en JSON extensas
- Scripts de smoke tests (`scripts/smoke_spec*.sh`)

## Antipatrón (evitar)

```
# ❌ MAL — un solo fsWrite con 400 líneas de markdown
fsWrite(path="requirements.md", text="""# Requirements...
...400 líneas más...
""")
```

Resultado observado: el payload sale con `text: null`, la tool rechaza con error de schema, y uno se queda retryeando en loop.

## Patrón correcto

```
# ✅ BIEN — chunks incrementales
fsWrite(path="requirements.md", text="# Requirements\n\n## Introduction\n...~30 líneas...")
fsAppend(path="requirements.md", text="\n\n### Requirement 1 — ...\n...~80 líneas...")
fsAppend(path="requirements.md", text="\n\n### Requirement 2 — ...\n...~80 líneas...")
# validar después de cada chunk crítico
executeBash(command="wc -l requirements.md")
```

## Si un chunk falla

Si un `fsWrite` o `fsAppend` falla (`text: null` u otro error de schema), **NO retryear con la misma llamada**. Cambiar de estrategia inmediatamente:

1. Reducir el tamaño del chunk a la mitad.
2. Si sigue fallando, crear el archivo vacío con `executeBash(command="touch file.md")` y append en chunks de 20-30 líneas.
3. Reportar al usuario si dos estrategias fallan — no loop infinito.

## Aplicable a subagents

Al delegar a subagents (feature-requirements-first-workflow, feature-design-first-workflow, bugfix-workflow) indicarles explícitamente en el prompt:

> "Al escribir archivos de más de 150 líneas (requirements.md, design.md, tasks.md), usar `fsWrite` con el primer chunk (~30-50 líneas) y luego `fsAppend` con chunks de ~50-100 líneas. No intentar escribir todo en una sola llamada."

Así evitamos que los subagents repitan el mismo antipatrón.

## Checkpoint de verificación

Después de crear un spec o doc grande, SIEMPRE verificar:

```bash
wc -l .kiro/specs/{feature}/requirements.md
wc -l .kiro/specs/{feature}/design.md
wc -l .kiro/specs/{feature}/tasks.md
```

Si una línea cuenta < 30 cuando esperábamos ~300, hubo un chunk fallido y el archivo quedó incompleto. Reescribir la sección faltante con append.
