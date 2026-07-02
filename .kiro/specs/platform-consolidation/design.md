# Design Document — Platform Consolidation

## Introducción

Este diseño describe la consolidación de la plataforma PharmAssist: migración de los endpoints del dashboard de DynamoDB a Aurora PostgreSQL, eliminación de 4 tablas DynamoDB del CDK stack, mejoras de UX (loading skeletons, dark mode, suggestion chips, WebSocket fallback), deploy unificado con Makefile, y test E2E con Playwright.

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React + MUI)                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │Dashboard │  │ ChatPanel    │  │ Suggestion │  │  WebSocket   │  │
│  │ Cards    │  │ (WS + HTTP)  │  │   Chips    │  │  Fallback    │  │
│  └────┬─────┘  └──────┬───────┘  └──────┬─────┘  └──────┬───────┘  │
└───────┼────────────────┼─────────────────┼───────────────┼──────────┘
        │ REST           │ WS/HTTP         │               │
        ▼                ▼                 ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                                  │
│  ┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐  │
│  │ Dashboard Endpoints│ │ Chat Endpoint     │  │ db.py (pool)    │  │
│  │ /api/dashboard/*  │ │ /api/chat          │  │ psycopg2 +      │  │
│  │ (Direct Aurora)   │ │ (→ AgentCore)      │  │ Secrets Manager │  │
│  └────────┬──────────┘ └──────────────────┘   └────────┬────────┘  │
└───────────┼─────────────────────────────────────────────┼───────────┘
            │                                             │
            ▼                                             ▼
┌──────────────────────┐                    ┌──────────────────────────┐
│   Aurora PostgreSQL   │                    │   AWS Secrets Manager    │
│   (agenda, doctor,    │                    │   (DB credentials)       │
│    cartera_medica)    │                    │                          │
└──────────────────────┘                    └──────────────────────────┘
```

**Decisión clave**: Los endpoints del dashboard consultan Aurora directamente via `psycopg2` (con connection pool en `backend/db.py`), NO a través del agente. Esto evita cold starts del agente y mantiene la latencia del dashboard baja (~100-300ms vs 3-8s del agente).


## Componentes

### 1. Backend: Módulo de conexión Aurora (`backend/db.py`)

Módulo compartido que encapsula la conexión a Aurora PostgreSQL. Reutiliza el patrón de `agentcore/toolkit.py` (Secrets Manager → credenciales → conexión) pero con `psycopg2` directamente (sin SQLAlchemy) para minimizar dependencias en el backend FastAPI.

```python
"""backend/db.py — Connection pool para Aurora PostgreSQL."""
import json
import logging
import os
from contextlib import contextmanager
from typing import Generator

import boto3
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)

_pool: pool.ThreadedConnectionPool | None = None


def _get_secret() -> dict:
    """Fetch DB credentials from Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    secret_arn = os.environ["DB_SECRET_ARN"]
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def _init_pool() -> pool.ThreadedConnectionPool:
    """Initialize psycopg2 ThreadedConnectionPool."""
    secret = _get_secret()
    return pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        host=secret["host"],
        port=secret.get("port", 5432),
        dbname=secret["dbname"],
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
        sslrootcert=os.environ.get("RDS_CA_BUNDLE", "rds-ca-bundle.pem"),
        connect_timeout=5,
    )


def get_pool() -> pool.ThreadedConnectionPool:
    """Get or create the connection pool (singleton)."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = _init_pool()
    return _pool


@contextmanager
def get_connection() -> Generator:
    """Context manager that gets a connection from the pool and returns it."""
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)
```

**Principios**:
- Pool con `minconn=2, maxconn=10` — suficiente para FastAPI con uvicorn (single process dev, gunicorn en prod)
- `sslmode=require` + CA bundle para TLS obligatorio
- Context manager `get_connection()` garantiza que las conexiones se devuelven al pool
- Secrets se cachean en memoria dentro del pool (no se re-fetcha en cada request)
- Si la conexión falla, se propaga la excepción para que el endpoint retorne 503


### 2. Backend: Dashboard Endpoints (refactorizados)

Los 3 endpoints existentes se refactorizan para consultar Aurora en lugar de DynamoDB. Los contratos de respuesta NO cambian.

#### GET `/api/dashboard/visits-today`

```python
@app.get("/api/dashboard/visits-today")
async def visits_today(apm_id: str = Depends(resolve_apm_id)):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT a.medico_mn, a.fecha_planificada, a.zona, a.tipo_visita,
                           a.productos_sugeridos, a.estado,
                           d.nombre AS "Medico_Nombre", d.apellido AS "Medico_Apellido",
                           d.especialidad_medica, d.cadencia
                    FROM agenda a
                    JOIN doctor d ON a.medico_mn = d.medico_mn
                    WHERE a.apm_id = %s AND a.fecha_planificada = CURRENT_DATE
                    ORDER BY a.hora_sugerida ASC
                """, (apm_id,))
                rows = cur.fetchall()
        return [_transform_visit_row(r) for r in rows]
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.error(f"Aurora connection error: {e}")
        raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")
```

#### GET `/api/dashboard/birthdays`

```python
@app.get("/api/dashboard/birthdays")
async def birthdays(apm_id: str = Depends(resolve_apm_id)):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT medico_mn, nombre, apellido, especialidad_medica,
                           fecha_nacimiento, zona
                    FROM doctor
                    WHERE apm_id = %s
                      AND fecha_nacimiento IS NOT NULL
                    ORDER BY
                      EXTRACT(DOY FROM fecha_nacimiento) - EXTRACT(DOY FROM CURRENT_DATE)
                """, (apm_id,))
                rows = cur.fetchall()
        return filtrar_cumpleanos_proximos(rows, dias_adelante=30)
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.error(f"Aurora connection error: {e}")
        raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")
```

#### GET `/api/dashboard/sla-alerts`

```python
@app.get("/api/dashboard/sla-alerts")
async def sla_alerts(apm_id: str = Depends(resolve_apm_id)):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT cm.medico_mn, d.nombre, d.apellido, d.especialidad_medica,
                           d.cadencia, cm.fecha_ultima_visita, d.zona
                    FROM cartera_medica cm
                    JOIN doctor d ON cm.medico_mn = d.medico_mn
                    WHERE cm.apm_id = %s
                """, (apm_id,))
                rows = cur.fetchall()
        return obtener_alertas_sla(rows)
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.error(f"Aurora connection error: {e}")
        raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")
```

**Manejo de errores**: Todos los endpoints atrapan `psycopg2.OperationalError` y `InterfaceError` (errores de conexión) y retornan HTTP 503 con mensaje genérico. Errores de lógica (datos inválidos) se propagan normalmente como 500.


### 3. CDK Stack: Eliminación de tablas DynamoDB

Se eliminan del `infrastructure/stacks/pharmassist_stack.py`:

| Recurso a eliminar | Logical ID | Tabla física |
|-------------------|------------|--------------|
| `self.medicos_table` | `MedicosTable` | `crm_medicos` |
| `self.visitas_table` | `VisitasTable` | `apm_visitas` |
| `self.ventas_table` | `VentasTable` | `ventas_reportadas` |
| `self.planificadas_table` | `PlanificadasTable` | `visitas_planificadas` |

**Se conserva**: `self.minutas_table` (`MinutasTable` / `minutas_visitas`) — usada por el agente para persistir minutas de visitas.

**También se eliminan**:
- Los `CfnOutput` que exportan nombres/ARNs de las 4 tablas
- Los `grant_read_write_data()` / `grant_read_data()` del Lambda proxy hacia las 4 tablas
- Las environment variables del Lambda proxy que referencian las tablas eliminadas

**Se conserva todo lo demás**: Cognito (User Pool, Identity Pool), API Gateway (HTTP + WebSocket), Lambda proxy, CloudFront + S3 (frontend), S3 audio bucket, IAM roles base.

### 4. Frontend: Loading Skeletons

Se agregan componentes Skeleton en las 3 tarjetas del dashboard, usando el estado `loading` del store de Zustand.

```typescript
// En DashboardPage.tsx — ejemplo para visitas
{visitsLoading ? (
  <Card sx={{ p: 2, height: 200 }}>
    <Skeleton variant="text" width="60%" height={32} />
    <Skeleton variant="rectangular" height={120} sx={{ mt: 1, borderRadius: 1 }} />
  </Card>
) : visitsError ? (
  <Card sx={{ p: 2, height: 200 }}>
    <Typography color="text.secondary">
      No se pudieron cargar las visitas del día
    </Typography>
  </Card>
) : (
  <TarjetaVisitasHoy visits={visits} />
)}
```

**Patrón**: Cada tarjeta tiene 3 estados: `loading` (Skeleton), `error` (mensaje vacío), `data` (tarjeta real). El Zustand store ya tiene los flags `visitsLoading`, `birthdaysLoading`, `alertsLoading`.

### 5. Frontend: WebSocket Fallback silencioso

El `useAppStore.ts` ya tiene lógica de WebSocket. Se extiende con fallback a HTTP:

```typescript
// En useAppStore.ts — sendMessage action
sendMessage: async (text: string) => {
  const { wsConnected, wsInstance } = get();
  
  // Add user message to chat immediately
  const userMsg: ChatMessage = { id: uuid(), role: 'user', content: text, timestamp: Date.now() };
  set(state => ({ chatMessages: [...state.chatMessages, userMsg] }));
  
  if (wsConnected && wsInstance) {
    // Prefer WebSocket
    wsInstance.send(text);
    console.debug('[PharmAssist] Message sent via WebSocket');
  } else {
    // Fallback to HTTP POST
    console.debug('[PharmAssist] WebSocket unavailable, using HTTP fallback');
    set({ chatLoading: true });
    try {
      const response = await sendChatMessage(text, get().sessionId, get().apmId);
      const assistantMsg: ChatMessage = { id: uuid(), role: 'assistant', content: response.message, timestamp: Date.now() };
      set(state => ({ chatMessages: [...state.chatMessages, assistantMsg], chatLoading: false }));
    } catch (e) {
      set({ chatError: 'Error al enviar mensaje', chatLoading: false });
    }
  }
}
```

**Reconexión**: Si el WS se desconecta, se activa un retry con backoff exponencial (1s, 2s, 4s, max 30s). Durante el retry, mensajes van por HTTP. Cuando reconecta, se retoma WS automáticamente.


### 6. Frontend: Dark Mode Fixes

Se ajusta el theme MUI (`frontend/src/theme.ts`) para garantizar contraste WCAG AA en dark mode:

```typescript
// theme.ts — palette dark overrides
const darkPalette = {
  background: {
    default: '#121212',
    paper: '#1e1e1e',
  },
  text: {
    primary: '#e0e0e0',    // contrast ratio > 10:1 vs paper
    secondary: '#a0a0a0',  // contrast ratio > 4.5:1 vs paper
  },
};

// Componentes MUI afectados:
const components = {
  MuiCard: {
    styleOverrides: {
      root: ({ theme }) => ({
        ...(theme.palette.mode === 'dark' && {
          backgroundColor: theme.palette.background.paper,
          border: '1px solid rgba(255,255,255,0.12)',
        }),
      }),
    },
  },
  MuiChip: {
    styleOverrides: {
      root: ({ theme }) => ({
        ...(theme.palette.mode === 'dark' && {
          backgroundColor: 'rgba(144, 202, 249, 0.16)',
          border: '1px solid rgba(144, 202, 249, 0.5)',
          color: '#90caf9',
        }),
      }),
    },
  },
  MuiSkeleton: {
    styleOverrides: {
      root: ({ theme }) => ({
        ...(theme.palette.mode === 'dark' && {
          backgroundColor: 'rgba(255,255,255,0.08)',
        }),
      }),
    },
  },
  MuiDataGrid: {
    styleOverrides: {
      root: ({ theme }) => ({
        ...(theme.palette.mode === 'dark' && {
          borderColor: 'rgba(255,255,255,0.12)',
          '& .MuiDataGrid-cell': { borderColor: 'rgba(255,255,255,0.08)' },
          '& .MuiDataGrid-columnHeaders': { backgroundColor: '#2d2d2d' },
        }),
      }),
    },
  },
};
```

### 7. Frontend: Suggestion Chips

Componente nuevo `SuggestionChips.tsx` que muestra chips clickeables cuando el chat está vacío:

```typescript
// frontend/src/components/Chat/SuggestionChips.tsx
const SUGGESTIONS = [
  '¿Qué visitas tengo hoy?',
  '¿Qué médicos tienen cumpleaños esta semana?',
  '¿Cuáles son mis alertas SLA?',
  'Dame un resumen de ventas de mi zona',
];

interface SuggestionChipsProps {
  onChipClick: (text: string) => void;
  visible: boolean;
}

export function SuggestionChips({ onChipClick, visible }: SuggestionChipsProps) {
  if (!visible) return null;
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ p: 1 }}>
      {SUGGESTIONS.map((text) => (
        <Chip
          key={text}
          label={text}
          onClick={() => onChipClick(text)}
          variant="outlined"
          clickable
        />
      ))}
    </Stack>
  );
}
```

**Visibilidad**: Los chips se muestran solo cuando `chatMessages.length === 0`. Al enviar cualquier mensaje (chip o input), desaparecen.

**Configuración local**: Los textos vienen de una constante en el archivo, no de una API call.


### 8. Makefile: `deploy-all` y `destroy`

Nuevos targets que orquestan el deploy completo:

```makefile
# --- Deploy order: CDK → Text Agent → BidiAgent → Frontend ---
# CDK provee los recursos base (Cognito, API GW, S3, CloudFront, MinutasTable)
# Text Agent se despliega primero porque BidiAgent depende de su ARN
# BidiAgent recibe TEXT_AGENT_ARN automáticamente via `agentcore status`
# Frontend se despliega último porque necesita la URL de API Gateway

.PHONY: deploy-all
deploy-all: ## Deploy completo: CDK + Text Agent + BidiAgent + Frontend
	@echo "═══════════════════════════════════════════════════════"
	@echo "  PharmAssist — Deploy completo"
	@echo "═══════════════════════════════════════════════════════"
	@echo ""
	@echo "→ [1/4] Deploying CDK stack..."
	$(MAKE) deploy-infra
	@echo ""
	@echo "→ [2/4] Deploying Text Agent..."
	$(MAKE) deploy-text-agent
	@echo ""
	@echo "→ [3/4] Deploying BidiAgent (con TEXT_AGENT_ARN auto-wired)..."
	$(MAKE) deploy-bidi-agent
	@echo ""
	@echo "→ [4/4] Deploying Frontend..."
	$(MAKE) deploy-frontend
	@echo ""
	@echo "✓ Deploy completo exitoso."
```

**Error propagation**: Makefile por defecto detiene la ejecución si un paso falla (exit code != 0). Cada sub-target (`deploy-infra`, etc.) ya maneja sus propios errores.

**Auto-wiring de TEXT_AGENT_ARN**: El script `scripts/deploy-bidi-agent.sh` ejecuta `agentcore status` en el directorio `agentcore/` para obtener el ARN del Text Agent y lo pasa como `-env TEXT_AGENT_ARN=<arn>` al deploy del BidiAgent.

```bash
# scripts/deploy-bidi-agent.sh (lógica de auto-wiring)
TEXT_AGENT_ARN=$(cd ../agentcore && agentcore status 2>/dev/null | grep -o 'arn:aws:bedrock-agentcore:[^"]*')
if [ -z "$TEXT_AGENT_ARN" ]; then
  echo "ERROR: Text Agent no está desplegado. Ejecutá 'make deploy-text-agent' primero."
  exit 1
fi
echo "  → TEXT_AGENT_ARN=$TEXT_AGENT_ARN"
cd ../bidiagent && agentcore deploy -auc \
  -env TEXT_AGENT_ARN="$TEXT_AGENT_ARN" \
  -env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  -env AWS_REGION="$AWS_REGION" \
  -env MINUTAS_TABLE_NAME="$MINUTAS_TABLE_NAME"
```

### 9. Test E2E con Playwright

Archivo: `e2e/tests/dashboard-flow.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('PharmAssist E2E Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login con credenciales demo desde env
    await page.goto(process.env.APP_URL || 'http://localhost:5173');
    await page.fill('[name="username"]', process.env.DEMO_USER || 'peccy');
    await page.fill('[name="password"]', process.env.DEMO_PASSWORD || 'Demo1234!');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });

  test('dashboard renders data cards', async ({ page }) => {
    // Verify at least one DataGrid or card is visible
    await expect(page.locator('[data-testid="dashboard-card"]').first()).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: 'e2e/screenshots/dashboard.png' });
  });

  test('suggestion chips are shown before first message', async ({ page }) => {
    await page.click('[data-testid="chat-toggle"]');
    await expect(page.locator('[data-testid="suggestion-chip"]').first()).toBeVisible();
  });

  test('chat sends message and receives response', async ({ page }) => {
    await page.click('[data-testid="chat-toggle"]');
    await page.fill('[data-testid="chat-input"]', '¿Qué visitas tengo hoy?');
    await page.press('[data-testid="chat-input"]', 'Enter');
    // Wait for agent response (max 30s)
    await expect(page.locator('[data-testid="assistant-message"]').first()).toBeVisible({ timeout: 30000 });
  });
});
```

**Config Playwright** (`e2e/playwright.config.ts`):
- Timeout global: 60s
- Screenshots: `on` (always capture)
- Reporter: `html` + `line`
- Base URL: leído de `process.env.APP_URL`

**Invocación**: `make e2e-test` ejecuta `npx playwright test` desde el directorio `e2e/`.


## Interfaces y Contratos

### API Contracts (sin cambios en la shape)

Los 3 endpoints del dashboard mantienen exactamente el mismo contrato de respuesta. Solo cambia la fuente de datos (DynamoDB → Aurora).

```typescript
// GET /api/dashboard/visits-today
// Response: VisitaPlanificada[]
interface VisitaPlanificada {
  apm: string;
  medico_mn: number;
  fecha_planificada: string;
  zona: string;
  tipo_visita: 'Presencial' | 'Virtual' | 'Telefónica';
  productos_sugeridos: string[];
  estado: 'Pendiente' | 'Completada' | 'Cancelada';
  medico?: Medico;
}

// GET /api/dashboard/birthdays
// Response: CumpleañosEntry[]
interface CumpleañosEntry {
  medico_mn: number;
  nombre: string;
  apellido: string;
  especialidad_medica: string;
  fecha_nacimiento: string;
  zona: string;
  dias_hasta_cumple: number;
}

// GET /api/dashboard/sla-alerts
// Response: AlertaSLA[]
interface AlertaSLA {
  medico: Medico;
  cadencia: string;
  fecha_ultima_visita?: string;
  dias_vencido: number;
}
```

### Módulo `backend/db.py` — API Interna

```python
# Exports:
get_connection() -> ContextManager[psycopg2.connection]  # uso: with get_connection() as conn
get_pool() -> psycopg2.pool.ThreadedConnectionPool      # para health checks o shutdown
```

### WebSocket Fallback — Contrato interno

```typescript
// Estado del store de Zustand:
interface ConnectionState {
  wsConnected: boolean;      // true = WS activo
  wsReconnecting: boolean;   // true = intentando reconectar
  fallbackActive: boolean;   // true = usando HTTP como fallback
}

// El frontend NUNCA muestra estos estados al usuario.
// Solo se logean en console.debug para debugging.
```

## Modelo de Datos

### Tablas Aurora PostgreSQL (existentes — no se crean en este spec)

```sql
-- Tabla: agenda (visitas planificadas del día)
CREATE TABLE agenda (
  id SERIAL PRIMARY KEY,
  apm_id VARCHAR(100) NOT NULL,
  medico_mn INTEGER NOT NULL REFERENCES doctor(medico_mn),
  fecha_planificada DATE NOT NULL,
  hora_sugerida TIME,
  zona VARCHAR(100),
  tipo_visita VARCHAR(20) DEFAULT 'Presencial',
  productos_sugeridos TEXT,  -- separados por '|'
  estado VARCHAR(20) DEFAULT 'Pendiente',
  created_at TIMESTAMP DEFAULT NOW()
);

-- Tabla: doctor (catálogo de médicos)
CREATE TABLE doctor (
  medico_mn INTEGER PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  especialidad_medica VARCHAR(100),
  zona VARCHAR(100),
  apm_id VARCHAR(100),
  cadencia VARCHAR(20),
  fecha_nacimiento DATE,
  telefono_celular VARCHAR(50),
  mail VARCHAR(150),
  hospital VARCHAR(200),
  hobby_intereses TEXT,
  -- ... otros campos del CRM
  created_at TIMESTAMP DEFAULT NOW()
);

-- Tabla: cartera_medica (relación APM-médico con última visita)
CREATE TABLE cartera_medica (
  id SERIAL PRIMARY KEY,
  apm_id VARCHAR(100) NOT NULL,
  medico_mn INTEGER NOT NULL REFERENCES doctor(medico_mn),
  fecha_ultima_visita DATE,
  total_visitas INTEGER DEFAULT 0,
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### DynamoDB: MinutasTable (se conserva)

```
Table: minutas_visitas
  PK: visita_id (String)
  SK: timestamp (String)
  Attributes: apm_id, medico_mn, transcription, summary, action_items, audio_s3_key
```


## Manejo de Errores

### Backend — Aurora connection errors

| Escenario | Comportamiento | HTTP Status |
|-----------|---------------|-------------|
| Secrets Manager no accesible | Pool init falla, 503 | 503 |
| Aurora host unreachable | Connection timeout, 503 | 503 |
| Credenciales inválidas | Auth error, 503 | 503 |
| Query timeout (>5s) | Statement timeout, 503 | 503 |
| SQL error (bug en query) | 500 con log detallado (no expuesto) | 500 |
| Datos válidos pero vacíos | Array vacío `[]` | 200 |

**Regla**: Nunca exponer en el response body: hostname de Aurora, username, query SQL, stack trace. Solo un mensaje genérico: `"Servicio temporalmente no disponible"`.

### Frontend — Loading states

| Estado | Duración típica | UI |
|--------|----------------|-----|
| Loading | 100-300ms | Skeleton visible |
| Success | instantáneo | Datos renderizados |
| Error (retryable) | 3 reintentos × 1s | Skeleton visible durante retry |
| Error (final) | — | Tarjeta vacía con mensaje |

### Frontend — WebSocket fallback

| Evento | Acción | Logging |
|--------|--------|---------|
| WS connect fail | Switch a HTTP, no UI feedback | `console.debug` |
| WS disconnect mid-session | Retry con backoff, HTTP interim | `console.debug` |
| WS reconnect success | Resume WS, stop HTTP fallback | `console.debug` |
| HTTP fallback error | Show error in chat | `console.error` |

## Decisiones de Diseño

1. **psycopg2 sobre SQLAlchemy**: El backend FastAPI solo necesita ejecutar queries parametrizados simples. SQLAlchemy agrega complejidad (ORM, session management) que no aporta valor aquí. `agentcore/toolkit.py` usa SQLAlchemy porque necesita el pool management más sofisticado para el agente long-lived.

2. **Connection pool en proceso**: Para el desarrollo local (uvicorn single process) y producción moderada, un `ThreadedConnectionPool` in-process es suficiente. Si se escala a múltiples workers, se puede migrar a pgbouncer externo sin cambiar la API del módulo `db.py`.

3. **Dashboard directo a Aurora (sin agente)**: Latencia ~100-300ms vs 3-8s si se pasara por el agente. El agente es para consultas complejas en lenguaje natural, no para queries predefinidos del dashboard.

4. **Fallback silencioso**: El APM no necesita saber si está usando WS o HTTP. La experiencia debe ser transparente — si WS falla, HTTP funciona igual pero sin streaming (respuesta completa de una vez).

5. **Chips desde config local**: Evita una llamada al backend extra al cargar el chat. Los textos son estáticos y solo cambian con deploys del frontend.

6. **CDK removal policy**: Las 4 tablas DynamoDB tienen `RemovalPolicy.DESTROY`. Al eliminarlas del stack, CDK las destruirá en el próximo deploy. Los datos ya están en Aurora, así que no hay pérdida.


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Data isolation — visits filtered by APM

*For any* `apm_id` and any set of visits in the `agenda` table, calling `GET /api/dashboard/visits-today` with that `apm_id` SHALL return only visits where `agenda.apm_id` matches the requesting APM, and zero visits belonging to other APMs.

**Validates: Requirements 1.1**

### Property 2: Data isolation — birthdays filtered by assigned APM

*For any* `apm_id` and any set of doctors in the `doctor` table, calling `GET /api/dashboard/birthdays` with that `apm_id` SHALL return only doctors where `doctor.apm_id` matches the requesting APM.

**Validates: Requirements 1.2**

### Property 3: SLA alert correctness

*For any* doctor with a defined `cadencia` and `fecha_ultima_visita`, the SLA alert calculation SHALL mark the doctor as overdue (dias_vencido > 0) if and only if the elapsed days since `fecha_ultima_visita` exceed the cadence period (30 for Mensual, 90 for Trimestral, 180 for Semestral, 365 for Anual).

**Validates: Requirements 1.3**

### Property 4: Aurora error produces 503 without internal details

*For any* database connection error (timeout, authentication failure, network unreachable, pool exhausted), the dashboard endpoints SHALL return HTTP 503 with a response body that does NOT contain hostnames, usernames, SQL queries, or Python stack traces.

**Validates: Requirements 1.7**

### Property 5: Response contract preservation

*For any* valid query result from Aurora, the JSON response from dashboard endpoints SHALL contain the same keys and value types as the existing contract (defined in frontend `types/index.ts`), ensuring frontend compatibility without code changes.

**Validates: Requirements 1.6**

### Property 6: Suggestion chip click sends user message

*For any* chip text from the suggestions list, clicking that chip SHALL add a message with `role: 'user'` and `content` equal to the chip text to the chat history, and send that text to the backend via the available channel (WS or HTTP).

**Validates: Requirements 6.2, 6.3**

### Property 7: Suggestion chips hidden after message

*For any* message sent (whether from chip click or typed input), the suggestion chips SHALL become invisible (not rendered) until the conversation is cleared/reset.

**Validates: Requirements 6.4**

### Property 8: Suggestion chip count within bounds

*For any* chip configuration, the system SHALL display between 3 and 5 chips (inclusive) when the chat conversation is empty.

**Validates: Requirements 6.1**
