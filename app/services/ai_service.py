from openai import OpenAI
from app.core.config import settings
from app.prompts.system_prompt import get_system_prompt
from app.services.query_router import route_query
from app.db.repository import execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# -----------------------------
# CONVERT RAW DB RESULTS → HUMAN ANSWER
# -----------------------------
def summarize_data_with_ai(query: str, data: list, role: str) -> str:
    if not data:
        return "No data was found in the database for your query."

    if isinstance(data, dict) and "error" in data:
        return f"There was a database error: {data['error']}"

    # Limit rows sent to AI to avoid token overflow
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
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful ERP business analyst. Summarize database results clearly for non-technical users."
            },
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
def generate_response(role: str, query: str):
    """
    Flow:
    1. route_query() returns (sql, db_name)
    2. If sql exists, run it on the correct DB
    3. Summarize results with AI
    4. Fall back to general LLM if no SQL generated
    """

   # STEP 1: Unpack tuple — sql may be None, db_name is always a string, error is polite message or None
    sql, db_name, error = route_query(query)

    if error:
        return {
            "type": "error",
            "response": error,
            "data": None
        }

    if sql:
        try:
            data = execute_query_on_db(db_name, sql)
        except Exception as e:
            print(f"[ai_service] DB error: {e}")
            data = {"error": str(e)}

        summary = summarize_data_with_ai(query, data, role)

        return {
            "type": "sql",
            "db": db_name,
            "query": sql,
            "data": data,
            "response": summary
        }

    print("[ai_service] No SQL generated — falling back to general LLM response.")

    # STEP 2: Not DB-related → general LLM response
    system_prompt = get_system_prompt(role)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.3
    )
    print("General LLM Response:", response.choices[0].message.content.strip())

    return {
        "type": "llm",
        "response": response.choices[0].message.content
    }