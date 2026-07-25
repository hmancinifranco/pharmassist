---
name: agent-development
description: Guía para crear y modificar agentes Strands y tools en PharmAssist (backend/agents, backend/tools, agentcore). Usar cuando se agregue o edite un agente, un tool, el system prompt, o se haga deploy de agentcore/agent.py con BedrockAgentCoreApp.
metadata:
  category: development
  complexity: intermediate
---

# Desarrollo de Agentes y Tools (Strands SDK + AgentCore)

## Arquitectura de Agentes

PharmAssist usa Strands Agents SDK con Amazon Bedrock (Claude) para crear agentes que consultan datos de la farmacéutica y responden consultas del APM.

### Tools del CodeAgent

El core es un **CodeAgent** de Strands con 5 tools. El LLM decide qué tool usar según la consulta del APM.

| Tool | Responsabilidad |
|------|-----------------|
| `query_db` | Ejecuta SQL read-only generado por el LLM contra Aurora PostgreSQL (médicos, visitas, ventas, prescripciones, cartera, ciclos); timeout 5s |
| `buscar_info_publica` | Búsqueda de información pública del médico |
| `generar_brief` | Arma el brief de preparación de visita |
| `obtener_minutas` | Recupera minutas de voz desde `MinutasTable` (DynamoDB) |
| `generar_mensaje_cumpleanos` | Genera un mensaje de cumpleaños para un médico |

## Creación de Agentes con Strands

### Patrón básico
```python
from strands import Agent
from strands.models import BedrockModel
import os

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    temperature=0.3,      # bajo para respuestas factuales
    max_tokens=4096,
)

agent = Agent(
    model=model,
    tools=[tool1, tool2, tool3],
    system_prompt="""Sos un asistente para visitadores médicos de una farmacéutica argentina.
    Respondés en español argentino. Usás datos reales del CRM, visitas y ventas.
    Siempre citás datos concretos (fechas, nombres, números)."""
)

response = agent("¿Cuándo fue la última visita al Dr. Herrera?")
```

### Configuración del modelo
- `temperature=0.1-0.3` para consultas factuales (datos, fechas, KPIs)
- `temperature=0.5-0.7` para generación de talking points y sugerencias
- `max_tokens=4096` mínimo (los agentes necesitan espacio para tool calls)
- SIEMPRE leer `BEDROCK_MODEL_ID` de variable de entorno, nunca hardcodear
- Habilitar acceso al modelo en Bedrock Console antes de usar

## Estructura de Tools

Los tools son funciones Python decoradas con `@tool` de Strands SDK.

### Patrón para crear un nuevo Tool

```python
import logging
import os
from typing import Dict, Any
from strands import tool

logger = logging.getLogger(__name__)

@tool
def buscar_medicos_por_zona(zona: str) -> Dict[str, Any]:
    """
    Busca todos los médicos asignados a una zona específica.
    Usar cuando el APM pregunta por médicos de una zona o necesita
    planificar visitas en un área geográfica.

    Args:
        zona: Nombre de la zona (ej: "Belgrano-R", "Palermo-Norte")

    Returns:
        {success: bool, message: str, data: lista de médicos}
    """
    try:
        # Lógica de consulta (SQL a Aurora PostgreSQL)
        resultados = []  # ... consulta real
        return {
            'success': True,
            'message': f'✅ Se encontraron {len(resultados)} médicos en {zona}',
            'data': resultados
        }
    except Exception as e:
        logger.error(f"Error buscando médicos en zona {zona}: {e}")
        return {
            'success': False,
            'message': f'❌ Error al buscar médicos en {zona}'
        }
```

### Reglas de Tools
- Retorno SIEMPRE `{success: bool, message: str, ...}` — el `message` es lo que el LLM usa
- Mensajes de error empiezan con ❌, éxito con ✅
- Español argentino en mensajes al usuario
- Logging con `logger.info/error`, nunca `print()`
- Docstrings descriptivos: el LLM decide qué tool usar basándose en el docstring
- Parámetros tipados con type hints
- Nombres en `snake_case` descriptivo (ej: `buscar_medicos_por_zona`, no `buscar`)
- Variables de entorno para credenciales de Aurora (`DB_SECRET_ARN`) y la tabla de minutas (`MINUTAS_TABLE_NAME`), nunca hardcodeadas
- Usar `os.environ.get(...)` para el secret de Aurora y el nombre de la tabla de minutas

### Cómo agregar un nuevo Tool

1. Crear o editar el archivo en `backend/tools/` (ej: `medicos_tools.py`)
2. Seguir el patrón: `@tool`, docstring descriptivo, try/except, retorno estandarizado
3. Registrar el tool en el agente correspondiente (`tools=[...]`)
4. Actualizar el system prompt del agente si cambia el comportamiento esperado
5. Si el tool consulta datos de negocio, usar SQL a Aurora (patrón `query_db`); para minutas usar boto3 con `MINUTAS_TABLE_NAME` desde env var
6. Testear el tool de forma aislada antes de integrarlo al agente

