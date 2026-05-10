import re
from openai import OpenAI
from app.core.config import settings
from app.db.repository import execute_query_on_db

client = OpenAI(api_key=settings.OPENAI_API_KEY)

# ================================================================
# DATABASE CONFIG
# ================================================================
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


# ================================================================
# BUSINESS SCHEMA REGISTRY
# ================================================================
# All column names verified against the real database (table2.txt).
#
# KEY FACTS discovered from real schema:
#   - ARCSP, ICSP, ARSP do NOT exist in this DB
#   - OEINVH uses CUSTOMER (not IDCUST), INVFISCYR, INVFISCPER, INVNET
#   - OESHIH uses CUSTOMER (not IDCUST), SALESPER1
#   - ARSAP key: CODESLSP (salesperson code), NAMEEMPL (name)
#   - AROBL uses DATEDUE for overdue, AMTINVCHC for amount; no CNTDTDUE
#   - APOBL uses IDVEND (not VENDORID), AMTINVCHC
#   - APVSM uses VENDORID, AMTINVCHC, CNTDTOPAY (avg days to pay)
#   - OESTATS: company-level summary (SALESAMTF, QTYSOLD, YR, PERIOD)
#   - ICLOC: warehouse location table (no ITEMNO — it's a location master)
#   - ARCUS: DATELASTIV (last invoice date), NAMECUST, IDCUST, SWACTV
#   - For item stock: use ICITEM + query ICLOC separately (different join)
# ================================================================

