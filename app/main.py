"""
app/main.py  — FastAPI entry point

Endpoints:
  POST   /api/query
  POST   /api/upload
  GET    /api/history/{session_id}
  DELETE /api/history/{session_id}
  GET    /api/sessions
  GET    /api/health
"""

import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from app.graph.builder import graph_app
from app.graph.state import GraphState, initial_state, reset_turn
from app.services.memory import get_memory, upsert_memory, delete_memory, list_sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("═══ AI Assistant starting (persistent memory via Supabase) ═══")
    yield
    logger.info("═══ AI Assistant shut down ═══")


app = FastAPI(
    title="LangGraph × Supabase AI Assistant",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    filter_source: Optional[str] = None


class QueryResponse(BaseModel):
    session_id: str
    answer: str
    intent: Optional[str] = None
    sources: list = []
    awaiting_clarification: bool = False
    turn: int = 0


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    chunks_ingested: int
    message: str


class HistoryResponse(BaseModel):
    session_id: str
    turns: int
    chat_history: list
    previous_queries: list


# ── In-process session state cache ───────────────────────────────────────────
_sessions: dict = {}


def _get_or_create_state(session_id: str) -> GraphState:
    if session_id not in _sessions:
        _sessions[session_id] = initial_state(session_id)
    return _sessions[session_id]


# ── POST /api/query ───────────────────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(body: QueryRequest):
    session_id = body.session_id or str(uuid.uuid4())
    logger.info("[/api/query] session=%s  query=%r", session_id, body.query[:80])

    existing = _get_or_create_state(session_id)
    state = reset_turn(existing, new_query=body.query)
    state["input_type"] = "text"
    if body.filter_source:
        state["retrieval_filter"] = {"source": body.filter_source}

    try:
        result: GraphState = graph_app.invoke(state)
    except Exception as exc:
        logger.exception("[/api/query] Graph error")
        raise HTTPException(status_code=500, detail=str(exc))

    _sessions[session_id] = result
    sources = list({c["source"] for c in (result.get("retrieved_chunks") or [])})
    turn_count = len(result.get("chat_history", [])) // 2

    return QueryResponse(
        session_id=session_id,
        answer=result.get("final_answer") or "",
        intent=result.get("intent"),
        sources=sources,
        awaiting_clarification=result.get("awaiting_clarification", False),
        turn=turn_count,
    )


# ── POST /api/upload ──────────────────────────────────────────────────────────

@app.post("/api/upload", response_model=UploadResponse)
async def upload_endpoint(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(default=None),
    query: Optional[str] = Form(default=None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files accepted.")

    session_id = session_id or str(uuid.uuid4())
    tmp_dir  = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, file.filename)

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        existing = _get_or_create_state(session_id)
        state = reset_turn(existing, new_query=query or "")
        state["input_type"] = "pdf"
        state["pdf_path"]   = tmp_path

        result: GraphState = graph_app.invoke(state)
        _sessions[session_id] = result

        from app.utils.pdf_loader import extract_text_from_pdf
        from app.utils.chunking   import chunk_text
        raw    = extract_text_from_pdf(tmp_path)
        chunks = chunk_text(raw)
        chunk_count = len(chunks)

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("[/api/upload] failed")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        chunks_ingested=chunk_count,
        message=f"'{file.filename}' ingested ({chunk_count} chunks). Use filter_source='{file.filename}' to query it.",
    )


# ── GET /api/history/{session_id} ────────────────────────────────────────────

@app.get("/api/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str):
    mem = get_memory(session_id)
    if not mem["chat_history"] and session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return HistoryResponse(
        session_id=session_id,
        turns=len(mem["chat_history"]) // 2,
        chat_history=mem["chat_history"],
        previous_queries=mem["previous_queries"],
    )


# ── DELETE /api/history/{session_id} ─────────────────────────────────────────

@app.delete("/api/history/{session_id}")
async def clear_history(session_id: str):
    delete_memory(session_id)
    _sessions.pop(session_id, None)
    return {"message": f"Session '{session_id}' cleared."}


# ── GET /api/sessions ─────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def get_sessions():
    return {"sessions": list_sessions()}


# ── GET /api/health ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "memory": "supabase",
        "active_sessions": len(_sessions),
    }