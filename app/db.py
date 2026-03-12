from contextlib import contextmanager
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import mysql.connector
except Exception:  # pragma: no cover - optional when running in sqlite mode
    mysql = None

from .config import DB_CONFIG, DB_ENGINE, SQLITE_DB_PATH

_SCHEMA_BOOTSTRAPPED = False


def is_sqlite() -> bool:
    return DB_ENGINE == "sqlite"


def _schema_path(file_name: str) -> Path:
    candidates: list[Path] = []

    # PyInstaller one-file extraction directory (preferred when available).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / file_name)

    # Source tree location (dev mode).
    candidates.append(Path(__file__).resolve().parent.parent / file_name)

    # Installed executable directory (fallback if files are shipped next to exe).
    candidates.append(Path(sys.executable).resolve().parent / file_name)

    # Current working directory as a last resort.
    candidates.append(Path.cwd() / file_name)

    for path in candidates:
        if path.exists():
            return path

    searched = " | ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Schema introuvable: {file_name}. Chemins testes: {searched}")


def _adapt_sqlite_query(query: str) -> str:
    q = query
    q = q.replace("%s", "?")
    q = q.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO")
    q = q.replace(
        "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
        "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
    )
    q = q.replace("DATE_ADD(NOW(), INTERVAL 15 MINUTE)", "DATETIME('now', '+15 minutes')")
    q = q.replace("DATE_SUB(CURDATE(), INTERVAL 12 MONTH)", "DATE('now', '-12 months')")
    q = q.replace("DATE_FORMAT(created_at, '%Y-%m')", "strftime('%Y-%m', created_at)")
    q = q.replace("CURDATE()", "DATE('now')")
    return q


def adapt_query(query: str) -> str:
    if is_sqlite():
        return _adapt_sqlite_query(query)
    return query


class SQLiteCursorAdapter:
    def __init__(self, cursor: sqlite3.Cursor, dictionary: bool = False):
        self._cursor = cursor
        self._dictionary = dictionary

    def execute(self, query: str, params: Iterable[Any] | None = None):
        self._cursor.execute(adapt_query(query), tuple(params or ()))
        return self

    def executemany(self, query: str, rows: list[tuple]):
        self._cursor.executemany(adapt_query(query), rows)
        return self

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not self._dictionary:
            return rows
        cols = [d[0] for d in (self._cursor.description or [])]
        return [dict(zip(cols, row)) for row in rows]

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None or not self._dictionary:
            return row
        cols = [d[0] for d in (self._cursor.description or [])]
        return dict(zip(cols, row))

    @property
    def lastrowid(self) -> int:
        return int(self._cursor.lastrowid)

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cursor.close()
        return False


class SQLiteConnectionAdapter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def cursor(self, dictionary: bool = False):
        return SQLiteCursorAdapter(self._conn.cursor(), dictionary=dictionary)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def initialize_database() -> None:
    if is_sqlite():
        SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema = _schema_path("schema_sqlite.sql").read_text(encoding="utf-8")
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        try:
            conn.executescript(schema)
            conn.commit()
        finally:
            conn.close()
        return

    if mysql is None or getattr(mysql, "connector", None) is None:
        raise RuntimeError("mysql-connector-python est requis pour DB_ENGINE=mysql.")

    schema = _schema_path("schema_mysql.sql").read_text(encoding="utf-8")
    cfg = DB_CONFIG.copy()
    cfg.pop("database", None)
    conn = mysql.connector.connect(**cfg)
    try:
        with conn.cursor() as cursor:
            for statement in [s.strip() for s in schema.split(";") if s.strip()]:
                cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _ensure_schema_ready() -> None:
    global _SCHEMA_BOOTSTRAPPED
    if _SCHEMA_BOOTSTRAPPED:
        return
    initialize_database()
    _SCHEMA_BOOTSTRAPPED = True


def column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    if is_sqlite():
        with conn.cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
        return any(str(row[1]).lower() == column_name.lower() for row in rows)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name=%s AND column_name=%s
            """,
            (table_name, column_name),
        )
        return int(cursor.fetchone()[0]) > 0


@contextmanager
def get_connection():
    _ensure_schema_ready()
    if is_sqlite():
        raw_conn = sqlite3.connect(str(SQLITE_DB_PATH))
        raw_conn.execute("PRAGMA foreign_keys = ON")
        conn = SQLiteConnectionAdapter(raw_conn)
    else:
        if mysql is None or getattr(mysql, "connector", None) is None:
            raise RuntimeError("mysql-connector-python est requis pour DB_ENGINE=mysql.")
        conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(adapt_query(query), params or ())
            return cursor.fetchall()


def fetch_one(query: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(adapt_query(query), params or ())
            return cursor.fetchone()


def execute(query: str, params: Iterable[Any] | None = None) -> int:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(adapt_query(query), params or ())
            conn.commit()
            return cursor.lastrowid


def execute_many(query: str, rows: list[tuple]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(adapt_query(query), rows)
            conn.commit()
