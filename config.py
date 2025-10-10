import os
import psycopg2

def conectar():
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("DATABASE_URL no está definido en las variables de entorno.")
            return None
        conn = psycopg2.connect(db_url)
        print("Conexión exitosa a PostgreSQL.")
        return conn
    except Exception as e:
        print("Error al conectar a PostgreSQL:", e.__class__.__name__, str(e))
        return None

def desconectar(conn):
    try:
        if conn:
            conn.close()
            print("Conexión cerrada correctamente.")
    except Exception as e:
        print("Error al cerrar conexión:", e.__class__.__name__, str(e))   