"""
AI Office Assistant — Central Configuration
All settings in one place. Override via environment variables.
"""

import os

# ─────────────────────────────────────────────
#  OLLAMA / LLM
# ─────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# ─────────────────────────────────────────────
#  FastAPI
# ─────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ─────────────────────────────────────────────
#  OUTPUT
# ─────────────────────────────────────────────
OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR",
    os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "Ideaphilip")
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
LOG_DIR = os.path.join(OUTPUT_DIR, "_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ─────────────────────────────────────────────
#  AGENT SETTINGS
# ─────────────────────────────────────────────
MAX_AGENT_ITERATIONS = 10          # Safety cap for the agentic loop
AGENT_THINK_TIMEOUT  = 120         # Seconds to wait for Ollama response
