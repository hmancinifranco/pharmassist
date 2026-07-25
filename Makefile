# ============================================================================
# PharmAssist — Makefile
# Orquesta el setup completo del proyecto para un usuario nuevo.
# Todos los targets leen configuración desde .env en la raíz del proyecto.
# ============================================================================

# Cargar .env si existe (las vars definidas sobreescriben el entorno)
ifneq (,$(wildcard .env))
	include .env
	export
endif

AWS_PROFILE ?= default
AWS_REGION  ?= us-east-1
STACK       ?= PharmAssistStack

.PHONY: help
help: ## Mostrar esta ayuda
	@echo ""
	@echo "PharmAssist — Setup targets:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort
	@echo ""
	@echo "Orden recomendado para un setup desde cero:"
	@echo "  1. make check-prereqs         (verifica Docker, CDK, toolkit, AWS CLI)"
	@echo "  2. make bootstrap             (instala dependencias Python/Node)"
	@echo "  3. make cdk-bootstrap         (cdk bootstrap la primera vez en la cuenta)"
	@echo "  4. make deploy-all            (deploy completo: Aurora → CDK → agents → frontend)"
	@echo "  5. make seed                  (puebla Aurora + crea usuario Peccy en Cognito)"
	@echo ""
	@echo "  O paso a paso:"
	@echo "    make deploy-data-layer      (ProduccionPocStack: VPC + Aurora + seed Lambda)"
	@echo "    make deploy-infra           (PharmAssistStack principal)"
	@echo "    make env-from-outputs       (escribe outputs de ambos stacks a .env)"
	@echo "    make seed                   (puebla Aurora + usuario Peccy)"
	@echo "    make deploy-text-agent      (CodeAgent a AgentCore, VPC mode)"
	@echo "    make deploy-bidi-agent      (BidiAgent de voz)"
	@echo "    make deploy-frontend        (build + S3 + CloudFront)"
	@echo ""
	@echo "Para borrar todo: make destroy"
	@echo ""

# ----------------------------------------------------------------------------
# Prerequisite checks
# ----------------------------------------------------------------------------

.PHONY: check-prereqs
check-prereqs: ## Verificar herramientas requeridas (docker, cdk, agentcore, aws, node, python)
	@echo "→ Verificando herramientas..."
	@command -v node >/dev/null || (echo "  ✗ node no encontrado (instalar Node.js 20+)" && exit 1)
	@command -v python3 >/dev/null || (echo "  ✗ python3 no encontrado (instalar Python 3.12+)" && exit 1)
	@command -v aws >/dev/null || (echo "  ✗ aws CLI no encontrado (instalar AWS CLI v2)" && exit 1)
	@command -v cdk >/dev/null || (echo "  ✗ cdk no encontrado (npm install -g aws-cdk)" && exit 1)
	@command -v docker >/dev/null || (echo "  ✗ docker no encontrado (instalar Docker Desktop)" && exit 1)
	@docker info >/dev/null 2>&1 || (echo "  ✗ docker daemon no está corriendo (abrir Docker Desktop)" && exit 1)
	@command -v agentcore >/dev/null || (echo "  ✗ agentcore no encontrado (pip install bedrock-agentcore-starter-toolkit)" && exit 1)
	@[ -f .env ] || (echo "  ✗ .env no existe (copialo de .env.example: cp .env.example .env)" && exit 1)
	@aws sts get-caller-identity --profile $(AWS_PROFILE) >/dev/null 2>&1 || (echo "  ✗ AWS profile '$(AWS_PROFILE)' no está configurado o sin acceso" && exit 1)
	@echo "  ✓ node $$(node --version)"
	@echo "  ✓ python3 $$(python3 --version | cut -d' ' -f2)"
	@echo "  ✓ aws $$(aws --version 2>&1 | cut -d' ' -f1)"
	@echo "  ✓ cdk $$(cdk --version)"
	@echo "  ✓ docker $$(docker --version | cut -d',' -f1)"
	@echo "  ✓ agentcore $$(agentcore --version 2>/dev/null || echo 'installed')"
	@echo "  ✓ AWS profile '$(AWS_PROFILE)' → $$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text)"
	@echo "  ✓ Región: $(AWS_REGION)"
	@echo ""
	@echo "IMPORTANTE: Antes de deployar, verificá en Bedrock Console → Model access:"
	@echo "  - anthropic.claude-sonnet-5 (inference profile us.anthropic.claude-sonnet-5)"
	@echo "  - amazon.nova-2-sonic-v1:0"
	@echo "  - amazon.nova-2-lite-v1:0 (para summarize de minutas)"

# ----------------------------------------------------------------------------
# Bootstrap (install deps)
# ----------------------------------------------------------------------------

.PHONY: bootstrap
bootstrap: ## Instalar dependencias (Python venvs + npm)
	@echo "→ Creando venv de infrastructure..."
	@cd infrastructure && python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt
	@echo "→ Creando venv de backend..."
	@cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt
	@echo "→ Instalando dependencias del frontend..."
	@cd frontend && npm install --silent
	@echo "→ Sincronizando frontend/.env con raíz (symlink)..."
	@[ -L frontend/.env ] || ln -sf ../.env frontend/.env
	@echo "✓ Bootstrap completo."

