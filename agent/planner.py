"""
JSON Execution Plan builder and manager.
Creates structured plans from LLM output, tracks step status,
and supports variable references ($stepN.output).
"""

import json
import re
import time
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import logging
from urllib.parse import urlparse

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from config import OLLAMA_URL, OLLAMA_MODEL, AGENT_THINK_TIMEOUT

logger = logging.getLogger("planner")


# ─────────────────────────────────────────────
#  DATA MODELS
# ─────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    SKIPPED   = "skipped"


@dataclass
class Step:
    id: int
    tool: str               # e.g. "excel", "word", "outlook", "vscode"
    action: str             # e.g. "create_spreadsheet", "send_email"
    args: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    output: Any = None      # result from execution
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "action": self.action,
            "args": self.args,
            "status": self.status.value,
            "output": str(self.output)[:300] if self.output else None,
            "error": self.error,
        }


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)

    # ── navigation ───────────────────────────

    def current_step(self) -> Step | None:
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance(self):
        self.current_step_index += 1

    def is_complete(self) -> bool:
        return self.current_step_index >= len(self.steps)

    # ── variable resolution ──────────────────

    def resolve_args(self, step: Step) -> dict:
        """
        Replace $stepN.output references in args with actual outputs.
        Example: {"attachments": ["$step1.output"]}  →  {"attachments": ["/path/to/file.xlsx"]}
        """
        resolved = copy.deepcopy(step.args)
        for key, value in resolved.items():
            resolved[key] = self._resolve_value(value)
        return resolved

    def _resolve_value(self, value: Any) -> Any:
        if isinstance(value, str):
            # Match $step<N>.output
            def replacer(match):
                ref_id = int(match.group(1))
                ref_step = next((s for s in self.steps if s.id == ref_id), None)
                if ref_step and ref_step.output:
                    return str(ref_step.output)
                return match.group(0)

            return re.sub(r"\$step(\d+)\.output", replacer, value)
        elif isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._resolve_value(v) for k, v in value.items()}
        return value

    # ── summary ──────────────────────────────

    def summary(self) -> dict:
        return {
            "goal": self.goal,
            "total_steps": len(self.steps),
            "completed": sum(1 for s in self.steps if s.status == StepStatus.SUCCESS),
            "failed": sum(1 for s in self.steps if s.status == StepStatus.FAILED),
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.summary(), indent=2)

    def progress_text(self) -> str:
        done = sum(1 for s in self.steps if s.status in (StepStatus.SUCCESS, StepStatus.FAILED, StepStatus.SKIPPED))
        return f"{done}/{len(self.steps)} steps complete"


# ─────────────────────────────────────────────
#  PLANNER — calls Ollama to generate plans
# ─────────────────────────────────────────────

PLAN_SYSTEM_PROMPT = """You are a planning agent. Given a user request, produce a JSON execution plan.

Available tools and actions:
- word: create_document(filename, title, content), add_table(filename, headers, rows), export_pdf(filename)
- excel: create_spreadsheet(filename, sheet_name, headers, rows), add_data(filename, sheet_name, rows), add_chart(filename, sheet_name, chart_type, data_range), apply_formatting(filename, sheet_name, style)
- outlook: send_email(to, subject, body, attachments)
- vscode: create_code_file(filename, language, content), open_in_editor(filepath), run_code(filepath)

Respond ONLY with valid JSON in this exact format:
{{
  "goal": "<short description>",
  "steps": [
    {{"id": 1, "tool": "<tool_name>", "action": "<action_name>", "args": {{ ... }}}},
    {{"id": 2, "tool": "<tool_name>", "action": "<action_name>", "args": {{ ... }}}}
  ]
}}

Rules:
- Generate realistic, meaningful content in args (not placeholders).
- Use descriptive filenames.
- Steps execute in order. You can reference previous step outputs with $stepN.output (e.g. $step1.output for the file created in step 1).
- For email attachments, use $stepN.output to attach files created in earlier steps.
- Respond with ONLY the JSON. No extra text.
"""


def _get_llm() -> ChatOllama:
    parsed = urlparse(OLLAMA_URL)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return ChatOllama(
        model=OLLAMA_MODEL, 
        base_url=base_url, 
        temperature=0, 
        timeout=AGENT_THINK_TIMEOUT
    )

