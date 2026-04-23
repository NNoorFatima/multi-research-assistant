"""
app/graph/nodes.py

All 7 node functions for the LangGraph AI assistant.
Each function signature: (state: GraphState) -> dict  (partial state update)

Nodes:
  1. input_node
  2. intent_classifier_node
  3. retriever_node
  4. decision_node          (router — returns routing string, not dict)
  5. answer_generator_node
  6. clarification_node
  7. memory_update_node
"""

import os
import json
import logging
from typing import Literal

from groq import Groq
from dotenv import load_dotenv

from app.graph.state import GraphState, Message
from app.services.retriever import retrieve_chunks
from app.services.memory import get_memory, upsert_memory
from app.utils.pdf_loader import extract_text_from_pdf
from app.utils.chunking import chunk_text
from app.services.embeddings import embed_and_upsert

load_dotenv()
logger = logging.getLogger(__name__)

# ── Groq client (shared across nodes) ───────────────────────────────────────
_groq = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_MODEL = "llama-3.1-8b-instant"   # fast, free-tier friendly


def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    """Thin wrapper around Groq chat completion."""
    resp = _groq.chat.completions.create(
        model=GROQ_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. INPUT NODE
# ─────────────────────────────────────────────────────────────────────────────

def input_node(state: GraphState) -> dict:
    """
    Entry point of the graph.

    Responsibilities:
      - If input_type == 'pdf': extract text, chunk, embed, upsert into Supabase
      - If input_type == 'text': pass through; load existing memory for session
      - Load chat_history + previous_queries from memory store
    """
    logger.info("[input_node] session=%s type=%s", state["session_id"], state["input_type"])

    updates: dict = {}

    # ── PDF ingestion path ───────────────────────────────────────
    if state["input_type"] == "pdf" and state.get("pdf_path"):
        try:
            raw_text = extract_text_from_pdf(state["pdf_path"])
            chunks = chunk_text(raw_text, chunk_size=500, overlap=50)
            source_name = os.path.basename(state["pdf_path"])
            embed_and_upsert(chunks, source=source_name)
            logger.info("[input_node] Ingested %d chunks from %s", len(chunks), source_name)
            # After ingestion the user's query is typically "I uploaded a PDF"
            # so we set a helpful synthetic query if none was provided
            if not state["query"].strip():
                updates["query"] = f"I just uploaded '{source_name}'. Please confirm it was processed."
        except Exception as exc:
            logger.error("[input_node] PDF ingestion failed: %s", exc)
            updates["error"] = f"PDF ingestion failed: {exc}"

    # ── Load memory ───────────────────────────────────────────────
    mem = get_memory(state["session_id"])
    updates["chat_history"] = mem.get("chat_history", [])
    updates["previous_queries"] = mem.get("previous_queries", [])

    return updates


# ─────────────────────────────────────────────────────────────────────────────
# 2. INTENT CLASSIFIER NODE
# ─────────────────────────────────────────────────────────────────────────────

def intent_classifier_node(state: GraphState) -> dict:
    """
    Classifies the user's query into: vague | simple | complex.

    Uses:
      - The current query
      - Last 3 turns of chat_history for context
      - Groq LLaMA3 with a structured JSON prompt
    """
    logger.info("[intent_classifier_node] query='%s'", state["query"][:80])

    history_snippet = _format_history(state["chat_history"], last_n=3)

    system = """You are an intent classifier for a RAG-based AI assistant.

Classify the user query into exactly one of these intents:
  - "vague"   : The query is too ambiguous or unclear to answer without more info
                (e.g. "tell me more", "what about that", "explain it")
  - "simple"  : A general question answerable from world knowledge, no documents needed
                (e.g. "what is RAG?", "who invented the internet?")
  - "complex" : Requires searching uploaded documents / knowledge base
                (e.g. "what does the report say about Q3 revenue?")

Respond ONLY with a JSON object. No preamble. No markdown. Example:
{"intent": "complex", "confidence": 0.92, "reason": "asks about specific document content"}"""

    user = f"""Recent conversation:
{history_snippet}

Current query: {state["query"]}"""

    try:
        raw = _chat(system, user, temperature=0.0)
        parsed = json.loads(raw)
        intent = parsed.get("intent", "complex")
        confidence = float(parsed.get("confidence", 0.8))
        logger.info("[intent_classifier_node] intent=%s conf=%.2f", intent, confidence)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("[intent_classifier_node] parse error %s — defaulting to complex", exc)
        intent = "complex"
        confidence = 0.5

    return {
        "intent": intent,
        "intent_confidence": confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. DECISION NODE  (router — returns a routing string)
# ─────────────────────────────────────────────────────────────────────────────

def decision_node(state: GraphState) -> Literal["clarification", "retriever", "answer_generator"]:
    """
    Pure routing node — returns the name of the next node to visit.

    Rules:
      vague   → clarification_node
      simple  → answer_generator_node  (skip retrieval)
      complex → retriever_node
      error   → answer_generator_node  (fail gracefully)
    """
    if state.get("error"):
        logger.warning("[decision_node] error present, routing to answer_generator")
        return "answer_generator"

    intent = state.get("intent", "complex")

    route_map = {
        "vague":   "clarification",
        "simple":  "answer_generator",
        "complex": "retriever",
    }
    route = route_map.get(intent, "retriever")
    logger.info("[decision_node] intent=%s → %s", intent, route)
    return route


# ─────────────────────────────────────────────────────────────────────────────
# 4. RETRIEVER NODE
# ─────────────────────────────────────────────────────────────────────────────

def retriever_node(state: GraphState) -> dict:
    """
    Queries Supabase pgvector for the top-k most relevant chunks.

    Uses:
      - HuggingFace SentenceTransformer to embed the query
      - Supabase match_documents RPC
      - Optional retrieval_filter from state
    """
    logger.info("[retriever_node] query='%s'", state["query"][:80])

    try:
        chunks = retrieve_chunks(
            query=state["query"],
            top_k=5,
            filter_metadata=state.get("retrieval_filter"),
        )
        logger.info("[retriever_node] Retrieved %d chunks", len(chunks))
        return {"retrieved_chunks": chunks}
    except Exception as exc:
        logger.error("[retriever_node] retrieval failed: %s", exc)
        return {
            "retrieved_chunks": [],
            "error": f"Retrieval failed: {exc}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. ANSWER GENERATOR NODE
# ─────────────────────────────────────────────────────────────────────────────

def answer_generator_node(state: GraphState) -> dict:
    """
    Generates the final structured answer using Groq.

    Behaviour:
      - If retrieved_chunks exist → grounded RAG answer with citations
      - If no chunks (simple intent) → direct LLM answer from world knowledge
      - Injects last 5 turns of chat_history for continuity
      - Structured output: answer + sources used
    """
    logger.info("[answer_generator_node] intent=%s chunks=%d",
                state.get("intent"), len(state.get("retrieved_chunks") or []))

    history_snippet = _format_history(state["chat_history"], last_n=5)
    chunks = state.get("retrieved_chunks") or []

    # ── Build context block ──────────────────────────────────────
    if chunks:
        context_block = "\n\n".join(
            f"[Source: {c['source']} | score: {c['similarity']:.2f}]\n{c['content']}"
            for c in chunks
        )
        rag_instruction = (
            "Answer the user's question using ONLY the provided context. "
            "If the context does not contain enough information, say so clearly. "
            "Do NOT fabricate facts. Cite sources by their filename when relevant."
        )
    else:
        context_block = "(No document context — use your general knowledge)"
        rag_instruction = (
            "Answer the user's question from your general knowledge. "
            "Be concise and accurate."
        )

    # ── Error passthrough ────────────────────────────────────────
    if state.get("error") and not chunks:
        return {
            "final_answer": (
                f"I encountered an issue while processing your request: {state['error']}. "
                "Please try again or rephrase your question."
            )
        }

    system = f"""You are a precise, helpful AI assistant with access to a document knowledge base.

{rag_instruction}

Format your response as follows:
1. A clear, direct answer in 1-3 paragraphs.
2. If sources were used, list them at the end under "**Sources:**".
3. If you are unsure, say "I'm not certain based on the available documents."

NEVER invent statistics, names, or facts not present in the context."""

    user = f"""## Conversation History
{history_snippet}

## Retrieved Context
{context_block}

## Current Question
{state["query"]}"""

    try:
        answer = _chat(system, user, temperature=0.3)
    except Exception as exc:
        logger.error("[answer_generator_node] generation failed: %s", exc)
        answer = "I'm sorry, I encountered an error generating a response. Please try again."

    return {"final_answer": answer}


# ─────────────────────────────────────────────────────────────────────────────
# 6. CLARIFICATION NODE
# ─────────────────────────────────────────────────────────────────────────────

def clarification_node(state: GraphState) -> dict:
    """
    Generates a targeted follow-up question when the user's query is vague.

    Sets:
      - clarification_question : the question to show the user
      - awaiting_clarification  : True (graph pauses, waits for user reply)
      - final_answer            : same as clarification_question (returned to API)
    """
    logger.info("[clarification_node] generating clarification for '%s'", state["query"][:80])

    history_snippet = _format_history(state["chat_history"], last_n=3)

    system = """You are a helpful assistant. The user's message is too vague to answer well.
Generate ONE short, specific clarifying question to understand what they need.
Do not answer the query. Only ask for clarification.
Keep the question under 25 words."""

    user = f"""Conversation so far:
{history_snippet}

Vague message: {state["query"]}"""

    try:
        question = _chat(system, user, temperature=0.4)
    except Exception as exc:
        logger.error("[clarification_node] failed: %s", exc)
        question = "Could you please provide more detail about what you're looking for?"

    return {
        "clarification_question": question,
        "awaiting_clarification": True,
        "final_answer": question,   # returned directly to the user via API
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. MEMORY UPDATE NODE
# ─────────────────────────────────────────────────────────────────────────────

def memory_update_node(state: GraphState) -> dict:
    """
    Persists the completed turn to the memory store.

    Appends:
      - user message  (query)
      - assistant message (final_answer or clarification_question)
      - query to previous_queries list

    Also updates the in-memory (later Supabase) store via memory.py.
    """
    logger.info("[memory_update_node] session=%s", state["session_id"])

    answer = state.get("final_answer") or state.get("clarification_question") or ""

    # Build updated history
    new_user_msg: Message = {"role": "user",      "content": state["query"]}
    new_asst_msg: Message = {"role": "assistant", "content": answer}

    updated_history = state["chat_history"] + [new_user_msg, new_asst_msg]
    updated_queries = state["previous_queries"] + [state["query"]]

    # Persist to memory store
    upsert_memory(
        session_id=state["session_id"],
        chat_history=updated_history,
        previous_queries=updated_queries,
    )

    logger.info("[memory_update_node] history now %d messages", len(updated_history))

    return {
        "chat_history": updated_history,
        "previous_queries": updated_queries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _format_history(history: list, last_n: int = 5) -> str:
    """Formats the last N messages into a readable string for prompts."""
    if not history:
        return "(no previous conversation)"
    recent = history[-(last_n * 2):]   # last_n turns = 2 messages each
    lines = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)