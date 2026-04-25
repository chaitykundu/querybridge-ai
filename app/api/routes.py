from fastapi import APIRouter
from pydantic import BaseModel
from app.services.ai_service import generate_response
from app.services.query_router import route_query, get_full_schema  # ← get_full_schema, not get_schema_context
from app.services.sql_service import run_sql

router = APIRouter()
chat_memory = {}  # In-memory chat history: { user_id: [ {role, content}, ... ] }


class ChatRequest(BaseModel):
    user_id: str
    role: str
    query: str


@router.post("/chat")
def chat_endpoint(request: ChatRequest):
    # init memory
    if request.user_id not in chat_memory:
        chat_memory[request.user_id] = []

    # 1. Save user message
    chat_memory[request.user_id].append({
        "role": "user",
        "content": request.query
    })

    # 2. Generate response
    result = generate_response(
        role=request.role,
        query=request.query,
        chat_history=chat_memory[request.user_id]
    )

    # 3. ✅ SAVE ASSISTANT RESPONSE (THIS WAS MISSING)
    if result.get("type") != "error":
        chat_memory[request.user_id].append({
            "role": "assistant",
            "content": result.get("response")
        })

    # 4. (optional but important) limit memory
    chat_memory[request.user_id] = chat_memory[request.user_id][-10:]

    return {
        "user_id": request.user_id,
        "type": result.get("type"),
        "response": result.get("response"),
        "data": result.get("data"),
    }

# -------------------------------------------------------
# DEBUG 1: Check if schema is loading correctly
# GET http://localhost:8000/api/debug/schema
# -------------------------------------------------------
@router.get("/debug/schema")
def debug_schema():
    schema = get_full_schema()  # ← returns dict { table_name: [col1, col2, ...] }
    return {
        "table_count": len(schema),
        "tables": list(schema.keys()),
        "preview": {
            k: schema[k] for k in list(schema.keys())[:3]
        }
    }


# -------------------------------------------------------
# DEBUG 2: See what SQL is generated for a query
# POST http://localhost:8000/api/debug/sql
# Body: { "query": "your question here" }
# -------------------------------------------------------
class DebugSQLRequest(BaseModel):
    query: str

@router.post("/debug/sql")
def debug_sql(request: DebugSQLRequest):
    sql = route_query(request.query)

    if not sql:
        return {
            "sql": None,
            "message": "AI could not generate SQL — falling back to LLM",
            "fix": "Call GET /api/debug/schema to confirm tables loaded correctly"
        }

    data = run_sql(sql)
    return {
        "sql": sql,
        "row_count": len(data) if isinstance(data, list) else 0,
        "data_preview": data[:5] if isinstance(data, list) else data
    }