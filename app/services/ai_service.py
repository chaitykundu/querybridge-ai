from openai import OpenAI
from app.core.config import settings
from app.prompts.system_prompt import get_system_prompt
from app.services.query_router import route_query, DB_DISPLAY_NAME
from app.db.repository import execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# -----------------------------
# CONVERT RAW DB RESULTS → HUMAN ANSWER
# -----------------------------
def summarize_data_with_ai(query: str, data: list, role: str, db_name: str="", chat_history: list = None) -> str:
    if chat_history is None:
        chat_history =[]

    # Handle completely empty datasets gracefully before hitting the LLM
    if not data:
        return (
            f"I couldn't find any relevant data in the '{db_name}' database for your query. "
            "Please try rephrasing or verify that the data exists for this timeframe."
        )

    # Handle SQL execution errors gracefully
    if isinstance(data, dict) and "error" in data:
        return (
            f"I couldn't retrieve the requested information from {db_name} due to a technical issue. "
            "Please try again or contact your system administrator if the problem persists."
        )

    # Limit rows to prevent blowing up the LLM token limit
    capped_data = data[:50]
    data_str = str(capped_data)
    exact_row_count = len(capped_data)

    prompt = f"""
You are an Executive Business Analyst. Your job is to translate raw ERP database results into a professional, human-readable answer.

User's Question: "{query}"
Target Company/Database: {db_name}
User Role: {role}

Raw Database Results ({exact_row_count} records TOTAL — this is the COMPLETE dataset):
{data_str}

STRICT PRESENTATION RULES:
1. Direct Answer First: Give the exact numbers or data asked for immediately in the first sentence.
2. Executive Formatting: 
   - Use bullet points for lists of 3 or more items.
   - Use **bold text** for KPIs, totals, and important metrics.
   - Include currency symbols ($) where it is obvious the metric represents money (e.g., Sales, Revenue, Price).
3. Comparisons: If the user asks for a comparison (e.g., this year vs last year), format it clearly and state the difference if the data provides it.
4. Zero Technical Jargon: DO NOT mention "SQL", "database", "tables", "columns", "JSON", "arrays", or "rows". Speak purely in business terms.
5. Entity Resolution: If the data contains raw IDs (like IDCUST) alongside readable names (like CustomerName), ONLY show the readable names to the user.
6. !!CRITICAL — ZERO HALLUCINATION!!:
   - The dataset above contains EXACTLY {exact_row_count} records. You MUST present EXACTLY {exact_row_count} items — no more, no less.
   - NEVER add, invent, or infer any names, numbers, or records not explicitly present in the Raw Database Results above.
   - Do NOT use chat history to supplement or fill in missing data.
   - If there are only {exact_row_count} results, say so — do not pad the list.
7. PROFIT/COST CAVEAT: If the user asked about profit or most profitable but the data only contains Revenue (no Cost or Profit column), clearly note:
   Note: Item cost data is not recorded in the system, so results are ranked by revenue. For true profit analysis, item costs need to be entered in SAGE 300.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a top-tier ERP Business Analyst. You summarize complex data into beautiful, direct, and non-technical business insights."
            },
            *chat_history,
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2  # Lower temperature for highly factual reporting
    )
    
    print("AI Summary Response:", response.choices[0].message.content.strip())
    return response.choices[0].message.content.strip()


# -----------------------------
# MAIN AI SERVICE (The missing function)
# -----------------------------
def generate_response(role: str, query: str, chat_history: list = None):
    if chat_history is None:
        chat_history =[]

    sql, db_name, error = route_query(query)
    
    display_name = DB_DISPLAY_NAME.get(db_name, db_name)  # friendly name for display only

    if error:
        return {"type": "error", "response": error, "data": None}

    if sql:
        try:
            data = execute_query_on_db(db_name, sql)  # use raw db_name for DB connection
            print("[DEBUG] Query result:", data[:3]) 
        except Exception as e:
            data = {"error": str(e)}

        summary = summarize_data_with_ai(query, data, role, display_name, chat_history)  # use display_name here

        return {
            "type": "sql",
            "db": display_name,  # friendly name in response
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