from openai import OpenAI
from app.core.config import settings
from app.db.repository import execute_query, execute_query_on_db
from app.services.schema_service import get_schema
from app.services.sql_validator import validate_aggregation
import re

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -----------------------------
# COMPANY → DATABASE MAP
# -----------------------------
DATABASE_NAME_MAP = {
    "star snacks": "STRDAT",
    "star snack":  "STRDAT",
    "kadouri":     "KADDAT",
    "supreme star": "TRIDAT",
    "star spice":  "SPCDAT",
    "star":        "STRDAT",
    "samin":       "SAMINC",
    "samin inc":   "SAMINC",
    "saminc":      "SAMINC",
    "strdat":      "STRDAT",
    "tridat":      "TRIDAT",
    "spcdat":      "SPCDAT",
    "kaddat":      "KADDAT",
}

# Default DB when no company is detected in the query
DEFAULT_DATABASE = "SAMINC"

# -----------------------------
# SCHEMA CACHE — per database
# -----------------------------
_schema_cache: dict[str, dict] = {}

# Tracks DBs that failed to load so we don't retry them
_unavailable_dbs: set[str] = set()


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
    global _schema_cache, _unavailable_dbs

    if db_name in _schema_cache:
        return _schema_cache[db_name]

    if db_name in _unavailable_dbs:
        print(f"[get_full_schema] DB '{db_name}' is marked unavailable — skipping.")
        return {}

    try:
        rows = execute_query_on_db(db_name, f"""
            SELECT t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
            FROM [{db_name}].INFORMATION_SCHEMA.TABLES t
            JOIN [{db_name}].INFORMATION_SCHEMA.COLUMNS c
              ON t.TABLE_NAME = c.TABLE_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE'
            ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
        """)
    except Exception as e:
        print(f"[get_full_schema] Cannot access DB '{db_name}': {e}")
        _unavailable_dbs.add(db_name)
        return {}

    def infer_role(col_name: str):
        c = col_name.upper()

        if "DATE" in c:
            return "date"
        if c.startswith("AMT") or "TOTAL" in c or "PRICE" in c:
            return "amount"
        if "QTY" in c:
            return "quantity"
        if "CUST" in c:
            return "customer"
        if "VEND" in c:
            return "vendor"
        if "NAME" in c:
            return "name"

        return "other"


    schema = {}

    for row in rows:
        table = row["TABLE_NAME"]
        col = row["COLUMN_NAME"]
        dtype = row["DATA_TYPE"]

        if table not in schema:
            schema[table] = {}

        schema[table][col] = {
            "type": dtype.lower(),
            "role": infer_role(col)
        }

    _schema_cache[db_name] = schema
    print(f"[Schema loaded] DB: {db_name} → {len(schema)} tables cached.")
    return schema


# -----------------------------
# STEP 1: Pick relevant tables
# Sends table name + all column names so LLM picks correctly
# based on actual columns, not just table names
# -----------------------------
def build_table_summary(schema: dict, max_cols: int = 10) -> str:
    """
    Compact summary: TABLE_NAME: COL1, COL2, COL3 ...
    Only sends first `max_cols` columns per table to stay within token limits.
    """
    lines = []
    for table, cols in schema.items():
        #col_names = ", ".join(c.split(" ")[0] for c in cols[:max_cols])
        col_names = ", ".join(list(cols.keys())[:max_cols])
        lines.append(f"{table}: {col_names}")
    return "\n".join(lines)


def build_table_summary_chunked(schema: dict, max_tables: int = 50, max_cols: int = 10) -> str:
    """
    If schema has too many tables, only send the first max_tables.
    Logs a warning if truncated.
    """
    keys = list(schema.keys())
    if len(keys) > max_tables:
        print(f"[build_table_summary] Schema has {len(keys)} tables — truncating to {max_tables} for token limit.")
        keys = keys[:max_tables]

    lines = []
    for table in keys:
        cols = schema[table]
        col_names = ", ".join(c.split(" ")[0] for c in cols[:max_cols])
        lines.append(f"{table}: {col_names}")
    return "\n".join(lines)


def pick_relevant_tables(user_query: str, db_name: str) -> list[str]:
    schema = get_full_schema(db_name)
    table_summary = build_table_summary(schema)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a database schema expert. "
                    "Given a user question and a list of tables with their exact column names, "
                    "identify which tables contain the columns needed to answer the question. "
                    "\n\nRules:"
                    "\n- If the user mentions a word that matches a TABLE NAME exactly, that is the table to query."
                    "\n- Choose tables that have columns matching what the user needs "
                    "(e.g. amounts, dates, invoice numbers, sequences)."
                    "\n- Do NOT pick a table just because its name sounds related — verify it has the right columns."
                    "\n- Reply with ONLY the relevant table names as a comma-separated list."
                    "\n- If no table fits, reply NULL."
                )
            },
            {
                "role": "user",
                "content": f"Question: {user_query}\n\nTables and their columns:\n{table_summary}"
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
            # for col in schema[table]:
            #     lines.append(f"  - {col}")
            for col, meta in schema[table].items():
                lines.append(f"  - {col} ({meta['type']})")
        
            lines.append("")
    return "\n".join(lines)


# -----------------------------
# MAIN ENTRY POINT
# Returns (sql, db_name, error)
# - sql: generated SELECT query or None
# - db_name: always a valid string
# - error: polite error message or None
# -----------------------------
def route_query(user_query: str) -> tuple[str | None, str, str | None]:
    # Step 0: always resolves to a DB (never None)
    db_name = detect_database(user_query)

    # Step 1: load schema — may fail gracefully if DB doesn't exist
    schema = get_full_schema(db_name)
    if not schema:
        company = next((k for k, v in DATABASE_NAME_MAP.items() if v == db_name), db_name)
        error_msg = f"The database for '{company}' is not available on the server. Please contact your administrator."
        print(f"[route_query] DB '{db_name}' unavailable — returning polite error.")
        return None, db_name, error_msg

    # Step 2: pick relevant tables
    relevant_tables = pick_relevant_tables(user_query, db_name)
    if not relevant_tables:
        print(f"[route_query] No relevant tables found in {db_name}")
        return None, db_name, None

    # Step 3: generate SQL using only real columns from real tables
    focused_schema = get_schema_for_tables(relevant_tables, db_name)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a T-SQL expert for SQL Server. "
                    "Write only a valid SELECT query using fully qualified table names like [DB].[dbo].[TABLE]. "
                    "RULES: "
                    "1. Only use column names that exist in the schema provided — never guess or invent column names. "
                    "2. If the user mentions a word matching a table name, use it as the FROM table, never as a WHERE filter value. "
                    "3. If the user mentions a standalone number, filter by the primary key or sequence column (INVHSEQ, SEQ, etc), NOT by date or amount columns. "
                    "4. For totals or best sellers, SUM the amount column directly — do not add wrong WHERE filters. "
                    "5. No explanation, no markdown, no backticks."
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
        return None, db_name, None

    if "SUM(AUDTDATE)" in sql.upper():
        print("[Validator] Invalid SQL detected")
        return None, db_name, "Invalid aggregation on date column."

    return sql, db_name, None