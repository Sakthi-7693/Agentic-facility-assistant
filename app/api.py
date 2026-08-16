"""FastAPI application - the HTTP surface of the agent."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.config import AUDIO_OUT_DIR, BASE_DIR, WEB_DIR, settings
from app.logging_setup import get_logger
from app.mcp_client.client import close_mcp_client, get_mcp_client
from app.orchestrator import get_orchestrator
from app.rag.vector_store import get_vector_store
from app.session import session_store
from app.tracing import flush, init_tracing
from app.voice.tts import cleanup_old_audio

log = get_logger(__name__)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the index, connect to MCP and start tracing; clean up on exit."""
    log.info("Nectar Autonomous Facility Agent - starting up")

    # Fail loudly at boot rather than with a confusing 401 on the first request.
    if settings.llm_provider != "ollama" and not settings.llm_api_key.startswith(
        ("gsk_", "sk-", "AIza")
    ):
        log.error("=" * 62)
        log.error("NO VALID API KEY. Every request will fail with a 401.")
        log.error("Expected a key in: %s", BASE_DIR / ".env")
        log.error("Set LLM_PROVIDER=ollama to run without a key.")
        log.error("=" * 62)

    init_tracing()
    log.info("Knowledge base ready: %d chunks", get_vector_store().ingest())

    mcp = await get_mcp_client()
    log.info("MCP mode=%s | tools=%s", mcp.mode, ", ".join(mcp.tool_names))

    cleanup_old_audio()
    log.info("Ready -> http://127.0.0.1:8000")

    yield

    log.info("Shutting down")
    await close_mcp_client()
    flush()


app = FastAPI(
    title="Nectar Autonomous Facility Agent",
    description="Voice agent with LLM routing, RAG and MCP tools.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    page = WEB_DIR / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>UI not found</h1><p>Expected web/index.html</p>", 404)
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    """Typed message in, agent reply out."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    result = await get_orchestrator().handle_text(request.message, request.session_id)
    return result.as_dict()


@app.post("/api/voice")
async def voice(
    audio: UploadFile = File(...),
    session_id: str | None = Body(default=None),
) -> dict:
    """Recorded audio in, agent reply plus synthesised speech out."""
    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty audio upload")

    result = await get_orchestrator().handle_audio(payload, session_id)
    return result.as_dict()


@app.get("/api/audio/{filename}")
async def get_audio(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid file name")

    path = AUDIO_OUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/session/reset")
async def reset_session(session_id: str = Body(..., embed=True)) -> dict:
    session_store.reset(session_id)
    return {"ok": True}


@app.get("/api/service-requests")
async def service_requests() -> dict:
    """Current maintenance tickets. The UI polls this after every turn so a
    newly raised ticket appears without the user asking for it."""
    mcp = await get_mcp_client()
    return await mcp.call("list_service_requests", {})


@app.get("/api/tools")
async def list_tools() -> dict:
    """Live MCP tool documentation, generated from the running server."""
    mcp = await get_mcp_client()
    return {
        "mode": mcp.mode,
        "count": len(mcp.tool_names),
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "parameters": t["function"]["parameters"],
                "write_action": mcp.is_write_tool(t["function"]["name"]),
            }
            for t in mcp.openai_tools()
        ],
    }


@app.get("/health")
async def health() -> dict:
    mcp = await get_mcp_client()
    return {
        "status": "ok",
        # Which interpreter is actually serving. On Windows a venv launcher
        # spawns the base interpreter, so the process list is misleading -
        # this tells you unambiguously whether the venv is in use.
        "python": {"executable": sys.executable, "env": sys.prefix},
        "llm_provider": settings.llm_provider,
        "models": {"fast": settings.fast_model, "smart": settings.smart_model},
        "mcp_mode": mcp.mode,
        "mcp_tools": len(mcp.tool_names),
        "kb_chunks": get_vector_store().count(),
        "tracing": settings.tracing_enabled,
        "active_sessions": session_store.count(),
    }
