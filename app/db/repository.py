from app.db.connection import get_connection


def execute_query(query: str):
    """Execute a query on the default database from connection settings."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(query)
    columns = [col[0] for col in cursor.description]

    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))

    conn.close()
    return results


def execute_query_on_db(db_name: str, query: str):
    """Execute a query after switching to a specific database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Switch to the target database before running the query
    cursor.execute(f"USE [{db_name}]")
    cursor.execute(query)

    columns = [col[0] for col in cursor.description]

    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))

    conn.close()
    return results