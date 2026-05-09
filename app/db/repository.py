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
    """Execute a query on a specific database using fully qualified table names."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(query)  # query already has [db].[dbo].[TABLE] — no USE needed

        if cursor.description is None:
            return []

        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return results

    except Exception as e:
        raise e

    finally:
        conn.close()  # always close, even on error