def _call_ollama(messages: list) -> str:
    """Call Ollama via LangChain and return the raw response text."""
    llm = _get_llm()
    lc_messages = []
    for m in messages:
        if m["role"] == "system":
            lc_messages.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))
                
    try:
        response = llm.invoke(lc_messages)
        return response.content
    except Exception as e:
        logger.exception("LangChain Ollama error")
        raise RuntimeError(f"Ollama error: {e}")


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    clean = text.strip()
    # Strip ```json ... ``` fences
    if clean.startswith("```"):
        lines = clean.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        clean = "\n".join(lines).strip()
    return json.loads(clean)


def create_plan(prompt: str, memory_context: str = "") -> Plan:
    """ Ask Ollama to generate a structured execution plan from the user prompt. """
    
    if memory_context:
        prompt_tmpl = ChatPromptTemplate.from_messages([
            ("system", PLAN_SYSTEM_PROMPT),
            ("system", "Current context:\n{memory_context}"),
            ("user", "{prompt}")
        ])
        messages = prompt_tmpl.format_messages(memory_context=memory_context, prompt=prompt)
    else:
        prompt_tmpl = ChatPromptTemplate.from_messages([
            ("system", PLAN_SYSTEM_PROMPT),
            ("user", "{prompt}")
        ])
        messages = prompt_tmpl.format_messages(prompt=prompt)

    try:
        response = _get_llm().invoke(messages)
        raw = response.content
    except Exception as e:
        logger.error(f"Failed to call Langchain Ollama: {e}")
        raise ConnectionError(f"Cannot connect to Ollama. Make sure it is running. Error: {e}")

    logger.info("Plan LangChain response: %s", raw[:1000])

    try:
        data = _extract_json(raw)
    except json.JSONDecodeError:
        # Fallback: try to create a simple single-step plan
        logger.warning("Failed to parse plan JSON, creating fallback chat plan")
        return Plan(
            goal=prompt,
            steps=[Step(id=1, tool="chat", action="respond", args={"message": raw})]
        )

    # Build Plan object
    goal = data.get("goal", prompt)
    steps = []
    for s in data.get("steps", []):
        steps.append(Step(
            id=s.get("id", len(steps) + 1),
            tool=s.get("tool", "unknown"),
            action=s.get("action", "unknown"),
            args=s.get("args", {}),
        ))

    if not steps:
        steps = [Step(id=1, tool="chat", action="respond", args={"message": raw})]

    return Plan(goal=goal, steps=steps)


def replan(plan: Plan, observation: str, memory_context: str = "") -> Plan | None:
    """
    Ask the LLM whether the remaining plan needs revision based on an observation.
    Returns a new Plan with remaining steps, or None if no changes needed.
    """
    remaining = [s.to_dict() for s in plan.steps if s.status == StepStatus.PENDING]
    if not remaining:
        return None

    prompt_tmpl = ChatPromptTemplate.from_messages([
        ("system", PLAN_SYSTEM_PROMPT),
        ("system", "Context:\n{memory_context}"),
        ("user", "Original goal: {goal}\n\nLast observation: {observation}\n\nRemaining steps: {remaining}\n\nIf the remaining steps are still correct, respond with exactly: NO_CHANGE\nOtherwise, respond with the revised remaining steps as JSON.")
    ])
    messages = prompt_tmpl.format_messages(
        memory_context=memory_context,
        goal=plan.goal,
        observation=observation,
        remaining=json.dumps(remaining, indent=2)
    )

    try:
        response = _get_llm().invoke(messages)
        raw = response.content
    except Exception:
        raw = "NO_CHANGE"

    if "NO_CHANGE" in raw.strip():
        return None

    try:
        data = _extract_json(raw)
        new_steps = []
        for s in data.get("steps", []):
            new_steps.append(Step(
                id=s.get("id", len(new_steps) + 1),
                tool=s.get("tool", "unknown"),
                action=s.get("action", "unknown"),
                args=s.get("args", {}),
            ))
        if new_steps:
            # Replace remaining pending steps
            completed = [s for s in plan.steps if s.status != StepStatus.PENDING]
            plan.steps = completed + new_steps
            plan.current_step_index = len(completed)
            return plan
    except Exception:
        logger.warning("Replan failed to parse, keeping original plan")

    return None
