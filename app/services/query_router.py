from openai import OpenAI
from app.core.config import settings
from app.db.repository import execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)

DATABASE_NAME_MAP = {
    "star snacks":  "STRDAT",
    "star snack":   "STRDAT",
    "kadouri":      "KADDAT",
    "supreme star": "TRIDAT",
    "star spice":   "SPCDAT",
    "star":         "STRDAT",
    "samin":        "SAMINC",
    "samin inc":    "SAMINC",
    "saminc":       "SAMINC",
    "strdat":       "STRDAT",
    "tridat":       "TRIDAT",
    "spcdat":       "SPCDAT",
    "kaddat":       "KADDAT",
}

DEFAULT_DATABASE = "SAMINC"

_schema_cache: dict[str, dict] = {}
_unavailable_dbs: set[str] = set()


# -----------------------------
# STEP 0: Detect database
# -----------------------------
def detect_database(user_query: str) -> str:
    query_lower = user_query.lower()
    for alias in sorted(DATABASE_NAME_MAP.keys(), key=len, reverse=True):
        if alias in query_lower:
            db = DATABASE_NAME_MAP[alias]
            print(f"[detect_database] Matched '{alias}' → {db}")
            return db

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    f"Identify which company from: {', '.join(DATABASE_NAME_MAP.keys())}. "
                    "Reply ONLY with the matched alias or NULL."
                )
            },
            {"role": "user", "content": user_query}
        ],
        temperature=0, max_tokens=20
    )
    result = response.choices[0].message.content.strip().lower()
    if result == "null" or result not in DATABASE_NAME_MAP:
        return DEFAULT_DATABASE
    return DATABASE_NAME_MAP[result]


# -----------------------------
# STEP 1: Load full schema — cached
# -----------------------------
def get_full_schema(db_name: str) -> dict:
    if db_name in _schema_cache:
        return _schema_cache[db_name]
    if db_name in _unavailable_dbs:
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

    schema: dict = {}
    for row in rows:
        schema.setdefault(row["TABLE_NAME"], {})[row["COLUMN_NAME"]] = {
            "type": row["DATA_TYPE"].lower()
        }

    _schema_cache[db_name] = schema
    print(f"[Schema loaded] DB: {db_name} → {len(schema)} tables cached.")
    return schema


# -----------------------------
# STEP 2: Keyword-filter tables in pure Python — NO LLM, NO tokens
#
# Query words are matched against table names directly.
# e.g. "best seller" → matches tables containing SALE, SLSS, CUST, ITEM
# This cuts 1051 tables down to ~10-30 relevant ones before any LLM call.
# -----------------------------

# Maps common query words → substrings that appear in your ERP table names.
# Extend this list based on your actual table naming conventions.
QUERY_WORD_TO_TABLE_HINT: dict[str, list[str]] = {
    "sale":     ["SALE", "SLSS", "INVH", "SINV"],
    "sales":    ["SALE", "SLSS", "INVH", "SINV"],
    "seller":   ["SALE", "SLSS", "CUST", "ITEM"],
    "best":     ["SALE", "SLSS", "CUST", "ITEM"],
    "top":      ["SALE", "SLSS", "CUST", "ITEM"],
    "invoice":  ["INVH", "INVD", "INV"],
    "invoices": ["INVH", "INVD", "INV"],
    "customer": ["CUST"],
    "customers":["CUST"],
    "vendor":   ["VEND", "SUPP"],
    "vendors":  ["VEND", "SUPP"],
    "item":     ["ITEM", "PROD"],
    "items":    ["ITEM", "PROD"],
    "product":  ["ITEM", "PROD"],
    "purchase": ["PORD", "PURCH", "PORC"],
    "order":    ["ORDR", "PORD"],
    "payment":  ["RCPT", "PAY"],
    "stock":    ["STCK", "INVT", "WHSE"],
    "inventory":["INVT", "STCK", "WHSE"],
    "account":  ["ACCT", "GL"],
    "ledger":   ["GL", "LEDG"],
    "employee": ["EMP", "HR"],
}

