import os
import psycopg2

def conectar():
    try:
        db_url = os.getenv("DATABASE_URL")
        return psycopg2.connect(db_url)
    except Exception as e:
        print("Error al conectar a PostgreSQL:", e)
        return None