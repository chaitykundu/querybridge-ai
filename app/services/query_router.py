import re
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
            print(f"[detect_database] Matched '{alias}' -> {db}")
            return db

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a database name detector. "
                    "The user will ask a business question. Your ONLY job is to identify which company database they are referring to.\n\n"
                    "Return ONLY one of these exact alias strings, nothing else:\n"
                    "- star snacks\n"
                    "- star spice\n"
                    "- supreme star\n"
                    "- kadouri\n"
                    "- saminc\n"
                    "- null\n\n"
                    "If the query does not mention any specific company, return: null\n"
                    "No explanation. No punctuation. Just the alias."
                )
            },
            {"role": "user", "content": user_query}
        ],
        temperature=0,
        max_tokens=10
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
    print(f"[Schema loaded] DB: {db_name} -> {len(schema)} tables cached.")
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
    "vendorid":     ["AP"],
    "vendid":       ["AP"],
    "vendorname":   ["AP"],
    "payable":      ["AP"],
    "payables":     ["AP"],
    "payment":      ["AP"],
    "payments":     ["AP"],
    "purchase":     ["AP", "PO"],
    "purchases":    ["AP", "PO"],
    "bill":         ["AP"],
    "bills":        ["AP"],
    "owed":         ["AP"],
    "overdue":      ["AP"],
    "due":          ["AP", "AR"],
    "balance":      ["AP", "GL"],
    "balances":     ["AP", "GL"],

    # Accounts Receivable
    "customer":     ["AR"],
    "customers":    ["AR"],
    "receivable":   ["AR"],
    "receipt":      ["AR"],
    "receipts":     ["AR"],
    "invoice":      ["AR", "OE"],
    "invoices":     ["AR", "OE"],
    "outstanding":  ["AR"],
    "aging":        ["AR", "AP"],

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

    "salesperson":  ["OE", "AR"],
    "salespersons": ["OE", "AR"],
    "salespeople":  ["OE", "AR"],
    "salesper":     ["OE", "AR"],
    "rep":          ["OE", "AR"],
    "reps":         ["OE", "AR"],
    "performer":    ["OE", "AR"],
    "performers":   ["OE", "AR"],

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
    "financial":    ["GL"],
    "expense":      ["GL", "AP"],

    # Payroll / HR
    "employee":     ["PR", "HR"],
    "employees":    ["PR", "HR"],
    "payroll":      ["PR"],
    "salary":       ["PR"],
    "salaries":     ["PR"],
}

BUSINESS_SIGNAL_WORDS = set(QUERY_WORD_TO_TABLE_HINT.keys()) | {
    "ship", "shipped", "shipping", "vendor", "vendors", "cust", "customer", "customers",
    "owe", "owed", "overdue", "due", "invoice", "invoices", "payment", "payments",
    "order", "orders", "purchase", "purchases", "inventory", "stock", "balance",
    "sales", "revenue", "expense", "amount", "qty", "quantity", "amounts",
    "po", "ar", "ap", "oe", "ic", "gl", "salesperson", "salespeople", "rep", "reps", "performer", "performers",
}

NON_BUSINESS_SIGNAL_WORDS = {
    "weather", "joke", "movie", "music", "song", "recipe", "python", "code", "program",
    "sports", "sport", "news", "capital", "country", "currency", "translate", "meaning",
    "definition", "history", "science", "math", "movie", "game", "games", "food",
    "cook", "cookbook", "restaurant", "travel", "directions", "map", "forecast",
}


def is_business_query(user_query: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", user_query.lower()))
    if words & BUSINESS_SIGNAL_WORDS:
        return True
    if words & NON_BUSINESS_SIGNAL_WORDS:
        return False
    # treat short or vague queries without ERP terms as non-business
    return False


def filter_tables_by_keywords(user_query: str, schema: dict) -> dict:
    query_words = re.findall(r"[a-z0-9]+", user_query.lower())
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

    # Fallback: match meaningful words against table names and column names
    if not matched:
        meaningful_words = [w for w in query_words if len(w) > 3 or w in QUERY_WORD_TO_TABLE_HINT]
        for table, cols in schema.items():
            if any(
                w.upper() in table.upper() or
                any(w.upper() in col.upper() for col in cols)
                for w in meaningful_words
            ):
                matched[table] = cols

    # Broaden the scope for a business-related query if we still found nothing.
    if not matched and set(query_words) & BUSINESS_SIGNAL_WORDS:
        print("[filter_tables] No direct match, using business fallback on column/table names.")
        for table, cols in schema.items():
            if any(
                w.upper() in table.upper() or
                any(w.upper() in col.upper() for col in cols)
                for w in query_words
            ):
                matched[table] = cols

        # If still no match, keep the most likely tables instead of abandoning SQL generation entirely.
        if not matched:
            fallback_count = min(80, len(schema))
            matched = {table: schema[table] for table in list(schema.keys())[:fallback_count]}
            print(f"[filter_tables] Business query fallback selected top {fallback_count} tables.")

    print(f"[filter_tables] {len(schema)} -> {len(matched)} tables after keyword filter.")
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

def build_ultra_compact_schema(db_name: str, schema: dict, max_cols: int = 150) -> str:
    lines =[]
    for table, cols in schema.items():
        # Sort columns so DATE, AMT, QTY, ID show up first
        sorted_cols = sorted(list(cols.keys()), key=_col_score, reverse=True)
        top = sorted_cols[:max_cols]
        
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


def _parse_money_amount(text: str) -> str | None:
    match = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)", text)
    if not match:
        return None
    normalized = match.group(1).replace(",", "")
    return normalized


