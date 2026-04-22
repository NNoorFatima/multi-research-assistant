"""
app/graph/builder.py

Constructs and compiles the LangGraph StateGraph.

Graph topology:
  input_node
    └─► intent_classifier_node
          └─► decision_node  (conditional router)
                ├── "vague"   → clarification_node  → memory_update_node → END
                ├── "simple"  → answer_generator_node → memory_update_node → END
                └── "complex" → retriever_node → answer_generator_node → memory_update_node → END
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.graph.state import GraphState
from app.graph.nodes import (
    input_node,
    intent_classifier_node,
    decision_node,
    retriever_node,
    answer_generator_node,
    clarification_node,
    memory_update_node,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Routing wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _route_from_decision(state: GraphState) -> Literal[
    "clarification", "retriever", "answer_generator"
]:
    """
    Thin wrapper around decision_node used as the conditional_edge function.
    LangGraph calls this with the current state and expects a node-name string back.
    """
    return decision_node(state)


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Assembles the full LangGraph StateGraph and returns the compiled app.

    Usage:
        graph = build_graph()
        result = graph.invoke(initial_state)
    """
    builder = StateGraph(GraphState)

    # ── Register nodes ───────────────────────────────────────────
    builder.add_node("input",             input_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("retriever",         retriever_node)
    builder.add_node("answer_generator",  answer_generator_node)
    builder.add_node("clarification",     clarification_node)
    builder.add_node("memory_update",     memory_update_node)

    # ── Entry point ──────────────────────────────────────────────
    builder.set_entry_point("input")

    # ── Linear edges ─────────────────────────────────────────────
    builder.add_edge("input",             "intent_classifier")
    builder.add_edge("intent_classifier", "decision")          # hits conditional below

    # ── Conditional routing from decision ────────────────────────
    # decision_node is NOT registered as a graph node — it's used
    # purely as the routing function for add_conditional_edges.
    builder.add_conditional_edges(
        source="intent_classifier",          # after intent is known
        path=_route_from_decision,           # returns "clarification" | "retriever" | "answer_generator"
        path_map={
            "clarification":    "clarification",
            "retriever":        "retriever",
            "answer_generator": "answer_generator",
        },
    )

    # ── Converging edges → memory_update ─────────────────────────
    builder.add_edge("clarification",    "memory_update")
    builder.add_edge("retriever",        "answer_generator")
    builder.add_edge("answer_generator", "memory_update")

    # ── Terminal edge ─────────────────────────────────────────────
    builder.add_edge("memory_update", END)

    # ── Compile ───────────────────────────────────────────────────
    graph = builder.compile()
    logger.info("[builder] Graph compiled successfully")
    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (imported by main.py)
# ─────────────────────────────────────────────────────────────────────────────

graph_app = build_graph()