BUSINESS_SCHEMA_REGISTRY = {

    # ----------------------------------------------------------------
    # SALES INVOICE — Revenue, trends, customer sales, item sales
    # ----------------------------------------------------------------
    "OEINVH": {
        "purpose": "Sales invoice header. One row per completed invoice/sale.",
        "use_for": [
            "total sales revenue", "sales by year", "sales by period",
            "monthly sales", "quarterly sales", "YoY growth", "sales trend",
            "net sales", "invoice count", "seasonal analysis",
            "customer invoice history", "period comparison", "sales total"
        ],
        "key_cols": [
            "INVUNIQ",       # unique invoice key (join to OEINVD)
            "INVNUMBER",     # invoice number
            "CUSTOMER",      # customer ID (join to ARCUS.IDCUST)
            "SALESPER1",     # salesperson code (join to ARSAP.CODESLSP)
            "ORDDATE",       # order date (YYYYMMDD integer)
            "INVFISCYR",     # fiscal year (e.g. '2023')
            "INVFISCPER",    # fiscal period (1-12)
            "INVNET",        # net invoice amount after discount
            "INVITMTOT",     # total item amount
            "INVSUBTOT",     # subtotal
            "INVNETNOTX",    # net amount before tax
            "SHIPDATE",      # ship date
        ],
        "joins": {
            "OEINVD": "OEINVH.INVUNIQ = OEINVD.INVUNIQ",
            "ARCUS":  "OEINVH.CUSTOMER = ARCUS.IDCUST",
            "ARSAP":  "OEINVH.SALESPER1 = ARSAP.CODESLSP",
        },
    },

    "OEINVD": {
        "purpose": "Sales invoice detail lines. One row per item per invoice. Best for item-level sales analysis.",
        "use_for": [
            "items sold", "quantity sold per item", "revenue per item",
            "best selling items", "top products", "product performance",
            "item sales ranking", "slow moving items", "item revenue",
            "returns per item", "item trend", "product quantity analysis"
        ],
        "key_cols": [
            "INVUNIQ",       # join to OEINVH
            "LINENUM",       # line number
            "ITEM",          # item number (join to ICITEM.ITEMNO)
            "DESC",          # item description
            "QTYSHIPPED",    # quantity shipped/sold
            "QTYORDERED",    # quantity ordered
            "UNITPRICE",     # unit price
            "EXTINVMISC",    # extended line amount (QTYSHIPPED * UNITPRICE)
            "UNITCOST",      # unit cost
            "EXTSCOST",      # extended cost (for margin analysis — from OESHID)
            "INVFISCYR",     # fiscal year
            "INVFISCPER",    # fiscal period
        ],
        "joins": {
            "OEINVH": "OEINVD.INVUNIQ = OEINVH.INVUNIQ",
            "ICITEM": "OEINVD.ITEM = ICITEM.ITEMNO",
        },
    },

    # ----------------------------------------------------------------
    # SHIPMENTS — Salesperson performance
    # ----------------------------------------------------------------
    "OESHIH": {
        "purpose": "Shipment header. Links shipments to salesperson. Use for salesperson revenue analysis.",
        "use_for": [
            "salesperson performance", "top salespeople", "best sales rep",
            "who sold the most", "salesperson revenue ranking",
            "sales by rep", "salesperson comparison"
        ],
        "key_cols": [
            "SHIUNIQ",       # unique shipment key (join to OESHID)
            "SHINUMBER",     # shipment number
            "CUSTOMER",      # customer ID
            "SALESPER1",     # salesperson code (join to ARSAP.CODESLSP)
            "SHIFISCYR",     # fiscal year
            "SHIFISCPER",    # fiscal period
            "SHIDATE",       # shipment date (YYYYMMDD)
            "SHINET",        # net shipment amount
            "SHIITMTOT",     # item total
        ],
        "joins": {
            "OESHID": "OESHIH.SHIUNIQ = OESHID.SHIUNIQ",
            "ARSAP":  "OESHIH.SALESPER1 = ARSAP.CODESLSP",
            "ARCUS":  "OESHIH.CUSTOMER = ARCUS.IDCUST",
        },
    },

    "OESHID": {
        "purpose": "Shipment detail lines. Quantity shipped and price per item per salesperson.",
        "use_for": [
            "salesperson item revenue", "quantity shipped by rep",
            "salesperson sales detail", "top salesperson calculation"
        ],
        "key_cols": [
            "SHIUNIQ",       # join to OESHIH
            "ITEM",          # item number
            "DESC",          # item description
            "QTYSHIPPED",    # quantity shipped
            "UNITPRICE",     # unit price
            "EXTSHIMISC",    # extended amount
            "UNITCOST",      # unit cost
        ],
        "joins": {
            "OESHIH": "OESHID.SHIUNIQ = OESHIH.SHIUNIQ",
            "ICITEM": "OESHID.ITEM = ICITEM.ITEMNO",
        },
    },

    # ----------------------------------------------------------------
    # CUSTOMERS
    # ----------------------------------------------------------------
    "ARCUS": {
        "purpose": "Customer master. Name, status, last activity date, credit limit.",
        "use_for": [
            "customer list", "customer info", "customer name lookup",
            "inactive customers", "customers with no recent sales",
            "customer last invoice date", "customer status",
            "customers not purchased in N years", "customer since when"
        ],
        "key_cols": [
            "IDCUST",        # customer ID (primary key)
            "NAMECUST",      # customer name
            "SWACTV",        # active flag (1=active, 0=inactive)
            "DATEINAC",      # date made inactive
            "DATELASTIV",    # date of last invoice
            "DATELASTAC",    # date of last activity
            "DATELASTPA",    # date of last payment
            "AMTBALDUEТ",    # total balance due
            "AMTCRLIMТ",     # credit limit
            "CODETЕРМ",      # payment terms
            "CODESLS P1",    # primary salesperson
            "NAMECITY",      # city
            "CODECTRY",      # country
        ],
        "joins": {
            "AROBL":  "ARCUS.IDCUST = AROBL.IDCUST",
            "OEINVH": "ARCUS.IDCUST = OEINVH.CUSTOMER",
            "ARAGED": "ARCUS.IDCUST = ARAGED.IDCUST",
        },
    },

    "AROBL": {
        "purpose": "AR open balance lines. Outstanding amounts owed by customers. Use for overdue analysis.",
        "use_for": [
            "customer outstanding balance", "who owes money",
            "overdue customers", "customers owed more than X amount",
            "unpaid invoices", "AR balance", "overdue more than N days",
            "customers with balance over threshold"
        ],
        "key_cols": [
            "IDCUST",        # customer ID (join to ARCUS.IDCUST)
            "IDINVC",        # invoice number
            "AMTINVCHC",     # invoice amount (home currency) — use this for totals
            "AMTDUEHC",      # amount still due
            "DATEDUE",       # due date (YYYYMMDD) — compare to get overdue days
            "DATEINVC",      # invoice date
            "DATEBUS",       # business date
            "FISCYR",        # fiscal year
            "FISCPER",       # fiscal period
            "SWPAID",        # paid flag (0=unpaid, 1=paid)
        ],
        "joins": {
            "ARCUS": "AROBL.IDCUST = ARCUS.IDCUST",
        },
        "notes": (
            "To calculate overdue days: DATEDIFF(day, CONVERT(date, CAST(DATEDUE AS varchar)), GETDATE()). "
            "DATEDUE is stored as YYYYMMDD integer. Filter SWPAID = 0 for unpaid only."
        ),
    },

    "ARAGED": {
        "purpose": "AR aging detail. Pre-calculated aging buckets per invoice.",
        "use_for": [
            "aging report", "how long overdue", "aged receivables",
            "30/60/90 day buckets", "customer aging detail"
        ],
        "key_cols": [
            "IDCUST",        # customer ID
            "IDINVC",        # invoice number
            "AMTINVCHC",     # invoice amount
            "AMTBALDUEH",    # balance due
            "DATEDUE",       # due date
            "DATEINVC",      # invoice date
            "AMTDUE1HC",     # current bucket
            "AMTDUE2HC",     # 31-60 days bucket
            "AMTDUE3HC",     # 61-90 days bucket
            "AMTDUE4HC",     # 91-120 days bucket
            "AMTDUE5HC",     # 120+ days bucket
        ],
        "joins": {
            "ARCUS": "ARAGED.IDCUST = ARCUS.IDCUST",
        },
    },

    # ----------------------------------------------------------------
    # SALESPERSON
    # ----------------------------------------------------------------
    "ARSAP": {
        "purpose": "Salesperson master. Name and code lookup for sales reps.",
        "use_for": [
            "salesperson name", "sales rep lookup",
            "list of salespeople", "who is salesperson"
        ],
        "key_cols": [
            "CODESLSP",      # salesperson code (primary key — join to OESHIH.SALESPER1 / OEINVH.SALESPER1)
            "NAMEEMPL",      # salesperson full name
            "CODEEMPL",      # employee code
            "SWACTV",        # active flag
        ],
        "joins": {
            "OESHIH": "ARSAP.CODESLSP = OESHIH.SALESPER1",
            "OEINVH": "ARSAP.CODESLSP = OEINVH.SALESPER1",
        },
    },

    # ----------------------------------------------------------------
    # ITEMS / INVENTORY
    # ----------------------------------------------------------------
    "ICITEM": {
        "purpose": "Item/product master. Description, category, cost, active status.",
        "use_for": [
            "item list", "product info", "item description",
            "item category", "product details", "inactive items",
            "item lookup by name or number"
        ],
        "key_cols": [
            "ITEMNO",        # item number (primary key)
            "DESC",          # item description — ALWAYS write as ICITEM.[DESC]
            "CATEGORY",      # item category
            "STOCKITEM",     # is stock item flag
            "INACTIVE",      # inactive flag (1=inactive)
            "DATEINACTV",    # date made inactive
            "STOCKUNIT",     # stock unit of measure
            "SELLABLE",      # sellable flag
        ],
        "joins": {
            "OEINVD": "ICITEM.ITEMNO = OEINVD.ITEM",
            "OESHID": "ICITEM.ITEMNO = OESHID.ITEM",
        },
    },

    # ----------------------------------------------------------------
    # COMPANY-LEVEL STATS — Overall sales summary
    # ----------------------------------------------------------------
    "OESTATS": {
        "purpose": "Company-level order/sales statistics by year and period. Best for overall revenue totals, YoY comparison, seasonal trends.",
        "use_for": [
            "total company sales by year", "which year had highest sales",
            "overall revenue trend", "YoY sales comparison",
            "best performing year", "total quantity sold company-wide",
            "seasonal sales pattern", "period over period growth",
            "company revenue summary"
        ],
        "key_cols": [
            "YR",            # fiscal year (e.g. '2023')
            "PERIOD",        # period/month (1-12)
            "SALESAMTF",     # total sales amount (functional/home currency)
            "SALESAMTS",     # total sales amount (source currency)
            "QTYSOLD",       # total quantity sold
            "INVCCOUNT",     # invoice count
            "COGSF",         # cost of goods sold
            "NUMORD",        # number of orders
            "AVGINFV",       # average invoice value
            "LARGESTINF",    # largest invoice amount
        ],
        "joins": {},
        "notes": "No joins needed. Standalone summary table. YR is a char field.",
    },

    # ----------------------------------------------------------------
    # VENDORS (AP)
    # ----------------------------------------------------------------
    "APVEN": {
        "purpose": "Vendor master. Vendor name, ID, status, contact details.",
        "use_for": [
            "vendor list", "vendor info", "vendor lookup",
            "supplier details", "vendor name", "active vendors"
        ],
        "key_cols": [
            "VENDORID",      # vendor ID (primary key — join to APVSM.VENDORID)
            "VENDNAME",      # vendor name
            "SWACTV",        # active flag
            "DATEINAC",      # date made inactive
            "DATELASTIV",    # date of last invoice
            "AMTBALDUEТ",    # total balance due
            "AMTCRLIMТ",     # credit limit
            "NAMECITY",      # city
        ],
        "joins": {
            "APOBL":  "APVEN.VENDORID = APOBL.IDVEND",   # NOTE: APOBL uses IDVEND not VENDORID
            "APVSM":  "APVEN.VENDORID = APVSM.VENDORID",
        },
    },

    "APOBL": {
        "purpose": "AP open balance lines. What we owe to vendors. Use for vendor outstanding analysis.",
        "use_for": [
            "vendor outstanding balance", "what we owe vendors",
            "vendors owed more than X", "unpaid vendor invoices",
            "vendor overdue payments", "vendor balance"
        ],
        "key_cols": [
            "IDVEND",        # vendor ID (join to APVEN.VENDORID) — NOTE: column is IDVEND here
            "IDINVC",        # invoice number
            "AMTINVCHC",     # invoice amount (home currency)
            "AMTDUEHC",      # amount still due
            "DATEDUE",       # due date (YYYYMMDD)
            "DATEINVC",      # invoice date
            "DATEBUS",       # business date
            "FISCYR",        # fiscal year
            "SWPAID",        # paid flag (0=unpaid)
        ],
        "joins": {
            "APVEN": "APOBL.IDVEND = APVEN.VENDORID",
        },
        "notes": (
            "CRITICAL: The vendor ID column in APOBL is IDVEND, not VENDORID. "
            "Always join: APOBL.IDVEND = APVEN.VENDORID. "
            "Filter SWPAID = 0 for unpaid only."
        ),
    },

    "APVSM": {
        "purpose": "Vendor statistics summary by year/period. Payment history and aging.",
        "use_for": [
            "vendor payment history", "vendor aging",
            "how long vendor overdue", "vendor days to pay",
            "vendor payment statistics"
        ],
        "key_cols": [
            "VENDORID",      # vendor ID (join to APVEN.VENDORID)
            "CNTYR",         # year
            "CNTPERD",       # period
            "AMTINVCHC",     # invoice amount
            "AMTPAYMHC",     # payment amount
            "CNTDTOPAY",     # average days to pay
            "AMTPURHC",      # purchase amount
            "CNTINVC",       # invoice count
        ],
        "joins": {
            "APVEN": "APVSM.VENDORID = APVEN.VENDORID",
        },
    },

    # ----------------------------------------------------------------
    # GENERAL LEDGER
    # ----------------------------------------------------------------
    "GLAFS": {
        "purpose": "GL account fiscal summary. Balance per account per fiscal year/period.",
        "use_for": [
            "account balance", "GL balance", "trial balance",
            "net income", "total expenses", "revenue by GL account",
            "financial statements", "period balances"
        ],
        "key_cols": [
            "ACCTID",        # GL account ID
            "FSCSYR",        # fiscal year
            "FSCSDSQ",       # fiscal period
            "OPENBAL",       # opening balance
            "NETPERD1",      # net activity period 1
            "NETPERD2",      # net activity period 2
            "NETPERD3",      # period 3
            "NETPERD4",      # period 4
            "NETPERD5",      # period 5
            "NETPERD6",      # period 6
            "NETPERD7",      # period 7
            "NETPERD8",      # period 8
            "NETPERD9",      # period 9
            "NETPERD10",     # period 10
            "NETPERD11",     # period 11
            "NETPERD12",     # period 12
        ],
        "joins": {},
        "notes": "Standalone. No join usually needed. FSCSYR is the year field (char).",
    },
}

