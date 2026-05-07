"""
Abstract base class for all sub-agents.
Every agent (Word, Excel, Outlook, VS Code) inherits from this.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Standardized result from any agent action."""
    success: bool
    message: str
    output_file: str | None = None   # path if a file was created/modified
    data: Any = None                 # extra structured data


class BaseAgent(ABC):
    """
    Abstract base for sub-agents.
    Subclasses must define `name`, `capabilities`, and implement `execute`.
    """

    name: str = "base"
    description: str = "Base agent"
    capabilities: list[str] = []

    @abstractmethod
    def execute(self, action: str, args: dict) -> AgentResult:
        """
        Execute an action with given arguments.
        Returns an AgentResult.
        """
        ...

    def get_capability_info(self) -> dict:
        """Return info about this agent for the LLM context."""
        return {
            "name": self.name,
            "description": self.description,
            "actions": self.capabilities,
        }

    def _validate_action(self, action: str) -> bool:
        if action not in self.capabilities:
            raise ValueError(
                f"Agent '{self.name}' does not support action '{action}'. "
                f"Available: {self.capabilities}"
            )
        return True
