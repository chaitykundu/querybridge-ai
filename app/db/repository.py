from app.db.connection import get_connection

def execute_query(query: str):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(zip(columns, row)))
    
    conn.close()
    return results