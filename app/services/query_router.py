from openai import OpenAI
from app.core.config import settings
from app.db.repository import execute_query, execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -----------------------------
# COMPANY → DATABASE MAP
# -----------------------------
DATABASE_NAME_MAP = {
    "star snacks": "STRDAT",
    "star snack": "STRDAT",
    "kadouri": "KADDAT",
    "supreme star": "TRIDAT",
    "star spice": "SPCDAT",
    "star": "STRDAT",
    "samin": "SAMINC",      # ← was SAMINCS
    "samin inc": "SAMINC",  # ← was SAMINCS
    "saminc": "SAMINC",     # ← was SAMINCS
}

DEFAULT_DATABASE = "SAMINC"  # ← was SAMINCS

# -----------------------------
# SCHEMA CACHE — per database
# -----------------------------
_schema_cache: dict[str, dict] = {}


# -----------------------------
# STEP 0: Detect company → database
# -----------------------------
def detect_database(user_query: str) -> str:
    """
    Returns a database name. Always returns something —
    falls back to DEFAULT_DATABASE if no company detected.
    """
    query_lower = user_query.lower()

    # Longest match first to avoid partial hits
    sorted_keys = sorted(DATABASE_NAME_MAP.keys(), key=len, reverse=True)
    for alias in sorted_keys:
        if alias in query_lower:
            db = DATABASE_NAME_MAP[alias]
            print(f"[detect_database] Matched alias '{alias}' → DB: {db}")
            return db

    # Fallback: ask LLM
    aliases_list = ", ".join(DATABASE_NAME_MAP.keys())
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a company name extractor. Given a user question, "
                    f"identify which company is being referred to from this list: {aliases_list}. "
                    "Reply with ONLY the matched alias exactly as written, or NULL if none match."
                )
            },
            {"role": "user", "content": user_query}
        ],
        temperature=0,
        max_tokens=20
    )

    result = response.choices[0].message.content.strip().lower()
    print(f"[detect_database] LLM detected alias: '{result}'")

    if result == "null" or result not in DATABASE_NAME_MAP:
        print(f"[detect_database] No match found — using default DB: {DEFAULT_DATABASE}")
        return DEFAULT_DATABASE

    return DATABASE_NAME_MAP[result]


# -----------------------------
# SCHEMA LOADER — cached per database
# -----------------------------
def get_full_schema(db_name: str) -> dict:
    global _schema_cache

    if db_name in _schema_cache:
        return _schema_cache[db_name]

    rows = execute_query_on_db(db_name, f"""
        SELECT t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
        FROM [{db_name}].INFORMATION_SCHEMA.TABLES t
        JOIN [{db_name}].INFORMATION_SCHEMA.COLUMNS c
          ON t.TABLE_NAME = c.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """)

    schema = {}
    for row in rows:
        table = row["TABLE_NAME"]
        if table not in schema:
            schema[table] = []
        schema[table].append(f"{row['COLUMN_NAME']} ({row['DATA_TYPE']})")

    _schema_cache[db_name] = schema
    print(f"[Schema loaded] DB: {db_name} → {len(schema)} tables cached.")
    return schema


# -----------------------------
# STEP 1: Pick relevant tables
# -----------------------------
def pick_relevant_tables(user_query: str, db_name: str) -> list[str]:
    schema = get_full_schema(db_name)
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
    print(f"[Table picker] DB: {db_name} | Query: '{user_query}' → Tables: {result}")

    if result.upper() == "NULL" or not result:
        return []

    picked = [t.strip() for t in result.split(",")]
    valid = [t for t in picked if t in schema]
    return valid[:3]


# -----------------------------
# STEP 2: Build focused schema string
# -----------------------------
def get_schema_for_tables(table_names: list[str], db_name: str) -> str:
    schema = get_full_schema(db_name)
    lines = []
    for table in table_names:
        if table in schema:
            lines.append(f"Table: [{db_name}].[dbo].[{table}]")
            for col in schema[table]:
                lines.append(f"  - {col}")
            lines.append("")
    return "\n".join(lines)


# -----------------------------
# MAIN ENTRY POINT
# Returns (sql: str | None, db_name: str)
# sql is None only if no relevant tables found or SQL generation failed
# db_name is ALWAYS a valid string
# -----------------------------
def route_query(user_query: str) -> tuple[str | None, str]:
    # Step 0: always resolves to a DB (never None)
    db_name = detect_database(user_query)

    # Step 1: pick relevant tables
    relevant_tables = pick_relevant_tables(user_query, db_name)
    if not relevant_tables:
        print(f"[route_query] No relevant tables found in {db_name}")
        return None, db_name

    # Step 2: generate SQL
    focused_schema = get_schema_for_tables(relevant_tables, db_name)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                "You are a T-SQL expert for SQL Server. "
                "Write only a valid SELECT query using fully qualified table names like [DB].[dbo].[TABLE]. "
                "When a user mentions a number that looks like an invoice or sequence number, "
                "use it to filter by the primary key or sequence column (e.g. INVHSEQ, INVSEQ, SEQ), "
                "NOT by date or amount columns. "
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
    print(f"[route_query] DB: {db_name} | Generated SQL: {sql}")

    if not sql.upper().startswith("SELECT"):
        return None, db_name

    return sql, db_name