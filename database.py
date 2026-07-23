import os
import mysql.connector


def _create_db_connection():
    try:
        return mysql.connector.connect(
            host=os.environ.get("MYSQL_HOST") or os.environ.get("DB_HOST") or "localhost",
            user=os.environ.get("MYSQL_USER") or os.environ.get("DB_USER") or "root",
            password=os.environ.get("MYSQL_PASSWORD") or os.environ.get("DB_PASSWORD") or os.environ.get("PASSWORD", ""),
            database=os.environ.get("MYSQL_DB") or os.environ.get("DB_NAME") or "pulse_medicare", 
            connection_timeout=3,
        )
    except Exception:
        return None


db = _create_db_connection()
cursor = db.cursor() if db else None
