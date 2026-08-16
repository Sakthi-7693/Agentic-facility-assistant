"""
Start the application.

    python run.py

Then open http://127.0.0.1:8000 in a browser.
"""

from __future__ import annotations

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.api:app",
        host="127.0.0.1",
        port=8000,
        # Reload is off on purpose: it would restart the MCP subprocess and
        # reload the Whisper model on every file save.
        reload=False,
        log_level=settings.log_level.lower(),
    )