# ================================================================
# Build registry summary for LLM (used in table selection prompt)
# ================================================================
def _build_registry_summary() -> str:
    lines = []
    for table, meta in BUSINESS_SCHEMA_REGISTRY.items():
        uses = ", ".join(meta["use_for"][:5])
        notes = f" NOTE: {meta['notes']}" if meta.get("notes") else ""
        lines.append(f"- {table}: {meta['purpose']} | USE FOR: {uses}{notes}")
    return "\n".join(lines)

REGISTRY_SUMMARY = _build_registry_summary()


# ================================================================
# STEP 0: Detect which company database
# ================================================================
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
                    "Return ONLY one of: star snacks, star spice, supreme star, kadouri, saminc, null\n"
                    "No explanation. Just the alias."
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


# ================================================================
# STEP 1: Quick non-business check (skip DB entirely)
# ================================================================
NON_BUSINESS_WORDS = {
    "weather", "joke", "movie", "music", "song", "recipe", "python", "code",
    "program", "sports", "news", "capital", "country", "translate", "history",
    "science", "game", "cook", "restaurant", "travel", "forecast", "poem",
}

def is_business_query(user_query: str) -> bool:
    words = set(re.findall(r"[a-z]+", user_query.lower()))
    return not bool(words & NON_BUSINESS_WORDS)


