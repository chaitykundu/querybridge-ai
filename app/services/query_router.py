from openai import OpenAI
from app.core.config import settings
from app.db.repository import execute_query

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Schema is loaded once and reused — never fetched again
_schema_cache = None


# -----------------------------
# SCHEMA LOADER — cached in memory
# -----------------------------
def get_full_schema() -> dict:
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    rows = execute_query("""
        SELECT t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c ON t.TABLE_NAME = c.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE' AND t.TABLE_SCHEMA = 'dbo'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """)

    schema = {}
    for row in rows:
        table = row["TABLE_NAME"]
        if table not in schema:
            schema[table] = []
        schema[table].append(f"{row['COLUMN_NAME']} ({row['DATA_TYPE']})")

    _schema_cache = schema
    print(f"[Schema loaded] {len(schema)} tables cached.")
    return schema


def get_schema_context() -> str:
    schema = get_full_schema()
    return f"Total tables: {len(schema)}\nTables: {', '.join(schema.keys())}"


# -----------------------------
# STEP 1: Send ONLY table names to AI
# Tiny prompt ~500 tokens — AI picks relevant tables
# -----------------------------
def pick_relevant_tables(user_query: str) -> list[str]:
    schema = get_full_schema()
    table_names = "\n".join(schema.keys())

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a database assistant. Given a user question and table names, "
                    "reply with ONLY the relevant table names as a comma-separated list. "
                    "If none are relevant, reply NULL."
                )
            },
            {
                "role": "user",
                "content": f"Question: {user_query}\n\nAvailable tables:\n{table_names}"
            }
        ],
        temperature=0,
        max_tokens=50
    )

    result = response.choices[0].message.content.strip()
    print(f"[Table picker] Query: '{user_query}' → Tables: {result}")

    if result.upper() == "NULL" or not result:
        return []

    picked = [t.strip() for t in result.split(",")]
    valid = [t for t in picked if t in schema]
    return valid[:3]  # max 3 tables to keep tokens low


# -----------------------------
# STEP 2: Generate SQL with ONLY picked tables' columns
# Focused prompt ~300 tokens
# -----------------------------
def get_schema_for_tables(table_names: list[str]) -> str:
    schema = get_full_schema()
    lines = []
    for table in table_names:
        if table in schema:
            lines.append(f"Table: {table}")
            for col in schema[table]:
                lines.append(f"  - {col}")
            lines.append("")
    return "\n".join(lines)


def route_query(user_query: str) -> str | None:
    # Step 1: which tables? (~500 tokens)
    relevant_tables = pick_relevant_tables(user_query)
    if not relevant_tables:
        print("[route_query] No relevant tables found — falling back to LLM")
        return None

    # Step 2: generate SQL with only those tables (~300 tokens)
    focused_schema = get_schema_for_tables(relevant_tables)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a T-SQL expert for SQL Server. "
                    "Write only a valid SELECT query. "
                    "No explanation, no markdown, no backticks."
                )
            },
            {
                "role": "user",
                "content": f"Schema:\n{focused_schema}\n\nQuestion: {user_query}\n\nSQL:"
            }
        ],
        temperature=0,
        max_tokens=300
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    print(f"[route_query] Generated SQL: {sql}")

    if not sql.upper().startswith("SELECT"):
        return None

    return sql