"""
Short-term memory and file awareness for the orchestrator.
Keeps track of current task context, step results, and files created.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileRecord:
    """Metadata about a file created during the session."""
    path: str
    file_type: str          # e.g. "docx", "xlsx", "py"
    created_at: float = field(default_factory=time.time)
    size_bytes: int = 0
    created_by_step: int = -1

    def refresh_size(self):
        if os.path.exists(self.path):
            self.size_bytes = os.path.getsize(self.path)


class ShortTermMemory:
    """
    Maintains context for a single task execution.
    Resets between tasks.
    """

    def __init__(self):
        self.task_goal: str = ""
        self.conversation: list[dict] = []      # {"role": ..., "content": ...}
        self.step_results: list[dict] = []       # ordered results per step
        self.files: list[FileRecord] = []        # files created this session
        self.errors: list[str] = []              # errors encountered
        self._start_time: float = 0.0

    # ── lifecycle ────────────────────────────

    def start_task(self, goal: str):
        self.reset()
        self.task_goal = goal
        self._start_time = time.time()

    def reset(self):
        self.task_goal = ""
        self.conversation.clear()
        self.step_results.clear()
        self.files.clear()
        self.errors.clear()
        self._start_time = 0.0

    # ── recording ────────────────────────────

    def record_step(self, step_id: int, tool: str, action: str,
                    result: Any, success: bool, output_file: str | None = None):
        entry = {
            "step_id": step_id,
            "tool": tool,
            "action": action,
            "success": success,
            "result_summary": str(result)[:500],
            "timestamp": time.time(),
        }
        self.step_results.append(entry)

        if output_file and os.path.exists(output_file):
            ext = os.path.splitext(output_file)[1].lstrip(".")
            rec = FileRecord(
                path=output_file,
                file_type=ext,
                created_by_step=step_id,
            )
            rec.refresh_size()
            self.files.append(rec)

        if not success:
            self.errors.append(f"Step {step_id} ({tool}.{action}): {result}")

    def add_conversation(self, role: str, content: str):
        self.conversation.append({"role": role, "content": content})

    # ── context for LLM ─────────────────────

    def build_context_summary(self) -> str:
        """Build a concise summary for injection into the LLM prompt."""
        lines = [f"Current goal: {self.task_goal}"]

        if self.files:
            lines.append("\nFiles created so far:")
            for f in self.files:
                lines.append(f"  - {os.path.basename(f.path)} ({f.file_type}, "
                             f"{f.size_bytes} bytes, step {f.created_by_step})")

        if self.step_results:
            lines.append(f"\nCompleted steps: {len(self.step_results)}")
            last = self.step_results[-1]
            status = "✅" if last["success"] else "❌"
            lines.append(f"  Last: step {last['step_id']} "
                         f"({last['tool']}.{last['action']}) {status}")

        if self.errors:
            lines.append(f"\n⚠ Errors ({len(self.errors)}):")
            for e in self.errors[-3:]:          # last 3
                lines.append(f"  - {e[:200]}")

        elapsed = time.time() - self._start_time if self._start_time else 0
        lines.append(f"\nElapsed: {elapsed:.1f}s")

        return "\n".join(lines)

    def get_file_paths(self) -> list[str]:
        """Return all file paths created during this session."""
        return [f.path for f in self.files]

    def get_last_output_file(self) -> str | None:
        """Return the most recently created file path, or None."""
        return self.files[-1].path if self.files else None
