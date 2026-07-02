"""System prompts for the PharmAssist unified agent."""

try:
    from agentcore.prompts.system_prompt import build_system_prompt
except ModuleNotFoundError:
    from prompts.system_prompt import build_system_prompt

__all__ = ["build_system_prompt"]
