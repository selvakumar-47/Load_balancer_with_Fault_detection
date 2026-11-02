import sqlite3
import os
import threading
from typing import List, Dict, Any, Optional
from config import Config

_local = threading.local()

def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a thread-local SQLite connection with WAL mode enabled."""
    target_path = db_path or Config.DATABASE_PATH
    
    # Store connection in thread local so each thread has its own connection
    attr_name = f"conn_{abs(hash(target_path))}"
    conn = getattr(_local, attr_name, None)
    
    if conn is None:
        conn = sqlite3.connect(
            target_path, 
            timeout=20.0, 
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging for high concurrency between threads
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        setattr(_local, attr_name, conn)
        
    return conn

def init_db(db_path: Optional[str] = None):
    """Initializes the database using schema.sql and seeds default system config and 3 test backends."""
    target_path = db_path or Config.DATABASE_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_db_connection(target_path)
    with conn:
        conn.executescript(schema_sql)

    # Seed default system configuration if not already set
    default_configs = [
        ("active_algorithm", Config.DEFAULT_ALGORITHM, "Active load balancing algorithm"),
        ("health_check_interval", str(Config.HEALTH_CHECK_INTERVAL_SECONDS), "Health check prober interval in seconds"),
        ("health_check_timeout", str(Config.HEALTH_CHECK_TIMEOUT_SECONDS), "Health check probe timeout in seconds"),
        ("request_timeout", str(Config.REQUEST_TIMEOUT_SECONDS), "Reverse proxy request timeout in seconds"),
        ("failure_threshold", str(Config.FAILURE_THRESHOLD), "Consecutive failures to trigger OPEN circuit"),
        ("recovery_threshold", str(Config.RECOVERY_THRESHOLD), "Consecutive successes in HALF-OPEN to restore CLOSED"),
        ("recovery_delay", str(Config.RECOVERY_DELAY_SECONDS), "Wait time in seconds in OPEN state before HALF-OPEN probe"),
    ]
    
    with conn:
        for key, val, desc in default_configs:
            conn.execute(
                "INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?);",
                (key, val, desc)
            )

    # Seed 3 default local test backends if table is empty
    with conn:
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM servers;")
        row = cursor.fetchone()
        if row and row["cnt"] == 0:
            default_servers = [
                ("srv-backend-a", "Backend Alpha", "http://127.0.0.1:8001", 3),
                ("srv-backend-b", "Backend Beta", "http://127.0.0.1:8002", 2),
                ("srv-backend-c", "Backend Gamma", "http://127.0.0.1:8003", 1),
            ]
            for s_id, s_name, s_url, s_weight in default_servers:
                conn.execute(
                    """INSERT INTO servers (id, name, url, weight, is_enabled, status, circuit_state)
                       VALUES (?, ?, ?, ?, 1, 'HEALTHY', 'CLOSED');""",
                    (s_id, s_name, s_url, s_weight)
                )

def query_db(query: str, args: tuple = (), one: bool = False, db_path: Optional[str] = None) -> Any:
    """Executes a SELECT query and returns rows as dictionaries."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(query, args)
    rows = cursor.fetchall()
    cursor.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]

def execute_db(query: str, args: tuple = (), db_path: Optional[str] = None) -> int:
    """Executes an INSERT, UPDATE, or DELETE query and returns the lastrowid or affected rows."""
    conn = get_db_connection(db_path)
    with conn:
        cursor = conn.cursor()
        cursor.execute(query, args)
        last_id = cursor.lastrowid
        cursor.close()
        return last_id
