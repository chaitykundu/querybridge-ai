from fastapi import APIRouter
from pydantic import BaseModel
from app.services.ai_service import generate_response
from app.services.query_router import route_query, get_full_schema

router = APIRouter()

# In-memory chat history: { user_id: [ {role, content}, ... ] }
chat_memory: dict[str, list] = {}

MAX_HISTORY = 20  # max messages to keep per user (10 turns)


class ChatRequest(BaseModel):
    user_id: str
    role: str
    query: str


@router.post("/chat")
def chat_endpoint(request: ChatRequest):
    user_id = request.user_id

    # Initialize history for new users
    if user_id not in chat_memory:
        chat_memory[user_id] = []

    history = chat_memory[user_id]

    # Generate response — pass history BEFORE adding current user message
    # so the current query isn't duplicated inside generate_response
    result = generate_response(
        role=request.role,
        query=request.query,
        chat_history=history  # history of previous turns only
    )

    # Save current turn to memory AFTER response
    history.append({"role": "user", "content": request.query})
    history.append({"role": "assistant", "content": result.get("response", "")})

    # Trim to max history
    chat_memory[user_id] = history[-MAX_HISTORY:]

    return {
        "user_id": user_id,
        "type": result.get("type"),
        "response": result.get("response"),
        "data": result.get("data"),
        "query": result.get("query"),   # SQL for debugging
        "db": result.get("db"),         # which DB was queried
    }


# -------------------------------------------------------
# DEBUG: Check schema loading
# GET /api/debug/schema?db=SAMINC
# -------------------------------------------------------
from fastapi import Query

@router.get("/debug/schema")
def debug_schema(db: str = Query(default="SAMINC")):
    schema = get_full_schema(db)
    print(f"[API] Schema for {db}: {list(schema.keys())}")
    return {
        "db": db,
        "table_count": len(schema),
        "tables": list(schema.keys()),
        "preview": {
            k: schema[k] for k in list(schema.keys())[:3]
        }
    }
print(f"[API] Router initialized with {len(router.routes)} routes.")

@router.get("/debug/schema/preview")
def preview_schema(db: str = "SAMINC", limit: int = 5):
    schema = get_full_schema(db)

    preview = {}

    for table, cols in schema.items():

        # CASE 1: dict -> convert to list
        if isinstance(cols, dict):
            cols_list = list(cols.keys())

        # CASE 2: list already correct
        elif isinstance(cols, list):
            cols_list = cols

        else:
            cols_list = []

        preview[table] = cols_list[:limit]

    return preview


# -------------------------------------------------------
# DEBUG: See what SQL is generated for a query
# POST /api/debug/sql
# Body: { "query": "your question here" }
# -------------------------------------------------------
class DebugSQLRequest(BaseModel):
    query: str

@router.post("/debug/sql")
def debug_sql(request: DebugSQLRequest):
    sql, db_name, error = route_query(request.query)

    if error:
        return {"sql": None, "error": error}

    if not sql:
        return {
            "sql": None,
            "message": "AI could not generate SQL — falling back to LLM",
            "fix": "Call GET /api/debug/schema?db=SAMINC to confirm tables loaded correctly"
        }

    from app.db.repository import execute_query_on_db
    try:
        data = execute_query_on_db(db_name, sql)
    except Exception as e:
        return {"sql": sql, "db": db_name, "error": str(e)}

    return {
        "sql": sql,
        "db": db_name,
        "row_count": len(data) if isinstance(data, list) else 0,
        "data_preview": data[:5] if isinstance(data, list) else data
    }


# -------------------------------------------------------
# DEBUG: View chat history for a user
# GET /api/debug/history?user_id=user_001
# -------------------------------------------------------
@router.get("/debug/history")
def debug_history(user_id: str = Query(...)):
    history = chat_memory.get(user_id, [])
    return {
        "user_id": user_id,
        "message_count": len(history),
        "history": history
    }


# -------------------------------------------------------
# Clear chat history for a user
# DELETE /api/chat/history?user_id=user_001
# -------------------------------------------------------
@router.delete("/chat/history")
def clear_history(user_id: str = Query(...)):
    if user_id in chat_memory:
        del chat_memory[user_id]
    return {"user_id": user_id, "status": "history cleared"}