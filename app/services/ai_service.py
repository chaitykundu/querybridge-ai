from openai import OpenAI
from app.core.config import settings
from app.prompts.system_prompt import get_system_prompt
from app.services.query_router import route_query
from app.db.repository import execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# -----------------------------
# CONVERT RAW DB RESULTS → HUMAN ANSWER
# -----------------------------
def summarize_data_with_ai(query: str, data: list, role: str, chat_history: list = None) -> str:
    if chat_history is None:
        chat_history = []

    if not data:
        return (
            "I could not find relevant data to answer this. "
            "Please try rephrasing your question or specify the table name (e.g. POINVJ, APCCS)."
        )

    if isinstance(data, dict) and "error" in data:
        return f"There was a database error: {data['error']}"

    data_str = str(data[:50])

    prompt = f"""
You are a helpful ERP assistant responding to a {role}.

The user asked: "{query}"

The database returned this data:
{data_str}

Write a clear, concise, human-friendly answer based only on this data.
- Use actual numbers and facts from the data
- Use bullet points if there are multiple rows
- Do NOT mention SQL, tables, columns, or any technical details
- If the data is empty or unclear, say so honestly
- NEVER invent or guess numbers not present in the data
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful ERP business analyst. Summarize database results clearly for non-technical users. Never invent data."
            },
            *chat_history,
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.3
    )
    print("AI Summary Response:", response.choices[0].message.content.strip())
    return response.choices[0].message.content.strip()


# -----------------------------
# MAIN AI SERVICE
# -----------------------------
def generate_response(role: str, query: str, chat_history: list = None):
    if chat_history is None:
        chat_history = []

    # STEP 1: route_query returns (sql, db_name, error)
    sql, db_name, error = route_query(query)

    # DB not available on server
    if error:
        return {
            "type": "error",
            "response": error,
            "data": None
        }

    # SQL was generated — run it
    if sql:
        try:
            data = execute_query_on_db(db_name, sql)
        except Exception as e:
            print(f"[ai_service] DB error: {e}")
            data = {"error": str(e)}

        summary = summarize_data_with_ai(query, data, role, chat_history)

        return {
            "type": "sql",
            "db": db_name,
            "query": sql,
            "data": data,
            "response": summary
        }

    print("[ai_service] No SQL generated — falling back to general LLM response.")

    # STEP 2: No SQL — use LLM with history but strict no-hallucination rule
    system_prompt = get_system_prompt(role)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            *chat_history,
            {"role": "user", "content": query}
        ],
        temperature=0.3
    )
    print("General LLM Response:", response.choices[0].message.content.strip())

    return {
        "type": "llm",
        "response": response.choices[0].message.content.strip()
    }