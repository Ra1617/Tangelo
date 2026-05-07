"""
Unified Tool Registry — auto-discovers and registers all sub-agents.
Provides tool descriptions for LLM prompt construction,
validates actions, and dispatches execution.
"""

import logging
from typing import Any

from agents.base_agent import BaseAgent, AgentResult
from agents.word_agent import WordAgent
from agents.excel_agent import ExcelAgent
from agents.outlook_agent import OutlookAgent
from agents.vscode_agent import VSCodeAgent

logger = logging.getLogger("registry")


# ─────────────────────────────────────────────
#  AGENT INSTANCES
# ─────────────────────────────────────────────

_AGENTS: dict[str, BaseAgent] = {
    "word":    WordAgent(),
    "excel":   ExcelAgent(),
    "outlook": OutlookAgent(),
    "vscode":  VSCodeAgent(),
}


# ─────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────

def get_agent(tool_name: str) -> BaseAgent | None:
    """Get an agent instance by tool name."""
    return _AGENTS.get(tool_name)


def execute_tool(tool_name: str, action: str, args: dict) -> AgentResult:
    """
    Execute a tool action.
    Returns AgentResult on success or failure.
    """
    agent = _AGENTS.get(tool_name)
    if agent is None:
        # Handle "chat" pseudo-tool (no real agent, just returns message)
        if tool_name == "chat":
            return AgentResult(
                success=True,
                message=args.get("message", "No response"),
            )
        return AgentResult(
            success=False,
            message=f"❌ Unknown tool: '{tool_name}'. Available: {list(_AGENTS.keys())}"
        )

    try:
        return agent.execute(action, args)
    except ValueError as e:
        return AgentResult(success=False, message=f"❌ {e}")
    except Exception as e:
        logger.exception("Tool execution error: %s.%s", tool_name, action)
        return AgentResult(success=False, message=f"❌ Execution error: {e}")


def get_all_capabilities() -> dict:
    """Return capabilities of all registered agents (for LLM context)."""
    return {
        name: agent.get_capability_info()
        for name, agent in _AGENTS.items()
    }


def get_tool_descriptions_for_llm() -> str:
    """Build a formatted string describing all tools for the LLM system prompt."""
    lines = []
    for name, agent in _AGENTS.items():
        lines.append(f"- {name}: {agent.description}")
        for cap in agent.capabilities:
            lines.append(f"    • {cap}")
    return "\n".join(lines)


def list_tools() -> list[str]:
    """Return list of available tool names."""
    return list(_AGENTS.keys())
