"""SQLite-backed API key store and usage logger for LeadsClean Cloud API.

Security model
--------------
Raw API keys (lc_<48 hex chars>) are shown to the user exactly once at
creation time and are NEVER stored.  The database stores only:
  - key_hash   SHA-256(raw_key)  — used for lookup and validation
  - key_prefix first 12 chars    — display hint for operators (e.g. "lc_630b0a79…")

If the database is ever leaked, raw keys cannot be recovered from the hashes
because the keys have 192 bits of entropy, making preimage attacks infeasible.
"""

import hashlib
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
    key_hash       TEXT PRIMARY KEY,
    key_prefix     TEXT NOT NULL,
    email          TEXT NOT NULL,
    plan           TEXT NOT NULL DEFAULT 'starter',
    calls_used     INTEGER NOT NULL DEFAULT 0,
    monthly_limit  INTEGER NOT NULL DEFAULT 500,
    created_at     TEXT NOT NULL,
    reset_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash    TEXT NOT NULL,
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


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _next_reset() -> str:
    today = date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return date(year, month, 1).isoformat()


# ---------------------------------------------------------------------------
# Key management — used by manage_keys.py
# ---------------------------------------------------------------------------

def create_key(email: str, plan: str = "starter") -> str:
    """Issue a new API key. Returns the raw key string — shown once, never stored."""
    raw_key = "lc_" + secrets.token_hex(24)
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12]           # e.g. "lc_630b0a79" — display hint only
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO api_keys "
            "(key_hash, key_prefix, email, plan, calls_used, monthly_limit, created_at, reset_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
            (key_hash, key_prefix, email, plan, limit, now, _next_reset()),
        )
    return raw_key


def list_keys() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT key_hash, key_prefix, email, plan, calls_used, monthly_limit, "
            "created_at, reset_at FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_key(raw_key: str) -> bool:
    """Revoke by raw key (lc_...) or by key_hash (64-char hex)."""
    key_hash = _hash_key(raw_key) if raw_key.startswith("lc_") else raw_key
    with _conn() as con:
        cur = con.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Per-request auth helpers
# ---------------------------------------------------------------------------

class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def _load_and_maybe_reset(con: sqlite3.Connection, key_hash: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
    if row is None:
        raise AuthError(401, "Invalid API key.")
    if date.today().isoformat() >= row["reset_at"]:
        con.execute(
            "UPDATE api_keys SET calls_used = 0, reset_at = ? WHERE key_hash = ?",
            (_next_reset(), key_hash),
        )
        con.commit()
        row = con.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
    return row


def get_key_info(raw_key: str) -> dict:
    """Read key metadata without incrementing calls_used (for GET /usage)."""
    key_hash = _hash_key(raw_key)
    with _conn() as con:
        row = _load_and_maybe_reset(con, key_hash)
    return {"key_hash": key_hash, **dict(row)}


def check_and_increment(raw_key: str) -> dict:
    """Validate key, handle monthly reset, and increment calls_used atomically.

    Returns key metadata dict on success. Raises AuthError on failure.
    key_hash is included in the returned dict for use in usage_log.
    """
    key_hash = _hash_key(raw_key)
    with _conn() as con:
        row = _load_and_maybe_reset(con, key_hash)
        if row["calls_used"] >= row["monthly_limit"]:
            raise AuthError(
                429,
                f"Monthly limit of {row['monthly_limit']} calls reached. "
                "Resets on the 1st of next month — contact us to upgrade.",
            )
        con.execute(
            "UPDATE api_keys SET calls_used = calls_used + 1 WHERE key_hash = ?", (key_hash,)
        )
        updated = con.execute(
            "SELECT calls_used, monthly_limit, reset_at, email, plan "
            "FROM api_keys WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
    return {"key_hash": key_hash, **dict(updated)}


# ---------------------------------------------------------------------------
# Usage logging — called via BackgroundTasks; never raises
# ---------------------------------------------------------------------------

def log_usage(key_hash: str, target_url: str, model: str, latency_ms: int, status: str) -> None:
    try:
        with _conn() as con:
            con.execute(
                "INSERT INTO usage_log (key_hash, target_url, model, latency_ms, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key_hash, target_url, model, latency_ms, status, datetime.utcnow().isoformat()),
            )
    except Exception:
        pass  # Never let logging kill a live request
