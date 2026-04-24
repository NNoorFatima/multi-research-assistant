"""
app/services/memory.py

In-memory store for chat history and previous queries.
Phase 1: plain Python dict keyed by session_id.
Phase 2 (TODO): swap _store reads/writes for Supabase table calls.
"""
from typing import List
import os
import supabase


supabase_client = supabase.create_client(
    supabase_url=os.environ["SUPABASE_URL"],
    supabase_key=os.environ["SUPABASE_SERVICE_KEY"]
)

_store: dict = {}

# def get_memory(session_id: str) -> dict:
#     return _store.get(session_id, {"chat_history": [], "previous_queries": []})
def get_memory(session_id: str):
    res = supabase_client.table("conversations") \
        .select("*") \
        .eq("session_id", session_id) \
        .execute()

    if res.data:
        return res.data[0]

    return {"chat_history": [], "previous_queries": []}

# def upsert_memory(session_id: str, chat_history: list, previous_queries: List[str]) -> None:
#     _store[session_id] = {"chat_history": chat_history, "previous_queries": previous_queries}
def upsert_memory(session_id: str, chat_history: list, previous_queries: List[str]) -> None:
    # Create the data to be inserted or updated    
    data = {
        "session_id": session_id,
        "chat_history": chat_history,
        "previous_queries": previous_queries
    }

    # Upsert the data into the "memory" table
    supabase_client.table("conversations").upsert(data, on_conflict="session_id").execute()


# def delete_memory(session_id: str) -> None:
#     """
#     Deletes memory for a given session_id.
#     If session_id does not exist, nothing happens.
#     """
#     _store.pop(session_id, None)
def delete_memory(session_id: str) -> None:
    """
    Deletes memory for a given session_id from the "conversation" table.
    If session_id does not exist, nothing happens.
    """
    supabase_client = supabase.create_client(
        supabase_url="YOUR_SUPABASE_URL",
        supabase_key="YOUR_SUPABASE_API_KEY"
    )

    # Delete the row with the given session_id from the "conversation" table
    response = supabase_client.table("conversations").delete().eq("session_id", session_id).execute()

    # Check if the deletion was successful
    if response.error is None:
        print(f"Successfully deleted memory for session_id: {session_id}")
    else:
        print(f"Error deleting memory for session_id: {session_id}. Error message: {response.error.message}")
# def list_sessions() -> list:
#     """
#     Returns all session IDs currently stored in memory.
#     """
#     return list(_store.keys())
def list_sessions() -> list:
    """
    Returns all session IDs currently stored in the "conversation" table.
    """

    # Query the "conversation" table for all session IDs
    response = supabase_client.table("conversations").select("session_id").execute()
    print("response=%s", response)
    # Extract the session IDs from the response
    session_ids = [result["session_id"] for result in response.data]

    return session_ids