# ================================================================
# STEP 2: LLM selects exact tables from registry
# Works for ANY question — no hardcoded keywords
# ================================================================
def select_tables_for_query(user_query: str) -> list[str]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SAGE 300 ERP table selector.\n"
                    "Given a business question, pick the MINIMUM set of tables needed.\n\n"
                    "Rules:\n"
                    "1. Return ONLY a comma-separated list of table names. Nothing else.\n"
                    "2. Maximum 4 tables.\n"
                    "3. Always include a master table (ARCUS, ICITEM, APVEN, ARSAP) when joining.\n"
                    "4. For salesperson ranking → OESHID, OESHIH, ARSAP\n"
                    "5. For item sales → OEINVD, OEINVH, ICITEM\n"
                    "6. For customer outstanding → AROBL, ARCUS\n"
                    "7. For customer overdue aging → ARAGED, ARCUS\n"
                    "8. For vendor outstanding → APOBL, APVEN\n"
                    "9. For overall company revenue/trend → OESTATS\n"
                    "10. For customer sales history (who bought most) → OEINVH, ARCUS\n"
                    "11. For GL balances → GLAFS\n"
                    "12. For inactive customers (no purchase in N years) → ARCUS only\n\n"
                    f"AVAILABLE TABLES:\n{REGISTRY_SUMMARY}"
                )
            },
            {"role": "user", "content": f"Question: {user_query}"}
        ],
        temperature=0,
        max_tokens=60
    )

    raw = response.choices[0].message.content.strip()
    tables = [t.strip().upper() for t in raw.split(",") if t.strip()]
    valid = [t for t in tables if t in BUSINESS_SCHEMA_REGISTRY]
    print(f"[select_tables] '{user_query}' → {valid}")
    return valid