def _parse_days(text: str) -> int | None:
    match = re.search(r"(\d+)\s*days", text)
    if not match:
        return None
    return int(match.group(1))


def build_direct_aging_sql(user_query: str, db_name: str, schema: dict) -> str | None:
    text = user_query.lower()
    if "owe" not in text and "owed" not in text:
        return None

    is_vendor = any(word in text for word in ["vendor", "vendors"])
    is_customer = any(word in text for word in ["customer", "customers", "cust"])
    if is_vendor and is_customer:
        return None

    amount = _parse_money_amount(text)
    days = _parse_days(text)

    if is_vendor and "APVEN" in schema and "APVSM" in schema:
        where = []
        having = []
        if days is not None:
            where.append(f"APVSM.CNTDTOPAY > {days}")
        if amount is not None:
            having.append(f"SUM(APVSM.AMTINVCHC) > {amount}")
        else:
            having.append("SUM(APVSM.AMTINVCHC) > 0")

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        having_clause = f"HAVING {' AND '.join(having)}" if having else ""

        return (
            f"SELECT APVEN.VENDORID, APVEN.VENDNAME, SUM(APVSM.AMTINVCHC) AS BALANCE_OWED "
            f"FROM [{db_name}].[dbo].[APVEN] APVEN "
            f"JOIN [{db_name}].[dbo].[APVSM] APVSM ON APVEN.VENDORID = APVSM.VENDORID "
            f"{where_clause} "
            f"GROUP BY APVEN.VENDORID, APVEN.VENDNAME "
            f"{having_clause} "
            f"ORDER BY SUM(APVSM.AMTINVCHC) DESC"
        )

    if is_customer and "ARCUS" in schema and "ARAGED" in schema:
        where = []
        having = []
        if days is not None:
            where.append(f"ARAGED.DATEDUE < DATEADD(day, -{days}, GETDATE())")
        if amount is not None:
            having.append(f"SUM(ARAGED.AMTINVCHC) > {amount}")
        else:
            having.append("SUM(ARAGED.AMTINVCHC) > 0")

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        having_clause = f"HAVING {' AND '.join(having)}" if having else ""

        return (
            f"SELECT ARCUS.IDCUST, ARCUS.NAMECUST, SUM(ARAGED.AMTINVCHC) AS BALANCE_OWED "
            f"FROM [{db_name}].[dbo].[ARCUS] ARCUS "
            f"JOIN [{db_name}].[dbo].[ARAGED] ARAGED ON ARCUS.IDCUST = ARAGED.IDCUST "
            f"{where_clause} "
            f"GROUP BY ARCUS.IDCUST, ARCUS.NAMECUST "
            f"{having_clause} "
            f"ORDER BY SUM(ARAGED.AMTINVCHC) DESC"
        )

    return None


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

    # Step 2: skip SQL routing for explicit non-business queries
    if not is_business_query(user_query):
        print(f"[route_query] Non-business or vague query detected; skipping SQL generation.")
        return None, db_name, None

    # Step 2.5: known aging queries can use deterministic SQL templates
    direct_sql = build_direct_aging_sql(user_query, db_name, schema)
    if direct_sql:
        print("[route_query] Using deterministic aging SQL template.")
        return direct_sql, db_name, None

    # Step 3: Python keyword filter — 1051 → ~10-30 tables, 0 tokens
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
                    "You are an Elite T-SQL Developer for SAGE 300 on MS SQL Server.\n"
                    "Your single most important task is to follow the query recipes below with ZERO deviation.\n\n"

                    "**STRICT SYNTAX RULES (CRITICAL):**\n"
                    "1. NEVER use 'LIMIT'. Always use 'SELECT TOP N' at the start of the query for ranking/top results.\n"
                    "2. MS SQL Server syntax only.\n\n"

                    f"**SAGE 300 MASTER COOKBOOK (db={db_name}):**\n"
                    "-------------------------------------------------------------------\n"
                    "**RECIPE 1: BEST PERFORMING SALESPEOPLE**\n"
                    f"- Detail Table: `[{db_name}].[dbo].[OESHID]`, Header: `[{db_name}].[dbo].[OESHIH]`, Salesperson Master: `[{db_name}].[dbo].[ARSAP]`.\n"
                    "- Join shipment to header: `OESHID.SHIUNIQ = OESHIH.SHIUNIQ`.\n"
                    "- Join salesperson name: `OESHIH.SALESPER1 = ARSAP.SALESPERSON` to get `ARSAP.NAMEPER` (full name).\n"
                    "- Calculation: `SUM(OESHID.QTYSHIPPED * OESHID.UNITPRICE) AS TotalSales`.\n"
                    "- Group by: `ARSAP.SALESPERSON, ARSAP.NAMEPER`.\n"
                    f"- Example: `SELECT TOP 5 ARSAP.NAMEPER, SUM(OESHID.QTYSHIPPED * OESHID.UNITPRICE) AS TotalSales FROM [{db_name}].[dbo].[OESHID] OESHID JOIN [{db_name}].[dbo].[OESHIH] OESHIH ON OESHID.SHIUNIQ = OESHIH.SHIUNIQ JOIN [{db_name}].[dbo].[ARSAP] ARSAP ON OESHIH.SALESPER1 = ARSAP.SALESPERSON GROUP BY ARSAP.SALESPERSON, ARSAP.NAMEPER ORDER BY TotalSales DESC`\n\n"

                    "**RECIPE 2: BEST-SELLING ITEMS**\n"
                    f"- Detail Table: `[{db_name}].[dbo].[OEINVD]`, Header Table: `[{db_name}].[dbo].[OEINVH]`, Item Master: `[{db_name}].[dbo].[ICITEM]`.\n"
                    "- Join: `OEINVD.INVUNIQ = OEINVH.INVUNIQ` and `OEINVD.ITEM = ICITEM.ITEMNO`.\n"
                    "- Metric: `SUM(OEINVD.QTYINVC)`.\n"
                    "- Item Name: `ICITEM.[DESC]` (Use brackets around DESC).\n"
                    "- NEVER use ICRECPD for sales — that table is for purchase receipts only.\n"
                    f"- Example: `SELECT TOP 5 ICITEM.[DESC], SUM(OEINVD.QTYINVC) AS TotalSold FROM [{db_name}].[dbo].[OEINVD] OEINVD JOIN [{db_name}].[dbo].[OEINVH] OEINVH ON OEINVD.INVUNIQ = OEINVH.INVUNIQ JOIN [{db_name}].[dbo].[ICITEM] ICITEM ON OEINVD.ITEM = ICITEM.ITEMNO GROUP BY ICITEM.[DESC] ORDER BY TotalSold DESC`\n\n"

                    "**RECIPE 3: VENDORS/CUSTOMERS OWED MONEY**\n"
                    f"- AP: `[{db_name}].[dbo].[APVEN]` (Master) joined to `[{db_name}].[dbo].[APOBL]` (Trans) on `VENDORID = IDVEND`.\n"
                    f"- AR: `[{db_name}].[dbo].[ARCUS]` (Master) joined to `[{db_name}].[dbo].[AROBL]` (Trans) on `IDCUST = IDCUST`.\n"
                    "- Metric: `SUM(AMTINVCHC)`.\n\n"

                    "**UNIVERSAL RULES:**\n"
                    f"1. BRACKET FORMAT (CRITICAL): ALWAYS write table names as `[{db_name}].[dbo].[TABLENAME]` with square brackets. NEVER use dot-notation like `{db_name}.dbo.TABLENAME`.\n"
                    "2. NO HALLUCINATIONS: Do NOT guess column names. Use ONLY columns present in the Schema below.\n"
                    "3. COLUMN NAMES: In detail tables, the item column is `ITEM`. In Master `ICITEM`, it is `ITEMNO`.\n"
                    "4. DATES: Dates are YYYYMMDD integers. If a query returns no data with a 2023 filter, remove the date filter and show all-time data.\n"
                    "5. OUTPUT: Return ONLY the raw SQL query. No explanations. No markdown."
                )
            },
            {
                "role": "user",
                "content": f"Schema:\n{compact_schema}\n\nReal Data Samples:\n{sample_text}\n\nQuestion: {user_query}\n\nSQL:"
            }
        ],
        temperature=0,
        max_tokens=300
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # Correct common vendor-join alias mistakes when the schema uses VENDORID.
    if re.search(r"(?i)\bIDVEND\b", sql):
        sql = re.sub(r"(?i)\bIDVEND\b", "VENDORID", sql)
        print("[route_query] Applied vendor alias correction: IDVEND -> VENDORID")

    # Correct shipment number alias mistakes for SAGE 300 shipment tables.
    if re.search(r"(?i)OESHID\.SHINUMBER", sql):
        sql = re.sub(r"(?i)OESHID\.SHINUMBER", "OESHIH.SHINUMBER", sql)
        print("[route_query] Applied shipment alias correction: OESHID.SHINUMBER -> OESHIH.SHINUMBER")

    print(f"[route_query] Generated SQL:\n{sql}")

    if not sql.upper().startswith("SELECT"):
        return None, db_name, None
    if "SUM(AUDTDATE)" in sql.upper():
        return None, db_name, "Invalid aggregation on date column."

    return sql, db_name, None