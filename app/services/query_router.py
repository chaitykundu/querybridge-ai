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

# ← ADD RIGHT HERE ↓
DB_DISPLAY_NAME = {
    "SAMINC": "Samin Inc",
    "STRDAT": "Star Snacks",
    "TRIDAT": "Supreme Star",
    "SPCDAT": "Star Spice",
    "KADDAT": "Kadouri",
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
            ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION  -- ✅ preserve real column order
        """)
    except Exception as e:
        print(f"[get_full_schema] Cannot access DB '{db_name}': {e}")
        _unavailable_dbs.add(db_name)
        return {}

    # ✅ Use dict to preserve insertion order (Python 3.7+)
    schema: dict = {}
    for row in rows:
        table = row["TABLE_NAME"]
        col = row["COLUMN_NAME"]
        schema.setdefault(table, {})[col] = {
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
    # Accounts Payable
    "vendor":       ["AP"],
    "vendors":      ["AP"],
    "payable":      ["AP"],
    "payment":      ["AP"],
    "payments":     ["AP"],
    "purchase":     ["AP", "PO"],
    "purchases":    ["AP", "PO"],
    "bill":         ["AP"],
    "bills":        ["AP"],

    # Accounts Receivable
    "customer":     ["AR"],
    "customers":    ["AR"],
    "receivable":   ["AR"],
    "receipt":      ["AR"],
    "receipts":     ["AR"],
    "invoice":      ["AR", "OE"],
    "invoices":     ["AR", "OE"],
    "outstanding":  ["AR"],
    "due":          ["AR"],

    # Order Entry / Sales
    "sale":         ["OE", "AR"],
    "sales":        ["OE", "AR"],
    "order":        ["OE"],
    "orders":       ["OE"],
    "shipment":     ["OE"],
    "shipments":    ["OE"],
    "seller":       ["OE", "AR"],
    "best":         ["OE", "AR"],
    "top":          ["OE", "AR"],

    # Inventory Control
    "inventory":    ["IC"],
    "stock":        ["IC"],
    "item":         ["IC"],
    "items":        ["IC"],
    "product":      ["IC"],
    "products":     ["IC"],
    "warehouse":    ["IC"],

    # Purchase Orders
    "po":           ["PO"],
    "purchasing":   ["PO", "AP"],

    # General Ledger
    "ledger":       ["GL"],
    "account":      ["GL"],
    "accounts":     ["GL"],
    "journal":      ["GL"],
    "balance":      ["GL"],
    "financial":    ["GL"],
    "expense":      ["GL", "AP"],

    # Payroll / HR
    "employee":     ["PR", "HR"],
    "employees":    ["PR", "HR"],
    "payroll":      ["PR"],
    "salary":       ["PR"],
    "salaries":     ["PR"],
}

def filter_tables_by_keywords(user_query: str, schema: dict) -> dict:
    query_words = user_query.lower().split()
    hints: set[str] = set()

    for word in query_words:
        if word in QUERY_WORD_TO_TABLE_HINT:
            hints.update(QUERY_WORD_TO_TABLE_HINT[word])

    matched: dict = {}

    if hints:
        for table in schema:
            # Match by PREFIX instead of substring
            if any(table.upper().startswith(hint) for hint in hints):
                matched[table] = schema[table]

    # Fallback
    if not matched:
        meaningful_words = [w for w in query_words if len(w) > 3]
        for table in schema:
            if any(w.upper() in table.upper() for w in meaningful_words):
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

def build_ultra_compact_schema(db_name: str, schema: dict, max_cols: int = 30) -> str:
    lines = []
    for table, cols in schema.items():
        # REMOVE the sorted/scoring — just take columns in original order
        top = list(cols.keys())[:max_cols]  # ← changed this line
        fq = f"[{db_name}].[dbo].[{table}]"
        lines.append(f"{fq}: {' '.join(top)}")
    return "\n".join(lines)

# ← ADD RIGHT HERE ↓
def get_table_sample(db_name: str, table: str) -> str:
    try:
        rows = execute_query_on_db(db_name, f"SELECT TOP 2 * FROM [{db_name}].[dbo].[{table}]")
        if rows:
            return str(rows)
    except:
        pass
    return ""

# -----------------------------
# MAIN ENTRY POINT — 2 steps only: detect DB → generate SQL
# No table picker. No second LLM call. One prompt does everything.
# -----------------------------
def route_query(user_query: str) -> tuple[str | None, str, str | None]:
    # Step 0: which database?
    db_name = detect_database(user_query)

    # Step 1: load full schema (cached after first call)
    schema = get_full_schema(db_name)
    # ADD THIS TO SEE YOUR REAL TABLE NAMES
    print("[DEBUG] Sample tables:", list(schema.keys())[:30])
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
    compact_schema = build_ultra_compact_schema(db_name, filtered, max_cols=30)

    # Add real sample data for top 3 tables
    sample_lines = []
    for table in list(filtered.keys())[:3]:
        sample = get_table_sample(db_name, table)
        if sample:
            sample_lines.append(f"Sample from {table}:\n{sample}")
    sample_text = "\n\n".join(sample_lines)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a T-SQL expert for Sage 300 ERP on SQL Server.\n"
                    "You generate correct SQL based on BUSINESS MEANING, not just column names.\n\n"

                    "RULES:\n"
                    "1. Only use columns that exist in the schema provided.\n"
                    "2. Always interpret queries in BUSINESS TERMS first.\n"
                    "3. Use the real data samples to understand what values and column names actually exist.\n"
                    "4. NEVER guess or invent column names — only use columns visible in the schema.\n"
                    "5. Return ONLY valid SQL Server query.\n"
                    "6. No explanation, no markdown.\n"
                )
            },
            {
                "role": "user",
                "content": f"Schema:\n{compact_schema}\n\nReal Data Samples:\n{sample_text}\n\nQuestion: {user_query}\n\nSQL:"  # ← added sample_text
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