# ================================================================
# STEP 3: Load schema from DB (cached per session)
# ================================================================
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
        table = row["TABLE_NAME"]
        col = row["COLUMN_NAME"]
        schema.setdefault(table, {})[col] = {"type": row["DATA_TYPE"].lower()}

    _schema_cache[db_name] = schema
    print(f"[Schema loaded] {db_name} → {len(schema)} tables cached.")
    return schema


def get_schema_for_tables(tables: list[str], full_schema: dict) -> dict:
    result = {t: full_schema[t] for t in tables if t in full_schema}
    missing = [t for t in tables if t not in full_schema]
    if missing:
        print(f"[get_schema_for_tables] Not in DB: {missing}")
    return result


# ================================================================
# STEP 4: Build compact schema string for SQL LLM
# ================================================================
_PRIORITY_KW = (
    "ID", "NO", "NUM", "CODE", "NAME", "DATE", "AMT", "QTY",
    "PRICE", "CUST", "VEND", "ITEM", "SALE", "FISCAL", "YR",
    "NET", "TOT", "LAST", "ACTV", "SLSP",
)

def _col_score(col: str) -> int:
    u = col.upper()
    return sum(1 for kw in _PRIORITY_KW if kw in u)

def build_compact_schema(db_name: str, schema: dict, max_cols: int = 60) -> str:
    lines = []
    for table, cols in schema.items():
        sorted_cols = sorted(cols.keys(), key=_col_score, reverse=True)[:max_cols]
        lines.append(f"[{db_name}].[dbo].[{table}]: {' '.join(sorted_cols)}")
    return "\n".join(lines)


