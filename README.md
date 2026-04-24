

```bash 
project/
│
├── app/
│   ├── main.py              # FastAPI entry
│   ├── graph/
│   │   ├── builder.py      # LangGraph setup
│   │   ├── nodes.py        # All nodes
│   │   └── state.py        # Graph state
│   │
│   ├── services/
│   │   ├── retriever.py    # Supabase queries
│   │   ├── embeddings.py
│   │   └── memory.py
│   │
│   ├── utils/
│   │   ├── pdf_loader.py
│   │   └── chunking.py
│
├── requirements.txt
└── README.md
```
# LangGraph × Supabase AI Assistant

A production-ready RAG assistant with graph-based decision making, persistent memory, and dynamic routing — built with LangGraph, Groq, HuggingFace SentenceTransformers, and Supabase pgvector.

---

## Architecture

```
POST /query or /upload
        │
        ▼
  [ input_node ]  ← loads memory, ingests PDF if uploaded
        │
        ▼
  [ intent_classifier_node ]  ← Groq LLaMA3 classifies: vague | simple | complex
        │
        ▼
  [ decision_node ]  ← conditional router
   ┌────┴────────────────────┐
   │ vague    │ complex       │ simple
   ▼          ▼               ▼
[clarif.] [retriever]  [answer_generator]
   │          │               │
   │          ▼               │
   │    [answer_generator]    │
   └──────────┴───────────────┘
                │
                ▼
        [ memory_update_node ]
                │
               END
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project
- A [Groq](https://console.groq.com) API key

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment
Create env file.
```bash
# Fill in GROQ_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY
```

### 4. Set up Supabase

Open your Supabase project → SQL Editor → paste and run `supabase_setup.sql`.

This creates:
- `documents` table with `vector(384)` column + IVFFlat index
- `match_documents` RPC function for cosine similarity search
- `conversations` table (for Phase 2 persistent memory)
- Row Level Security policies

### 5. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the interactive Swagger UI.

---

## API Reference

### `POST /query`

Ask a question. The graph classifies intent and retrieves context if needed.

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What were the key findings in the Q3 report?",
    "session_id": "user-abc-123",
    "filter_source": "q3_report.pdf"
  }'
```

**Response:**
```json
{
  "session_id": "user-abc-123",
  "answer": "According to the Q3 report...",
  "intent": "complex",
  "sources": ["q3_report.pdf"],
  "awaiting_clarification": false,
  "turn": 1
}
```

**Intent behaviour:**
| Intent | What happens |
|--------|-------------|
| `vague` | Returns a clarifying question, sets `awaiting_clarification: true` |
| `simple` | Answers directly from LLM knowledge, no retrieval |
| `complex` | Embeds query → Supabase similarity search → grounded answer |

---

### `POST /upload`

Upload a PDF to the knowledge base.

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@reports/q3_report.pdf" \
  -F "session_id=user-abc-123"
```

**Response:**
```json
{
  "session_id": "user-abc-123",
  "filename": "q3_report.pdf",
  "chunks_ingested": 42,
  "message": "'q3_report.pdf' ingested successfully (42 chunks)..."
}
```

After uploading, query the document using `filter_source: "q3_report.pdf"` to restrict retrieval to that file.

---

### `GET /history/{session_id}`

Retrieve full conversation history for a session.

```bash
curl http://localhost:8000/history/user-abc-123
```

---

### `DELETE /history/{session_id}`

Clear memory for a session (start fresh).

```bash
curl -X DELETE http://localhost:8000/history/user-abc-123
```

---

### `GET /health`

Liveness check — returns graph node list and active session count.

---

## Project Structure

```
project/
├── app/
│   ├── main.py                  # FastAPI entry — all endpoints
│   ├── graph/
│   │   ├── state.py             # GraphState TypedDict — shared truth
│   │   ├── nodes.py             # All 7 node functions
│   │   └── builder.py          # StateGraph wiring + conditional edges
│   ├── services/
│   │   ├── embeddings.py        # HuggingFace SentenceTransformer + upsert
│   │   ├── retriever.py         # Supabase pgvector similarity search
│   │   └── memory.py            # In-memory store (→ Supabase Phase 2)
│   └── utils/
│       ├── pdf_loader.py        # PyMuPDF text extraction + cleanup
│       └── chunking.py          # Sentence-aware sliding window chunker
├── supabase_setup.sql           # Run once in Supabase SQL Editor
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ | Groq API key for LLaMA3 inference |
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Anon key — used for reads in retriever.py |
| `SUPABASE_SERVICE_KEY` | ✅ | Service-role key — used for writes in embeddings.py |

---

## Tuning Guide

| Parameter | File | Default | When to change |
|-----------|------|---------|----------------|
| `SIMILARITY_THRESHOLD` | `retriever.py` | `0.30` | Raise to `0.50` if getting off-topic chunks |
| `chunk_size` | `chunking.py` | `500` | Lower for precise retrieval, raise for more context |
| `overlap` | `chunking.py` | `50` | Raise if answers miss context at chunk boundaries |
| `top_k` | `retriever.py` | `5` | Raise for broader context, lower for speed |
| `GROQ_MODEL` | `nodes.py` | `llama3-8b-8192` | Swap for `llama3-70b-8192` for higher quality |

---

## Phase 2: Persistent Memory

Currently `memory.py` uses an in-process Python dict. To persist across restarts:

1. The `conversations` table is already created by `supabase_setup.sql`
2. Update `get_memory()` and `upsert_memory()` in `app/services/memory.py`  
   to read/write from the `conversations` Supabase table instead of `_store`

---