.PHONY: cdk-bootstrap
cdk-bootstrap: ## Ejecutar 'cdk bootstrap' (solo la primera vez en cada cuenta/región)
	@echo "→ Bootstrapeando CDK en cuenta $$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text) región $(AWS_REGION)..."
	@cd infrastructure && . .venv/bin/activate && cdk bootstrap aws://$$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text)/$(AWS_REGION) --profile $(AWS_PROFILE)

# ----------------------------------------------------------------------------
# Infrastructure deploy
# ----------------------------------------------------------------------------

.PHONY: deploy-data-layer
deploy-data-layer: ## Deploy de la capa de datos (ProduccionPocStack: VPC + Aurora + seed Lambda) y escribe outputs POC_* a .env
	@echo "→ Deployando ProduccionPocStack (VPC + Aurora Serverless v2 + seed Lambda, ~8-12 min)..."
	@cd produccion-poc/infrastructure && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements.txt \
		&& cdk deploy ProduccionPocStack --profile $(AWS_PROFILE) --require-approval never
	@echo "→ Escribiendo outputs POC_* a .env..."
	@bash scripts/env-from-outputs.sh || true

.PHONY: deploy-infra
deploy-infra: ## Deploy del CDK stack principal (correr 2 veces: antes y después de deploy-text-agent)
	@cd infrastructure && . .venv/bin/activate && cdk deploy $(STACK) --profile $(AWS_PROFILE) --require-approval never

.PHONY: env-from-outputs
env-from-outputs: ## Escribir los outputs del stack en .env
	@echo "→ Extrayendo outputs del stack $(STACK) y escribiendo a .env..."
	@bash scripts/env-from-outputs.sh

.PHONY: cdk-diff
cdk-diff: ## Ver cambios pendientes en el stack
	@cd infrastructure && . .venv/bin/activate && cdk diff $(STACK) --profile $(AWS_PROFILE)

# ----------------------------------------------------------------------------
# Data + demo users
# ----------------------------------------------------------------------------

.PHONY: seed
seed: seed-aurora seed-peccy ## Poblar Aurora (seed Lambda) + crear usuario demo Peccy en Cognito

.PHONY: seed-users
seed-users: ## (Avanzado) Crear un usuario demo adicional con los valores DEMO_USER_* del .env
	@cd backend && . .venv/bin/activate && python ../scripts/create-demo-user.py

.PHONY: seed-aurora
seed-aurora: ## Poblar Aurora invocando la Lambda de seed del ProduccionPocStack (~5-10 min)
	@[ -n "$(POC_SEED_LAMBDA_ARN)" ] || (echo "✗ POC_SEED_LAMBDA_ARN vacío. Deployá la capa de datos primero: make deploy-data-layer" && exit 1)
	@echo "→ Invocando seed Lambda (puebla Aurora con datos sintéticos)..."
	@aws lambda invoke --function-name $(POC_SEED_LAMBDA_ARN) --payload '{}' \
		--cli-read-timeout 900 --profile $(AWS_PROFILE) --region $(AWS_REGION) /tmp/poc-seed-response.json >/dev/null
	@cat /tmp/poc-seed-response.json && echo ""

.PHONY: seed-peccy
seed-peccy: ## Crear el usuario demo 'Peccy' en Cognito (custom:apm_id → APM_001 en Aurora)
	@cd backend && . .venv/bin/activate && python ../scripts/setup_peccy_user.py

# ----------------------------------------------------------------------------
# Agents deploy
# ----------------------------------------------------------------------------

.PHONY: deploy-text-agent
deploy-text-agent: ## Deploy del Text Agent a Bedrock AgentCore
	@bash scripts/deploy-text-agent.sh

.PHONY: deploy-bidi-agent
deploy-bidi-agent: ## Deploy del BidiAgent (voz) a Bedrock AgentCore
	@bash scripts/deploy-bidi-agent.sh

.PHONY: agents-invoke
agents-invoke: ## Invocar el Text Agent con un prompt de prueba
	@cd agentcore && AWS_PROFILE=$(AWS_PROFILE) agentcore invoke '{"prompt": "Hola", "apm_id": "Demo APM"}'

# ----------------------------------------------------------------------------
# Frontend deploy
# ----------------------------------------------------------------------------

.PHONY: deploy-frontend
deploy-frontend: ## Build + S3 sync + CloudFront invalidation
	@bash scripts/deploy-frontend.sh