# ================================================================
# STEP 5: Sample data for column value context
# ================================================================
def get_table_sample(db_name: str, table: str) -> str:
    try:
        rows = execute_query_on_db(db_name, f"SELECT TOP 2 * FROM [{db_name}].[dbo].[{table}]")
        if rows:
            return str(rows)
    except Exception:
        pass
    return ""


# ================================================================
# STEP 6: Build join hints from registry for selected tables
# ================================================================
def build_join_hints(selected_tables: list[str]) -> str:
    seen = set()
    lines = []
    for table in selected_tables:
        meta = BUSINESS_SCHEMA_REGISTRY.get(table, {})
        for join_table, join_on in meta.get("joins", {}).items():
            if join_table in selected_tables:
                key = tuple(sorted([table, join_table]))
                if key not in seen:
                    seen.add(key)
                    lines.append(f"  {join_on}")
        if meta.get("notes"):
            lines.append(f"  NOTE ({table}): {meta['notes']}")
    return "\n".join(lines) if lines else "Determine joins from schema."


# ================================================================
# STEP 7: Generate SQL
# ================================================================
def generate_sql(user_query: str, db_name: str, schema: dict, selected_tables: list[str]) -> str | None:
    compact_schema = build_compact_schema(db_name, schema)
    join_hints = build_join_hints(selected_tables)

    sample_lines = []
    for table in selected_tables[:2]:
        sample = get_table_sample(db_name, table)
        if sample:
            sample_lines.append(f"-- {table} sample:\n{sample}")
    sample_text = "\n\n".join(sample_lines)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an Elite T-SQL Developer for SAGE 300 ERP on MS SQL Server.\n\n"

                    "ABSOLUTE RULES:\n"
                    "1. MS SQL Server ONLY. Never use LIMIT — use SELECT TOP N.\n"
                    f"2. Always bracket tables: [{db_name}].[dbo].[TABLENAME]\n"
                    "3. Use ONLY columns listed in the Schema below.\n"
                    "4. DATE COLUMNS are stored as YYYYMMDD integers.\n"
                    "   - To filter by year: WHERE INVFISCYR = '2023' or CAST(ORDDATE/10000 AS INT) = 2023\n"
                    "   - To calculate overdue days: DATEDIFF(day, CONVERT(date, CAST(DATEDUE AS varchar(8))), GETDATE())\n"
                    "5. ICITEM.[DESC] — always bracket DESC as it's a reserved word.\n"
                    "6. APOBL vendor join: APOBL.IDVEND = APVEN.VENDORID (not APOBL.VENDORID).\n"
                    "7. ARSAP salesperson join: ARSAP.CODESLSP = OESHIH.SALESPER1 (not ARSAP.SALESPERSON).\n"
                    "8. For unpaid invoices: WHERE SWPAID = 0\n"
                    "9. OUTPUT: Raw SQL only. No markdown. No explanation.\n\n"

                    "VERIFIED JOIN RELATIONSHIPS:\n"
                    f"{join_hints}\n\n"

                    "PROVEN SQL PATTERNS:\n"
                    "-- TOP SALESPEOPLE:\n"
                    f"SELECT TOP 5 ARSAP.NAMEEMPL, SUM(OESHID.QTYSHIPPED * OESHID.UNITPRICE) AS TotalSales "
                    f"FROM [{db_name}].[dbo].[OESHID] OESHID "
                    f"JOIN [{db_name}].[dbo].[OESHIH] OESHIH ON OESHID.SHIUNIQ = OESHIH.SHIUNIQ "
                    f"JOIN [{db_name}].[dbo].[ARSAP] ARSAP ON OESHIH.SALESPER1 = ARSAP.CODESLSP "
                    f"GROUP BY ARSAP.CODESLSP, ARSAP.NAMEEMPL ORDER BY TotalSales DESC\n\n"

                    "-- TOP ITEMS BY SALES:\n"
                    f"SELECT TOP 5 ICITEM.[DESC], SUM(OEINVD.QTYSHIPPED * OEINVD.UNITPRICE) AS TotalSales "
                    f"FROM [{db_name}].[dbo].[OEINVD] OEINVD "
                    f"JOIN [{db_name}].[dbo].[OEINVH] OEINVH ON OEINVD.INVUNIQ = OEINVH.INVUNIQ "
                    f"JOIN [{db_name}].[dbo].[ICITEM] ICITEM ON OEINVD.ITEM = ICITEM.ITEMNO "
                    f"GROUP BY ICITEM.ITEMNO, ICITEM.[DESC] ORDER BY TotalSales DESC\n\n"

                    "-- TOP CUSTOMERS BY REVENUE:\n"
                    f"SELECT TOP 5 ARCUS.NAMECUST, SUM(OEINVH.INVNET) AS TotalRevenue "
                    f"FROM [{db_name}].[dbo].[OEINVH] OEINVH "
                    f"JOIN [{db_name}].[dbo].[ARCUS] ARCUS ON OEINVH.CUSTOMER = ARCUS.IDCUST "
                    f"GROUP BY ARCUS.IDCUST, ARCUS.NAMECUST ORDER BY TotalRevenue DESC\n\n"

                    "-- CUSTOMER OUTSTANDING (overdue > 90 days):\n"
                    f"SELECT ARCUS.NAMECUST, SUM(AROBL.AMTINVCHC) AS TotalOwed, "
                    f"DATEDIFF(day, CONVERT(date, CAST(AROBL.DATEDUE AS varchar(8))), GETDATE()) AS DaysOverdue "
                    f"FROM [{db_name}].[dbo].[AROBL] AROBL "
                    f"JOIN [{db_name}].[dbo].[ARCUS] ARCUS ON AROBL.IDCUST = ARCUS.IDCUST "
                    f"WHERE AROBL.SWPAID = 0 AND DATEDIFF(day, CONVERT(date, CAST(AROBL.DATEDUE AS varchar(8))), GETDATE()) > 90 "
                    f"GROUP BY ARCUS.IDCUST, ARCUS.NAMECUST ORDER BY TotalOwed DESC\n\n"

                    "-- VENDOR OUTSTANDING:\n"
                    f"SELECT APVEN.VENDNAME, SUM(APOBL.AMTINVCHC) AS TotalOwed "
                    f"FROM [{db_name}].[dbo].[APOBL] APOBL "
                    f"JOIN [{db_name}].[dbo].[APVEN] APVEN ON APOBL.IDVEND = APVEN.VENDORID "
                    f"WHERE APOBL.SWPAID = 0 GROUP BY APVEN.VENDORID, APVEN.VENDNAME ORDER BY TotalOwed DESC\n\n"

                    "-- INACTIVE CUSTOMERS (no purchase in 2 years):\n"
                    f"SELECT NAMECUST, IDCUST, DATELASTIV FROM [{db_name}].[dbo].[ARCUS] "
                    f"WHERE DATELASTIV < CAST(FORMAT(DATEADD(year,-2,GETDATE()),'yyyyMMdd') AS decimal) "
                    f"OR DATELASTIV IS NULL ORDER BY DATELASTIV ASC\n\n"

                    "-- SALES BY YEAR (overall trend):\n"
                    f"SELECT YR, SUM(SALESAMTF) AS TotalSales, SUM(QTYSOLD) AS TotalQty "
                    f"FROM [{db_name}].[dbo].[OESTATS] GROUP BY YR ORDER BY YR\n"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Schema:\n{compact_schema}\n\n"
                    f"Sample Data:\n{sample_text}\n\n"
                    f"Question: {user_query}\n\n"
                    "SQL:"
                )
            }
        ],
        temperature=0,
        max_tokens=500
    )

    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # Auto-correct common SAGE 300 column mistakes
    corrections = [
        (r"(?i)\bAPOBL\.VENDORID\b",     "APOBL.IDVEND"),
        (r"(?i)\bARSAP\.SALESPERSON\b",  "ARSAP.CODESLSP"),
        (r"(?i)\bARSAP\.NAMEPER\b",      "ARSAP.NAMEEMPL"),
        (r"(?i)\bOESHIH\.IDCUST\b",      "OESHIH.CUSTOMER"),
        (r"(?i)\bOEINVH\.IDCUST\b",      "OEINVH.CUSTOMER"),
    ]
    for pattern, replacement in corrections:
        if re.search(pattern, sql):
            sql = re.sub(pattern, replacement, sql)
            print(f"[generate_sql] Auto-corrected: {pattern} → {replacement}")

    print(f"[generate_sql] SQL:\n{sql}")
    return sql