## Cuándo crear un Tool vs. lógica en el agente

| Situación | Solución |
|-----------|----------|
| Consultar datos (SQL a Aurora, DynamoDB de minutas) | Tool |
| Cálculo complejo (KPIs, rankings) | Tool |
| Formatear una respuesta | System prompt del agente |
| Decidir qué hacer con la consulta | System prompt del agente |
| Llamar a un servicio externo (AWS) | Tool |
| Combinar resultados de varios tools | Agente coordinador |

## Cuándo crear un Agente nuevo vs. agregar Tools

| Situación | Solución |
|-----------|----------|
| Nuevo dominio de datos (ej: stock de muestras) | Nuevo agente |
| Nueva consulta sobre datos existentes | Nuevo tool en agente existente |
| Lógica que combina múltiples dominios | Coordinador orquesta |
| System prompt > 2000 palabras | Dividir en agentes especializados |

## Deploy con AgentCore

### Wrapping del agente
Para deploy en AgentCore, el agente se wrappea en `agentcore/agent.py`:

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
import os

# Imports de tools (dual-path para local y AgentCore)
try:
    from agentcore.tools.query_db import query_db
except ImportError:
    from backend.tools.query_db import query_db

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(model=model, tools=[query_db], system_prompt="...")

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload, context):
    user_message = payload.get("prompt", "Hola")
    response = agent(user_message)
    return {"result": str(response)}

if __name__ == "__main__":
    app.run()
```

### requirements.txt de AgentCore
```
bedrock-agentcore
strands-agents
strands-agents-tools
boto3
pandas
```

### Deploy
```bash
source .env
cd agentcore

# Configurar
agentcore configure -e agent.py -ni -r $AGENTCORE_REGION

# Deploy (SIEMPRE incluir -env con el secret de Aurora y la tabla de minutas del CDK output)
agentcore deploy -auc \
  -env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID \
  -env AWS_REGION=$AWS_REGION \
  -env DB_SECRET_ARN=$DB_SECRET_ARN \
  -env MINUTAS_TABLE_NAME=$MINUTAS_TABLE_NAME

# Test
agentcore invoke '{"prompt": "¿Qué médicos tengo en Belgrano?", "apm_id": "Demo APM"}'
```

### Notas críticas de AgentCore
- `agentcore` CLI NO soporta `--profile`. Usar `export AWS_PROFILE=...`
- `agentcore` CLI NO persiste env vars entre deploys. SIEMPRE incluir `-env`
- Omitir `-env` = el agente usa valores por defecto que NO coinciden con tu Aurora/tabla de minutas
- El agente corre en **modo VPC** para alcanzar Aurora (subnets del cluster de `ProduccionPocStack`)
- Default region es `us-west-2`, especificar si usás otra
- Para dev local: `agentcore dev` + `agentcore invoke --dev`
- Después de cada cambio de código, testear con `agentcore invoke --dev`
- El comando correcto es `agentcore deploy` (no `launch`)

## Sincronización backend ↔ agentcore

Los módulos compartidos son copias de `backend/` en `agentcore/` con imports dual-path:

- `agentcore/tools/` ← copia de `backend/tools/` (fuente de verdad: backend/)
- `agentcore/agents/` ← copia de `backend/agents/`
- `agentcore/models/` ← copia de `backend/models/`
- `agentcore/data/` ← copia de `backend/data/`
- `agentcore/utils/` ← copia de `backend/utils/`

- ✅ Editar siempre en `backend/` — luego copiar a `agentcore/`
- ❌ Symlinks NO funcionan con `agentcore deploy` (no resuelve links fuera del directorio)
- Los módulos usan imports con try/except para dual-path (backend.X / X)

## Datos del Dominio (referencia rápida para tools)

### Tablas Aurora PostgreSQL (consultadas vía `query_db`)
- **medicos**: Medico_MN, Nombre, Apellido, Mail, Telefono_Consultorio, Telefono_Celular, Especialidad_Medica, Calle, Altura, Barrio, Zona, Fecha_Ultima_Visita, Fecha_Nacimiento, Hobby_Intereses, Religion, Cadencia, Hospital, Facultad, Anio_Egresado, APM, Latitud, Longitud
- **visitas**: Visita_ID, APM, Medico_MN, Fecha_Visita, Zona, Tipo_Visita, Productos_Presentados, Notas
- **ventas**: Anio, Mes, Zona, Producto, Presentacion, Tipo_OTC_RX, Unidades_Vendidas, Valor_Venta_ARS, Crecimiento_YoY_Pct, Farmacia

### DynamoDB (`MinutasTable`, vía `obtener_minutas`)
- **minutas**: minutas de voz asociadas a visitas

### Relaciones clave
- `Medico_MN` vincula médicos con visitas
- `APM` (nombre) vincula visitas con el visitador y médicos con su APM asignado
- `Zona` vincula médicos, visitas y ventas geográficamente
- `Productos_Presentados` en visitas usa `|` como separador

### Cadencias de visita
Mensual, Trimestral, Semestral, Anual, Digital (solo contenido online)
