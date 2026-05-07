"""
AI Office Assistant — Entry Point
Launches the FastAPI server in a background thread,
then starts the Tkinter GUI on the main thread.
"""

import sys
import os
import threading
import logging
import time

# ── Make sure project root is on path ────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# ── Logging setup ────────────────────────────
from config import LOG_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-14s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "assistant.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("main")


# ─────────────────────────────────────────────
#  FAST API SERVER (background thread)
# ─────────────────────────────────────────────

def start_api():
    """Run the FastAPI server via uvicorn in a background thread."""
    from config import API_HOST, API_PORT
    import uvicorn
    from api.server import app

    logger.info("Starting FastAPI server on %s:%s", API_HOST, API_PORT)
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="warning",     # keep console clean
        access_log=False,
    )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    logger.info("=" * 50)
    logger.info("AI Office Assistant starting...")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("=" * 50)

    # Start FastAPI in background
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()

    # Give the server a moment to start
    time.sleep(1.5)
    logger.info("FastAPI server thread launched")

    # Launch Tkinter GUI on main thread
    from gui.app import AgentOSApp
    app = AgentOSApp()

    logger.info("GUI launched — ready to accept commands")
    app.mainloop()

    logger.info("Application closed")


if __name__ == "__main__":
    main()
