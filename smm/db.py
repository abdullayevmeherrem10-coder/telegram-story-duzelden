import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    image_headline TEXT NOT NULL,
    image_subtext TEXT NOT NULL,
    image_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | published
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, model)
);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with _conn() as c:
        c.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def bump_usage(model: str) -> int:
    """Modelin bugünkü sorğu sayğacını artırır, yeni dəyəri qaytarır."""
    with _conn() as c:
        c.execute(
            "INSERT INTO usage (date, model, count) VALUES (?,?,1) "
            "ON CONFLICT(date, model) DO UPDATE SET count = count + 1",
            (_today(), model))
        row = c.execute("SELECT count FROM usage WHERE date=? AND model=?",
                        (_today(), model)).fetchone()
        return row["count"]


def set_usage_at_least(model: str, value: int):
    """Limit dolduğu biliniəndə sayğacı ən azı həmin dəyərə qaldırır."""
    with _conn() as c:
        c.execute(
            "INSERT INTO usage (date, model, count) VALUES (?,?,?) "
            "ON CONFLICT(date, model) DO UPDATE SET count = MAX(count, excluded.count)",
            (_today(), model, value))


def usage_today(model: str) -> int:
    with _conn() as c:
        row = c.execute("SELECT count FROM usage WHERE date=? AND model=?",
                        (_today(), model)).fetchone()
        return row["count"] if row else 0


def get_state(key: str, default: str | None = None) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key: str, value: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO state (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value))


def add_post(idea: str, caption: str, hashtags: str,
             image_headline: str, image_subtext: str, image_path: str | None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO posts (idea, caption, hashtags, image_headline, image_subtext, "
            "image_path, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (idea, caption, hashtags, image_headline, image_subtext,
             image_path, "pending", _now(), _now()),
        )
        return cur.lastrowid


def set_status(post_id: int, status: str):
    with _conn() as c:
        c.execute("UPDATE posts SET status=?, updated_at=? WHERE id=?",
                  (status, _now(), post_id))


def delete_post(post_id: int) -> dict | None:
    """Postu bazadan silir, silinən sətri qaytarır."""
    with _conn() as c:
        row = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
        return dict(row) if row else None


def get_post(post_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None


def list_posts(status: str | None = None, limit: int = 20) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM posts WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
