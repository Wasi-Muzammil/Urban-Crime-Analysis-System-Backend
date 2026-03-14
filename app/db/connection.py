import mysql.connector
from mysql.connector import pooling
from app.core.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

connection_pool = pooling.MySQLConnectionPool(
    pool_name="ucas_pool",
    pool_size=10,
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    autocommit=False,
)


def get_connection():
    """Return a connection from the pool."""
    return connection_pool.get_connection()