# ----------------------------------------------------------------------------
# Deploy completo (orquesta todos los pasos en orden)
# Dependencias:
#   deploy-infra      → crea la infra CDK (Cognito, API GW, Lambda, S3, CloudFront)
#   env-from-outputs  → escribe los outputs del stack a .env (ARNs, URLs, table names)
#   deploy-text-agent → necesita env vars de .env (tablas, modelo, región)
#   deploy-bidi-agent → necesita TEXT_AGENT_ARN (obtenido de agentcore status del text agent)
#   deploy-frontend   → necesita VITE_* vars de .env (Cognito, API URL, WS URL)
# Si cualquier paso falla, Make detiene la ejecución (comportamiento por defecto).
# ----------------------------------------------------------------------------

.PHONY: deploy-all
deploy-all: ## Deploy completo: CDK + env-from-outputs + Text Agent + BidiAgent + Frontend
	@echo "═══════════════════════════════════════════════════════"
	@echo "  PharmAssist — Deploy completo (cuenta $$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text 2>/dev/null || echo 'unknown'))"
	@echo "═══════════════════════════════════════════════════════"
	@echo ""
	@echo "→ [1/6] Deploying capa de datos (ProduccionPocStack: VPC + Aurora)..."
	$(MAKE) deploy-data-layer
	@echo ""
	@echo "→ [2/6] Deploying CDK stack principal (PharmAssistStack)..."
	$(MAKE) deploy-infra
	@echo ""
	@echo "→ [3/6] Escribiendo outputs de ambos stacks a .env..."
	$(MAKE) env-from-outputs
	@echo ""
	@echo "→ [4/6] Deploying Text Agent (CodeAgent, VPC) a AgentCore..."
	$(MAKE) deploy-text-agent
	@echo ""
	@echo "→ [5/6] Deploying BidiAgent (voz) a AgentCore..."
	$(MAKE) deploy-bidi-agent
	@echo ""
	@echo "→ [6/6] Building + deploying frontend a CloudFront..."
	$(MAKE) deploy-frontend
	@echo ""
	@echo "  Nota: si es la primera vez, poblá Aurora con 'make seed' (data + usuario Peccy)."
	@echo ""
	@echo "✓ Deploy completo exitoso."
	@echo "  → Frontend: $$(grep VITE_API_URL .env | cut -d= -f2 | head -1)"
	@echo "  → CloudFront: $$(grep CloudFrontDomain .env 2>/dev/null || echo '(ver outputs del stack)')"

# ----------------------------------------------------------------------------
# Documentación
# ----------------------------------------------------------------------------

.PHONY: docs-html
docs-html: ## Regenerar los exportables HTML de docs/ desde el Markdown (requiere pandoc)
	@bash scripts/build-docs-html.sh

# ----------------------------------------------------------------------------
# E2E tests
# ----------------------------------------------------------------------------

.PHONY: e2e-test
e2e-test: ## Ejecutar test E2E con Playwright (requiere deploy completo)
	@cd e2e && npm install --silent && npx playwright install chromium --with-deps && npx playwright test

# ----------------------------------------------------------------------------
# Local dev
# ----------------------------------------------------------------------------

.PHONY: dev-frontend
dev-frontend: ## Correr el frontend localmente (http://localhost:5173)
	@cd frontend && npm run dev

.PHONY: dev-backend
dev-backend: ## Correr el backend localmente (http://localhost:8000)
	@cd backend && . .venv/bin/activate && uvicorn main:app --reload --port 8000

# ----------------------------------------------------------------------------
# Destroy
# ----------------------------------------------------------------------------

.PHONY: destroy
destroy: ## Destruir TODO (agents + stack principal + capa de datos Aurora). Pedirá confirmación.
	@echo "⚠️  Vas a destruir TODOS los recursos de PharmAssist en la cuenta $$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text) región $(AWS_REGION)."
	@read -p "¿Continuar? (escribí 'destroy' para confirmar): " confirm && [ "$$confirm" = "destroy" ]
	@echo "→ [1/4] Destruyendo BidiAgent (depende de Text Agent, se destruye primero)..."
	@cd bidiagent && AWS_PROFILE=$(AWS_PROFILE) agentcore destroy --force --delete-ecr-repo 2>&1 | tail -5 || echo "  (no había agente o no se pudo destruir)"
	@echo "→ [2/4] Destruyendo Text Agent..."
	@cd agentcore && AWS_PROFILE=$(AWS_PROFILE) agentcore destroy --force --delete-ecr-repo 2>&1 | tail -5 || echo "  (no había agente o no se pudo destruir)"
	@echo "→ [3/4] Destruyendo CDK stack principal (PharmAssistStack)..."
	@cd infrastructure && . .venv/bin/activate && cdk destroy $(STACK) --profile $(AWS_PROFILE) --force
	@echo "→ [4/4] Destruyendo capa de datos (ProduccionPocStack: Aurora + VPC + NAT)..."
	@cd produccion-poc/infrastructure && . .venv/bin/activate && cdk destroy ProduccionPocStack --profile $(AWS_PROFILE) --force 2>&1 | tail -5 || echo "  (no estaba deployado o no se pudo destruir)"
	@echo "→ Limpiando memorias AgentCore huérfanas..."
	@bash scripts/cleanup-orphan-memories.sh || true
	@echo "✓ Destrucción completa."
