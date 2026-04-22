from app.db.repository import execute_query


def run_sql(query: str):
    """
    Executes a SQL query and returns results as a list of dicts.
    Returns an error dict if something goes wrong.
    """
    try:
        results = execute_query(query)
        return results
    except Exception as e:
        return {"error": str(e), "query": query}