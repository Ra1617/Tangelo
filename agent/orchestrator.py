"""
Orchestrator Agent — The brain of the system.
Implements the agentic think → act → observe → update loop using LangGraph.
Delegates tasks to sub-agents via the tool registry.
"""

import time
import logging
from typing import Callable, TypedDict, Any

from langgraph.graph import StateGraph, END

from config import MAX_AGENT_ITERATIONS
from agent.memory import ShortTermMemory
from agent.planner import (
    Plan, StepStatus,
    create_plan, replan, _call_ollama
)
from tools.registry import execute_tool

logger = logging.getLogger("orchestrator")


# ─────────────────────────────────────────────
#  STATUS CALLBACK TYPE
# ─────────────────────────────────────────────

StatusCallback = Callable[[str, str, dict | None], None]

def _noop_callback(phase: str, message: dict | None, data: dict | None = None):
    pass


# ─────────────────────────────────────────────
#  LANGGRAPH STATE
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    prompt: str
    plan: Any
    iteration: int
    current_result: Any
    last_step_success: bool
    last_observation: str


# ─────────────────────────────────────────────
#  ORCHESTRATOR
# ─────────────────────────────────────────────

class Orchestrator:
    """
    Core agent loop powered by LangGraph.
    """

    def __init__(self):
        self.memory = ShortTermMemory()
        self._status_cb: StatusCallback = _noop_callback
        self._build_graph()

    def set_status_callback(self, cb: StatusCallback):
        """Set a callback for live status updates (used by GUI)."""
        self._status_cb = cb or _noop_callback

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("planner_node", self._node_planner)
        workflow.add_node("actor_node", self._node_actor)
        workflow.add_node("observer_node", self._node_observer)
        workflow.add_node("replanner_node", self._node_replanner)

        workflow.set_entry_point("planner_node")
        
        def plan_router(state: AgentState) -> str:
            plan = state.get("plan")
            if not plan:
                return END
            if plan.is_complete() or state.get("iteration", 0) >= MAX_AGENT_ITERATIONS:
                return END
            return "actor_node"
            
        workflow.add_conditional_edges("planner_node", plan_router)
        workflow.add_edge("actor_node", "observer_node")
        
        def observer_router(state: AgentState) -> str:
            if not state.get("last_step_success", True):
                return "replanner_node"
            plan = state.get("plan")
            if not plan or plan.is_complete() or state.get("iteration", 0) >= MAX_AGENT_ITERATIONS:
                return END
            return "actor_node"
            
        workflow.add_conditional_edges("observer_node", observer_router)
        workflow.add_edge("replanner_node", "actor_node")
        
        self.graph = workflow.compile()

    # ── LANGGRAPH NODES ──────────────────────

    def _node_planner(self, state: AgentState) -> dict:
        self._status_cb("planning", "🧠 Creating execution plan...", None)
        try:
            plan = create_plan(state["prompt"], self.memory.build_context_summary())
            self._status_cb(
                "plan_ready",
                f"📋 Plan created: {len(plan.steps)} steps",
                {"plan": plan.summary()}
            )
            logger.info("Plan created: %s", plan.to_json())
            return {"plan": plan, "iteration": 0}
        except Exception as e:
            logger.exception("Planning failed")
            self._status_cb("error", f"❌ Planning failed: {e}", None)
            return {"plan": None}

    def _node_actor(self, state: AgentState) -> dict:
        plan = state["plan"]
        iteration = state.get("iteration", 0) + 1
        step = plan.current_step()
        if not step:
            return {"iteration": iteration}
            
        step.status = StepStatus.RUNNING
        step.started_at = time.time()

        self._status_cb(
            "thinking",
            f"🧠 Thinking about step {step.id}: {step.tool}.{step.action}...",
            {"step": step.to_dict()}
        )

        self._status_cb(
            "acting",
            f"🔧 Executing: {step.tool}.{step.action}",
            {"step": step.to_dict()}
        )

        resolved_args = plan.resolve_args(step)
        result = execute_tool(step.tool, step.action, resolved_args)
        
        step.finished_at = time.time()
        return {"iteration": iteration, "current_result": result}

    def _node_observer(self, state: AgentState) -> dict:
        plan = state["plan"]
        step = plan.current_step()
        result = state.get("current_result")
        
        if not step or not result:
            return {}

        elapsed = step.finished_at - step.started_at
        
        if result.success:
            step.status = StepStatus.SUCCESS
            step.output = result.output_file or result.message
            self._status_cb(
                "observing",
                f"👁 Step {step.id} succeeded ({elapsed:.1f}s): {result.message}",
                {"step": step.to_dict(), "result": result.message}
            )
        else:
            step.status = StepStatus.FAILED
            step.error = result.message
            self._status_cb(
                "observing",
                f"⚠ Step {step.id} failed: {result.message}",
                {"step": step.to_dict(), "error": result.message}
            )
            
        self.memory.record_step(
            step_id=step.id,
            tool=step.tool,
            action=step.action,
            result=result.message,
            success=result.success,
            output_file=result.output_file,
        )
        
        observation = f"Step {step.id} ({step.tool}.{step.action}) {'FAILED' if not result.success else 'SUCCESS'}: {result.message}"
        
        plan.advance()
        
        return {"last_step_success": result.success, "last_observation": observation, "plan": plan}

    def _node_replanner(self, state: AgentState) -> dict:
        plan = state["plan"]
        observation = state["last_observation"]
        self._status_cb(
            "updating",
            f"📋 Updating plan... {plan.progress_text()}",
            {"progress": plan.progress_text()}
        )
        
        try:
            revised = replan(plan, observation, self.memory.build_context_summary())
            if revised:
                plan = revised
                self._status_cb(
                    "replanned",
                    "🔄 Plan revised based on failure",
                    {"plan": plan.summary()}
                )
        except Exception:
            logger.warning("Replan failed, continuing with original plan")
            
        return {"plan": plan}

    # ── MAIN ENTRY POINT ─────────────────────

    def execute(self, prompt: str) -> dict:
        """
        Run the full agentic loop for a user prompt via LangGraph.
        """
        self.memory.start_task(prompt)
        self._status_cb("start", f"📝 Understanding your request...", None)
        
        initial_state = {
            "prompt": prompt,
            "plan": None,
            "iteration": 0,
            "current_result": None,
            "last_step_success": True,
            "last_observation": ""
        }
        
        final_state = self.graph.invoke(initial_state)

        plan = final_state.get("plan")
        if not plan:
            msg = "❌ Planning failed or was aborted."
            # Only trigger error cb if there's no plan because planning node sends it if it hits an exception
            return {
                "success": False,
                "message": msg,
                "plan": None,
                "files_created": [],
            }

        files = self.memory.get_file_paths()
        completed = sum(1 for s in plan.steps if s.status == StepStatus.SUCCESS)
        total = len(plan.steps)

        if completed == total:
            msg = f"✅ All {total} steps completed successfully!"
        elif completed > 0:
            msg = f"⚠ {completed}/{total} steps completed. Some steps had issues."
        else:
            msg = f"❌ Task failed. No steps completed successfully."

        if files:
            msg += "\n\n📁 Files created:\n" + "\n".join(f"  • {f}" for f in files)

        self._status_cb("complete", msg, {"plan": plan.summary()})

        return {
            "success": completed > 0,
            "message": msg,
            "plan": plan.summary(),
            "files_created": files,
        }

    # ── SIMPLE CHAT (no plan needed) ─────────

    def chat(self, prompt: str) -> str:
        """Simple chat — just ask Ollama for a conversational reply."""
        messages = [
            {"role": "system", "content": (
                "You are a helpful AI office assistant. Answer the user's question. "
                "Keep responses concise and useful. If the user seems to be asking "
                "you to create a document, spreadsheet, email, or code — tell them "
                "you can do that and ask them to be specific."
            )},
        ]
        for entry in self.memory.conversation[-6:]:
            messages.append(entry)
        messages.append({"role": "user", "content": prompt})

        try:
            reply = _call_ollama(messages)
            self.memory.add_conversation("user", prompt)
            self.memory.add_conversation("assistant", reply)
            return reply
        except Exception as e:
            return f"❌ Error: {e}"

    # ── DETECT INTENT ────────────────────────

    def process(self, prompt: str) -> dict:
        self.memory.add_conversation("user", prompt)
        intent = self._classify_intent(prompt)

        if intent == "task":
            return self.execute(prompt)
        else:
            reply = self.chat(prompt)
            return {
                "success": True,
                "message": reply,
                "plan": None,
                "files_created": [],
            }

    def _classify_intent(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": (
                "Classify the user's message as either 'task' or 'chat'.\n"
                "- 'task': The user wants to CREATE, SEND, MAKE, BUILD, GENERATE, "
                "EXPORT, or DO something (e.g., create a document, send an email, "
                "make a spreadsheet, write code).\n"
                "- 'chat': The user is asking a question, having a conversation, "
                "or greeting.\n\n"
                "Respond with ONLY the word 'task' or 'chat'. Nothing else."
            )},
            {"role": "user", "content": prompt},
        ]
        try:
            reply = _call_ollama(messages).strip().lower()
            return "task" if "task" in reply else "chat"
        except Exception:
            return "task" if any(kw in prompt.lower() for kw in
                                ["create", "make", "send", "build", "generate",
                                 "write", "export", "email"]) else "chat"

    def reset(self):
        self.memory.reset()
