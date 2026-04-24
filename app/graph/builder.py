"""
app/graph/builder.py

Constructs and compiles the LangGraph StateGraph.

Graph topology:
  input_node
    └─► intent_classifier_node
          └─► (conditional routing via decision_node function)
                ├── "vague"   → clarification_node   → memory_update_node → END
                ├── "simple"  → answer_generator_node → memory_update_node → END
                └── "complex" → retriever_node → answer_generator_node → memory_update_node → END

KEY POINT: decision_node is NOT registered as a graph node.
It is used only as the routing *function* passed to add_conditional_edges.
There is no add_edge("intent_classifier", "decision") — that would reference
a non-existent node and crash at compile time.
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.graph.state import GraphState
from app.graph.nodes import (
    input_node,
    intent_classifier_node,
    decision_node,          # routing function, NOT a graph node
    retriever_node,
    answer_generator_node,
    clarification_node,
    memory_update_node,
)

logger = logging.getLogger(__name__)


def _route_from_decision(state: GraphState) -> Literal[
    "clarification", "retriever", "answer_generator"
]:
    """
    Passed to add_conditional_edges as the routing function.
    LangGraph calls this after intent_classifier_node finishes
    and routes to whichever node name this returns.
    """
    return decision_node(state)


def build_graph():
    """
    Assembles and compiles the full LangGraph StateGraph.

    Returns:
        A compiled LangGraph app — call it with graph_app.invoke(state).
    """
    builder = StateGraph(GraphState)

    # ── Register all nodes ───────────────────────────────────────
    builder.add_node("input",             input_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("retriever",         retriever_node)
    builder.add_node("answer_generator",  answer_generator_node)
    builder.add_node("clarification",     clarification_node)
    builder.add_node("memory_update",     memory_update_node)
    # NOTE: decision_node is NOT added here — it's a routing function only

    # ── Entry point ──────────────────────────────────────────────
    builder.set_entry_point("input")

    # ── Fixed edge: input → intent_classifier ────────────────────
    builder.add_edge("input", "intent_classifier")

    # ── Conditional routing FROM intent_classifier ───────────────
    # After intent_classifier_node runs and sets state["intent"],
    # LangGraph calls _route_from_decision(state) to pick the next node.
    # There is NO separate "decision" node — the routing happens here.
    builder.add_conditional_edges(
        source="intent_classifier",
        path=_route_from_decision,
        path_map={
            "clarification":    "clarification",
            "retriever":        "retriever",
            "answer_generator": "answer_generator",
        },
    )

    # ── After retrieval, always generate answer ───────────────────
    builder.add_edge("retriever", "answer_generator")

    # ── Both answer paths converge to memory_update ──────────────
    builder.add_edge("answer_generator", "memory_update")
    builder.add_edge("clarification",    "memory_update")

    # ── Terminal ─────────────────────────────────────────────────
    builder.add_edge("memory_update", END)

    graph = builder.compile()
    logger.info("[builder] Graph compiled — nodes: input → intent_classifier → [clarification|retriever→answer_generator] → memory_update → END")
    return graph


graph_app = build_graph()