# ================================================================
# MAIN ENTRY POINT
# ================================================================
def route_query(user_query: str) -> tuple[str | None, str, str | None]:

    # Step 0: Which company?
    db_name = detect_database(user_query)

    # Step 1: Non-business check — skip DB entirely
    if not is_business_query(user_query):
        print("[route_query] Non-business query. Skipping DB.")
        return None, db_name, None

    # Step 2: LLM picks exact tables from registry
    selected_tables = select_tables_for_query(user_query)
    if not selected_tables:
        print("[route_query] No tables selected.")
        return None, db_name, None

    # Step 3: Load full schema (cached — only hits DB once per session)
    full_schema = get_full_schema(db_name)
    if not full_schema:
        company = next((k for k, v in DATABASE_NAME_MAP.items() if v == db_name), db_name)
        return None, db_name, f"The database for '{company}' is not available."

    # Step 4: Extract only selected tables' schema
    focused_schema = get_schema_for_tables(selected_tables, full_schema)
    if not focused_schema:
        print("[route_query] Selected tables not found in DB.")
        return None, db_name, None

    print(f"[route_query] Schema: {len(full_schema)} total → {len(focused_schema)} selected: {list(focused_schema.keys())}")

    # Step 5: Generate SQL with focused schema + proven patterns
    sql = generate_sql(user_query, db_name, focused_schema, selected_tables)

    if not sql or not sql.upper().startswith("SELECT"):
        return None, db_name, None
    if "SUM(AUDTDATE)" in sql.upper():
        return None, db_name, "Invalid aggregation on date column."

    return sql, db_name, None