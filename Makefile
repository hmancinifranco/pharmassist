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
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort
	@echo ""
	@echo "Orden recomendado para un setup desde cero:"
	@echo "  1. make check-prereqs         (verifica Docker, CDK, toolkit, AWS CLI)"
	@echo "  2. make bootstrap             (instala dependencias Python/Node)"
	@echo "  3. make cdk-bootstrap         (cdk bootstrap la primera vez en la cuenta)"
	@echo "  4. make deploy-infra          (deploy CDK — primera pasada, sin agent ARN)"
	@echo "  5. make env-from-outputs      (escribe outputs del stack en .env)"
	@echo "  6. make seed                  (usuarios Cognito + CSVs → DynamoDB)"
	@echo "  7. make deploy-text-agent     (deploy Text Agent a AgentCore)"
	@echo "  8. make deploy-bidi-agent     (deploy BidiAgent de voz)"
	@echo "  9. make deploy-infra          (segunda pasada — pasa ARNs al Lambda proxy)"
	@echo " 10. make deploy-frontend       (build + S3 sync + invalidación CloudFront)"
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
	@echo "  - anthropic.claude-opus-4-6 (inference profile us.anthropic.claude-opus-4-6-v1)"
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

.PHONY: deploy-infra
deploy-infra: ## Deploy del CDK stack (correr 2 veces: antes y después de deploy-text-agent)
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
seed: seed-data seed-peccy ## Cargar CSVs en DynamoDB + crear usuario demo Peccy con sus 12 médicos

.PHONY: seed-users
seed-users: ## (Avanzado) Crear un usuario demo adicional con los valores DEMO_USER_* del .env
	@cd backend && . .venv/bin/activate && python ../scripts/create-demo-user.py

.PHONY: seed-data
seed-data: ## Cargar los CSVs en DynamoDB (y generar visitas planificadas)
	@cd backend && . .venv/bin/activate && python -m data.loader \
		--medicos-table $(MEDICOS_TABLE_NAME) \
		--visitas-table $(VISITAS_TABLE_NAME) \
		--ventas-table $(VENTAS_TABLE_NAME) \
		--planificadas-table $(PLANIFICADAS_TABLE_NAME) \
		--data-dir .. --year $$(date +%Y)

.PHONY: seed-peccy
seed-peccy: ## Crear el usuario demo 'Peccy' con 12 médicos + 2 años de visitas
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
destroy: ## Destruir TODO (agents + stack + buckets). Pedirá confirmación.
	@echo "⚠️  Vas a destruir TODOS los recursos de PharmAssist en la cuenta $$(aws sts get-caller-identity --profile $(AWS_PROFILE) --query Account --output text) región $(AWS_REGION)."
	@read -p "¿Continuar? (escribí 'destroy' para confirmar): " confirm && [ "$$confirm" = "destroy" ]
	@echo "→ Destruyendo Text Agent..."
	@cd agentcore && AWS_PROFILE=$(AWS_PROFILE) agentcore destroy --force --delete-ecr-repo 2>&1 | tail -5 || echo "  (no había agente o no se pudo destruir)"
	@echo "→ Destruyendo BidiAgent..."
	@cd bidiagent && AWS_PROFILE=$(AWS_PROFILE) agentcore destroy --force --delete-ecr-repo 2>&1 | tail -5 || echo "  (no había agente o no se pudo destruir)"
	@echo "→ Destruyendo CDK stack..."
	@cd infrastructure && . .venv/bin/activate && cdk destroy $(STACK) --profile $(AWS_PROFILE) --force
	@echo "→ Limpiando memorias AgentCore huérfanas..."
	@bash scripts/cleanup-orphan-memories.sh || true
	@echo "✓ Destrucción completa."
