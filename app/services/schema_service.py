# app/services/schema_service.py

from app.db.connection import get_connection

SCHEMA_CACHE = {}


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
    if c.startswith("ID"):
        return "identifier"

    return "other"


def load_schema(db_name: str):
    conn = get_connection(db_name)
    cursor = conn.cursor()

    query = """
    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    ORDER BY TABLE_NAME
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    schema = {}

    for row in rows:
        table = row.TABLE_NAME.upper()
        col = row.COLUMN_NAME.upper()

        schema.setdefault(table, {})
        schema[table][col] = {
            "type": row.DATA_TYPE.lower(),
            "role": infer_role(col)
        }

    SCHEMA_CACHE[db_name] = schema
    return schema


def get_schema(db_name: str):
    if db_name not in SCHEMA_CACHE:
        load_schema(db_name)

    return SCHEMA_CACHE[db_name]