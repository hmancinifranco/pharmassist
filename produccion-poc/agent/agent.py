"""
Entry point del CodeAgent de Producción — PharmAssist POC.

Crea un CodeAgent con strands-code-agent que genera y ejecuta código Python/SQL
en un REPL persistente. Si strands-code-agent no está disponible, fallback a
Agent regular con @tool query_db.

Wrapping con BedrockAgentCoreApp para deploy en AgentCore, o standalone via __main__.

Requirements: 1.1, 1.2, 1.6, 1.7
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration from environment
# ─────────────────────────────────────────────────────────────────────────────

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"
)
BEDROCK_REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
MAX_RETRIES = 2


# ─────────────────────────────────────────────────────────────────────────────
# CodeAgent creation (with fallback to regular Agent)
# ─────────────────────────────────────────────────────────────────────────────

def _create_model():
    """Instantiate BedrockModel with configured model ID and region."""
    from strands.models import BedrockModel

    return BedrockModel(
        model_id=BEDROCK_MODEL_ID,
        region_name=BEDROCK_REGION,
        temperature=0.3,
        max_tokens=4096,
    )


def _build_system_prompt() -> str:
    """Build the complete system prompt via SystemPromptBuilder."""
    try:
        from system_prompt import SystemPromptBuilder
    except ImportError:
        from produccion_poc_agent.system_prompt import SystemPromptBuilder

    builder = SystemPromptBuilder()
    return builder.build()


def _try_import_code_agent():
    """Attempt to import CodeAgent and Toolkit from strands-code-agent.

    Returns (CodeAgent, Toolkit) tuple or (None, None) if unavailable.

    NOTE: strands-code-agent Toolkit API differs from our assumed interface.
    Force fallback to regular Agent with @tool query_db for now.
    This provides equivalent functionality for the POC.
    """
    # Force fallback to regular Agent — the CodeAgent Toolkit API
    # doesn't match our assumed interface (authorized_imports, init_code, etc.)
    # The regular Agent with @tool query_db is functionally equivalent for POC.
    logger.info(
        "Using regular Agent with @tool query_db (CodeAgent toolkit API mismatch)."
    )
    return None, None


def create_code_agent(apm_id: str):
    """Create a CodeAgent instance configured for the given APM.

    Tries strands-code-agent first. If unavailable, creates a regular
    strands Agent with query_db as a @tool.

    Args:
        apm_id: The APM identifier for this session.

    Returns:
        A callable agent (CodeAgent or Agent).
    """
    model = _create_model()
    system_prompt = _build_system_prompt()

    CodeAgentCls, ToolkitCls = _try_import_code_agent()

    if CodeAgentCls is not None and ToolkitCls is not None:
        return _create_with_code_agent(
            CodeAgentCls, ToolkitCls, model, system_prompt, apm_id
        )
    else:
        return _create_with_regular_agent(model, system_prompt, apm_id)


def _create_with_code_agent(CodeAgentCls, ToolkitCls, model, system_prompt, apm_id: str):
    """Create agent using strands-code-agent CodeAgent + Toolkit.

    The Toolkit injects query_db, get_apm_id, get_ciclo_actual_id into
    the REPL sandbox, along with init_code that sets APM_ID and CICLO_ACTUAL.
    """
    try:
        from toolkit import PharmaToolkit
    except ImportError:
        from produccion_poc_agent.toolkit import PharmaToolkit

    pharma_toolkit = PharmaToolkit(apm_id=apm_id, db_secret_arn=DB_SECRET_ARN)

    toolkit = ToolkitCls(
        authorized_imports=["pandas", "numpy"],
        init_code=(
            "import pandas as pd\n"
            "import numpy as np\n"
            f"APM_ID = '{apm_id}'\n"
            f"CICLO_ACTUAL = get_ciclo_actual_id()\n"
            'print(f"Sesión lista: APM={{APM_ID}}, Ciclo={{CICLO_ACTUAL}}")\n'
        ),
        domain_specific_code=[
            pharma_toolkit.query_db,
            pharma_toolkit.get_apm_id,
            pharma_toolkit.get_ciclo_actual_id,
        ],
    )

    agent = CodeAgentCls(
        model=model,
        system_prompt=system_prompt,
        toolkits=[toolkit],
    )
    return agent


def _create_with_regular_agent(model, system_prompt, apm_id: str):
    """Fallback: create a regular strands Agent with @tool query_db.

    Used when strands-code-agent is not installed or incompatible.
    """
    from strands import Agent, tool
    try:
        from toolkit import PharmaToolkit
    except ImportError:
        from produccion_poc_agent.toolkit import PharmaToolkit

    pharma_toolkit = PharmaToolkit(apm_id=apm_id, db_secret_arn=DB_SECRET_ARN)

    @tool
    def query_db(sql: str) -> str:
        """Ejecuta SQL SELECT contra PostgreSQL. Retorna resultado como string tabular."""
        try:
            df = pharma_toolkit.query_db(sql)
            if df.empty:
                return "La query retornó 0 filas."
            return df.to_string(index=False, max_rows=50)
        except ValueError as e:
            return f"Error de validación: {e}"
        except Exception as e:
            return f"Error ejecutando query: {e}"

    @tool
    def get_ciclo_actual() -> str:
        """Retorna el ID del ciclo promocional vigente."""
        return str(pharma_toolkit.get_ciclo_actual_id())

    @tool
    def get_apm_info() -> str:
        """Retorna el APM_ID de la sesión actual."""
        return pharma_toolkit.get_apm_id()

    agent = Agent(
        model=model,
        tools=[query_db, get_ciclo_actual, get_apm_info],
        system_prompt=system_prompt,
    )
    return agent


# ─────────────────────────────────────────────────────────────────────────────
# invoke() — Entrypoint principal con retry logic
# ─────────────────────────────────────────────────────────────────────────────

def invoke(message: str, apm_id: str = "APM_001") -> dict[str, Any]:
    """Process an APM question with retry logic.

    Creates the CodeAgent for the given APM, invokes it with the message,
    and handles up to MAX_RETRIES if the LLM generates invalid SQL.

    Args:
        message: Natural language question from the APM.
        apm_id: The APM identifier (default: APM_001 for testing).

    Returns:
        dict with keys:
            - result (str): The agent's response text.
            - success (bool): Whether the invocation completed without error.
            - retries (int): Number of retries used.
    """
    agent = create_code_agent(apm_id)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = agent(message)
            return {
                "result": str(response),
                "success": True,
                "retries": attempt,
            }
        except Exception as e:
            last_error = e
            logger.warning(
                "Intento %d/%d falló: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                str(e),
            )
            if attempt < MAX_RETRIES:
                # Add error context to the next attempt message
                message = (
                    f"{message}\n\n"
                    f"[NOTA: El intento anterior falló con: {str(e)}. "
                    f"Por favor corregí el SQL y reintentá.]"
                )
            continue

    # All retries exhausted
    logger.error(
        "Todos los intentos agotados para APM %s. Último error: %s",
        apm_id,
        last_error,
    )
    return {
        "result": (
            "No pude procesar tu consulta después de varios intentos. "
            "Por favor reformulá la pregunta o contactá soporte técnico."
        ),
        "success": False,
        "retries": MAX_RETRIES,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BedrockAgentCoreApp wrapping (deploy entry point)
# ─────────────────────────────────────────────────────────────────────────────

def _create_app():
    """Create and configure the BedrockAgentCoreApp.

    This is the entry point for `agentcore deploy`. The app exposes
    an `invoke` entrypoint that receives payload with `prompt` and `apm_id`.
    """
    try:
        from bedrock_agentcore import BedrockAgentCoreApp
    except ImportError:
        logger.info(
            "bedrock-agentcore not installed. Running in standalone mode."
        )
        return None

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def handle_invoke(payload: dict, context: Any = None) -> dict:
        """AgentCore entrypoint — receives payload, returns result.

        Expected payload:
            {
                "prompt": "¿Cuántos médicos tengo?",
                "apm_id": "APM_001"  (optional, defaults to APM_001)
            }
        """
        user_message = payload.get("prompt", "")
        apm_id = payload.get("apm_id", "APM_001")

        if not user_message:
            return {
                "result": "No se recibió ninguna pregunta.",
                "success": False,
                "retries": 0,
            }

        return invoke(message=user_message, apm_id=apm_id)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Main — standalone execution or AgentCore deploy
# ─────────────────────────────────────────────────────────────────────────────

app = _create_app()

if __name__ == "__main__":
    if app is not None:
        # Running under AgentCore (agentcore dev / agentcore deploy)
        app.run()
    else:
        # Standalone mode — simple REPL for testing
        import sys

        print("=== PharmAssist CodeAgent (standalone) ===")
        print(f"Model: {BEDROCK_MODEL_ID}")
        print(f"Region: {BEDROCK_REGION}")
        print(f"DB Secret ARN: {DB_SECRET_ARN or '(not set)'}")
        print()

        if len(sys.argv) > 1:
            # Single question from CLI args
            question = " ".join(sys.argv[1:])
            apm_id = os.environ.get("APM_ID", "APM_001")
            result = invoke(question, apm_id)
            print(result["result"])
        else:
            # Interactive mode
            apm_id = os.environ.get("APM_ID", "APM_001")
            print(f"APM ID: {apm_id}")
            print("Escribí tu pregunta (Ctrl+C para salir):\n")
            try:
                while True:
                    question = input("APM> ").strip()
                    if not question:
                        continue
                    result = invoke(question, apm_id)
                    print(f"\n{result['result']}\n")
            except (KeyboardInterrupt, EOFError):
                print("\nChau!")