def filter_tables_by_keywords(user_query: str, schema: dict) -> dict:
    """
    Pure Python — zero LLM calls, zero tokens.
    Matches query words against table name substrings.
    Returns a filtered schema dict with only relevant tables.
    """
    query_words = user_query.lower().split()
    hints: set[str] = set()

    # Collect all table-name hints that match any word in the query
    for word in query_words:
        if word in QUERY_WORD_TO_TABLE_HINT:
            hints.update(QUERY_WORD_TO_TABLE_HINT[word])

    matched: dict = {}

    if hints:
        for table in schema:
            table_upper = table.upper()
            if any(hint in table_upper for hint in hints):
                matched[table] = schema[table]

    # Fallback: if no hint matched, try raw word-in-table-name scan
    if not matched:
        meaningful_words = [w for w in query_words if len(w) > 3]
        for table in schema:
            table_upper = table.upper()
            if any(w.upper() in table_upper for w in meaningful_words):
                matched[table] = schema[table]

    print(f"[filter_tables] {len(schema)} → {len(matched)} tables after keyword filter.")
    return matched


# -----------------------------
# STEP 3: Build ultra-compact schema string
# Format: TABLE: COL1 COL2 COL3 (no types, no punctuation = fewer tokens)
# Only the first N columns per table — sorted by business relevance
# -----------------------------
_PRIORITY_KEYWORDS = (
    "SEQ", "NO", "NUM", "CODE", "NAME", "DATE", "AMT",
    "TOTAL", "QTY", "PRICE", "CUST", "VEND", "ITEM",
    "PROD", "INV", "SALE", "DESC", "TYPE", "ID",
)

def _col_score(col: str) -> int:
    u = col.upper()
    return sum(1 for kw in _PRIORITY_KEYWORDS if kw in u)

def build_ultra_compact_schema(db_name: str, schema: dict, max_cols: int = 5) -> str:
    """
    One line per table, top-scored columns only, no types.
    TABLE_NAME: COL1 COL2 COL3
    ~5-10 tokens per table instead of 30-50.
    """
    lines = []
    for table, cols in schema.items():
        top = sorted(cols.keys(), key=_col_score, reverse=True)[:max_cols]
        # Fully qualified so LLM can use directly in SQL
        fq = f"[{db_name}].[dbo].[{table}]"
        lines.append(f"{fq}: {' '.join(top)}")
    return "\n".join(lines)


# -----------------------------
# MAIN ENTRY POINT — 2 steps only: detect DB → generate SQL
# No table picker. No second LLM call. One prompt does everything.
# -----------------------------
def route_query(user_query: str) -> tuple[str | None, str, str | None]:
    # Step 0: which database?
    db_name = detect_database(user_query)

    # Step 1: load full schema (cached after first call)
    schema = get_full_schema(db_name)
    if not schema:
        company = next((k for k, v in DATABASE_NAME_MAP.items() if v == db_name), db_name)
        return None, db_name, (
            f"The database for '{company}' is not available. "
            "Please contact your administrator."
        )

    # Step 2: Python keyword filter — 1051 → ~10-30 tables, 0 tokens
    filtered = filter_tables_by_keywords(user_query, schema)
    if not filtered:
        print(f"[route_query] No tables matched query keywords.")
        return None, db_name, None

    # Step 3: build compact schema and generate SQL in ONE LLM call
    compact_schema = build_ultra_compact_schema(db_name, filtered)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a T-SQL expert for SQL Server.\n"
                    "You generate correct SQL based on BUSINESS MEANING, not just column names.\n\n"

                    "You are given:\n"
                    "1. A schema with tables and columns\n"
                    "2. OPTIONAL business meaning of columns (VERY IMPORTANT)\n\n"

                    "RULES:\n"
                    "1. Only use columns from schema.\n"
                    "2. Always interpret queries in BUSINESS TERMS first (sales, customers, invoices, payments).\n"
                    "3. If multiple tables exist, choose joins only when business relationship is logical.\n"
                    "4. NEVER assume column meaning unless explicitly stated.\n"
                    "5. 'top/best seller' means highest SUM(quantity or amount related to sales).\n"
                    "6. Avoid incorrect aggregations on unrelated fields (dates, IDs, codes).\n"
                    "7. Return ONLY valid SQL Server query.\n"
                    "8. No explanation, no markdown.\n"
                )
            },
            {
                "role": "user",
                "content": f"Schema:\n{compact_schema}\n\nQuestion: {user_query}\n\nSQL:"
            }
        ],
        temperature=0,
        max_tokens=300
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    print(f"[route_query] Generated SQL:\n{sql}")

    if not sql.upper().startswith("SELECT"):
        return None, db_name, None
    if "SUM(AUDTDATE)" in sql.upper():
        return None, db_name, "Invalid aggregation on date column."

    return sql, db_name, None