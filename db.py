"""SQLite-backed API key store and usage logger for LeadsClean Cloud API."""

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

DB_PATH = os.getenv("LEADSCLEAN_DB", "leadsclean.db")

PLAN_LIMITS: dict[str, int] = {
    "trial":   100,
    "starter": 500,
    "growth":  2_000,
    "pro":     10_000,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    key            TEXT PRIMARY KEY,
    email          TEXT NOT NULL,
    plan           TEXT NOT NULL DEFAULT 'starter',
    calls_used     INTEGER NOT NULL DEFAULT 0,
    monthly_limit  INTEGER NOT NULL DEFAULT 500,
    created_at     TEXT NOT NULL,
    reset_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key     TEXT NOT NULL,
    target_url  TEXT NOT NULL,
    model       TEXT NOT NULL,
    latency_ms  INTEGER,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't exist. Called on server startup."""
    with _conn() as con:
        con.executescript(_SCHEMA)


def _next_reset() -> str:
    today = date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return date(year, month, 1).isoformat()


# ---------------------------------------------------------------------------
# Key management — used by manage_keys.py
# ---------------------------------------------------------------------------

def create_key(email: str, plan: str = "starter") -> str:
    """Issue a new API key. Returns the raw key string (shown once)."""
    key = "lc_" + secrets.token_hex(24)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO api_keys "
            "(key, email, plan, calls_used, monthly_limit, created_at, reset_at) "
            "VALUES (?, ?, ?, 0, ?, ?, ?)",
            (key, email, plan, limit, now, _next_reset()),
        )
    return key


def list_keys() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT key, email, plan, calls_used, monthly_limit, created_at, reset_at "
            "FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_key(key: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM api_keys WHERE key = ?", (key,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Per-request auth helpers
# ---------------------------------------------------------------------------

class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def _load_and_maybe_reset(con: sqlite3.Connection, key: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise AuthError(401, "Invalid API key.")
    if date.today().isoformat() >= row["reset_at"]:
        con.execute(
            "UPDATE api_keys SET calls_used = 0, reset_at = ? WHERE key = ?",
            (_next_reset(), key),
        )
        con.commit()
        row = con.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
    return row


def get_key_info(key: str) -> dict:
    """Read key metadata without incrementing calls_used (for /usage endpoint)."""
    with _conn() as con:
        row = _load_and_maybe_reset(con, key)
    return {"key": key, **dict(row)}


def check_and_increment(key: str) -> dict:
    """Validate key, handle monthly reset, and increment calls_used atomically.

    Returns key metadata dict on success. Raises AuthError on failure.
    """
    with _conn() as con:
        row = _load_and_maybe_reset(con, key)
        if row["calls_used"] >= row["monthly_limit"]:
            raise AuthError(
                429,
                f"Monthly limit of {row['monthly_limit']} calls reached. "
                "Resets on the 1st of next month — contact us to upgrade.",
            )
        con.execute(
            "UPDATE api_keys SET calls_used = calls_used + 1 WHERE key = ?", (key,)
        )
        updated = con.execute(
            "SELECT calls_used, monthly_limit, reset_at, email, plan FROM api_keys WHERE key = ?",
            (key,),
        ).fetchone()
    return {"key": key, **dict(updated)}


# ---------------------------------------------------------------------------
# Usage logging — always called via BackgroundTasks; never raises
# ---------------------------------------------------------------------------

def log_usage(api_key: str, target_url: str, model: str, latency_ms: int, status: str) -> None:
    try:
        with _conn() as con:
            con.execute(
                "INSERT INTO usage_log (api_key, target_url, model, latency_ms, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (api_key, target_url, model, latency_ms, status, datetime.utcnow().isoformat()),
            )
    except Exception:
        pass  # Never let logging kill a live request
