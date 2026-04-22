"""
app/services/memory.py

In-memory store for chat history and previous queries.
Phase 1: plain Python dict keyed by session_id.
Phase 2 (TODO): swap _store reads/writes for Supabase table calls.
"""
from typing import List

_store: dict = {}

def get_memory(session_id: str) -> dict:
    return _store.get(session_id, {"chat_history": [], "previous_queries": []})

def upsert_memory(session_id: str, chat_history: list, previous_queries: List[str]) -> None:
    _store[session_id] = {"chat_history": chat_history, "previous_queries": previous_queries}