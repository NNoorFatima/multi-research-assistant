

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