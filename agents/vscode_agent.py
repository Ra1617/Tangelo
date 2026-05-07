"""
VS Code Agent — Creates code files, opens them in VS Code, and runs code.
"""

import os
import subprocess
import logging

from agents.base_agent import BaseAgent, AgentResult
from config import OUTPUT_DIR

logger = logging.getLogger("vscode_agent")

# Language → file extension mapping
LANG_EXT = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "html": ".html",
    "css": ".css",
    "java": ".java",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
    "go": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "bash": ".sh",
    "powershell": ".ps1",
    "sql": ".sql",
    "json": ".json",
    "yaml": ".yml",
    "markdown": ".md",
    "xml": ".xml",
    "text": ".txt",
}

# Language → run command mapping
LANG_RUN = {
    "python": "python",
    "javascript": "node",
    "typescript": "npx ts-node",
    "bash": "bash",
    "powershell": "powershell -File",
}


class VSCodeAgent(BaseAgent):
    name = "vscode"
    description = "Create code files, open in VS Code, and run code"
    capabilities = ["create_code_file", "open_in_editor", "run_code"]

    def execute(self, action: str, args: dict) -> AgentResult:
        self._validate_action(action)

        if action == "create_code_file":
            return self._create_code_file(**args)
        elif action == "open_in_editor":
            return self._open_in_editor(**args)
        elif action == "run_code":
            return self._run_code(**args)

        return AgentResult(success=False, message=f"Unknown action: {action}")

    # ── Actions ──────────────────────────────

    def _create_code_file(self, filename: str, language: str, content: str) -> AgentResult:
        """Create a source code file."""
        try:
            if not filename:
                import time
                filename = f"generated_code_{int(time.time())}.txt"
            if not language:
                language = "txt"
            if not content:
                content = ""

            # Ensure correct extension
            ext = LANG_EXT.get(language.lower(), "")
            if ext and not filename.endswith(ext):
                filename += ext

            # Create in a 'code' subdirectory to keep things organized
            code_dir = os.path.join(OUTPUT_DIR, "code")
            os.makedirs(code_dir, exist_ok=True)
            path = os.path.join(code_dir, filename)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info("Created code file: %s", path)
            return AgentResult(
                success=True,
                message=f"✅ Code file created: {filename} ({language})",
                output_file=path
            )

        except Exception as e:
            logger.exception("Failed to create code file")
            return AgentResult(success=False, message=f"❌ Code file error: {e}")

    def _open_in_editor(self, filepath: str) -> AgentResult:
        """Open a file in VS Code."""
        try:
            # Resolve relative paths
            if not os.path.isabs(filepath):
                filepath = os.path.join(OUTPUT_DIR, filepath)

            if not os.path.exists(filepath):
                # Try in code subdirectory
                alt = os.path.join(OUTPUT_DIR, "code", os.path.basename(filepath))
                if os.path.exists(alt):
                    filepath = alt
                else:
                    return AgentResult(success=False, message=f"❌ File not found: {filepath}")

            # Launch VS Code
            subprocess.Popen(
                ["code", filepath],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("Opened in VS Code: %s", filepath)
            return AgentResult(
                success=True,
                message=f"✅ Opened in VS Code: {os.path.basename(filepath)}",
                output_file=filepath
            )

        except FileNotFoundError:
            return AgentResult(
                success=False,
                message="❌ VS Code CLI ('code') not found. Is VS Code installed?"
            )
        except Exception as e:
            logger.exception("Failed to open in editor")
            return AgentResult(success=False, message=f"❌ Editor error: {e}")

    def _run_code(self, filepath: str) -> AgentResult:
        """Execute a code file and capture output."""
        try:
            if not os.path.isabs(filepath):
                filepath = os.path.join(OUTPUT_DIR, "code", filepath)

            if not os.path.exists(filepath):
                return AgentResult(success=False, message=f"❌ File not found: {filepath}")

            # Determine language from extension
            ext = os.path.splitext(filepath)[1].lower()
            ext_to_lang = {v: k for k, v in LANG_EXT.items()}
            lang = ext_to_lang.get(ext, "")
            run_cmd = LANG_RUN.get(lang)

            if not run_cmd:
                return AgentResult(
                    success=False,
                    message=f"❌ Don't know how to run {ext} files"
                )

            # Execute with timeout
            cmd = f"{run_cmd} \"{filepath}\""
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.dirname(filepath),
            )

            output = result.stdout or ""
            errors = result.stderr or ""

            if result.returncode == 0:
                logger.info("Code executed successfully: %s", filepath)
                msg = f"✅ Code executed successfully\n\nOutput:\n{output[:2000]}"
                if errors:
                    msg += f"\n\nWarnings:\n{errors[:500]}"
                return AgentResult(
                    success=True,
                    message=msg,
                    data={"output": output, "return_code": 0}
                )
            else:
                logger.warning("Code execution failed: %s", filepath)
                return AgentResult(
                    success=False,
                    message=f"❌ Code execution failed (exit code {result.returncode})\n\n{errors[:2000]}",
                    data={"output": output, "errors": errors, "return_code": result.returncode}
                )

        except subprocess.TimeoutExpired:
            return AgentResult(success=False, message="❌ Code execution timed out (30s limit)")
        except Exception as e:
            logger.exception("Failed to run code")
            return AgentResult(success=False, message=f"❌ Run error: {e}")
