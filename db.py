"""SQLite-backed store for candidate items, drafts, and review state.

This doubles as the "memory / context store" from the architecture diagram:
it remembers what's been seen, scored, drafted, reviewed, and posted so
nothing gets processed twice and threads can be tracked over time.
"""
import sqlite3
import time
from contextlib import contextmanager

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reddit_id TEXT UNIQUE NOT NULL,      -- e.g. "t1_abc123" or "t3_xyz789"
    kind TEXT NOT NULL,                  -- "submission" | "comment"
    subreddit TEXT,
    author TEXT,
    permalink TEXT,
    body TEXT,
    matched_keyword TEXT,
    is_reply_to_us INTEGER DEFAULT 0,
    parent_our_comment_id TEXT,          -- set when this is a reply to our comment
    thread_root_id TEXT,                 -- top-level submission id, for context

    relevance_score REAL,
    relevance_reasoning TEXT,
    should_mention_product INTEGER,
    draft_reply TEXT,
    final_reply TEXT,                    -- filled in / edited by the human reviewer

    status TEXT NOT NULL DEFAULT 'new',
    -- new -> scored -> pending_review -> approved/rejected -> posted
    posted_comment_id TEXT,

    fetched_at INTEGER,
    scored_at INTEGER,
    reviewed_at INTEGER,
    posted_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def item_exists(reddit_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM items WHERE reddit_id = ?", (reddit_id,)
        ).fetchone()
        return row is not None


def insert_candidate(
    reddit_id: str,
    kind: str,
    subreddit: str,
    author: str,
    permalink: str,
    body: str,
    matched_keyword: str = "",
    is_reply_to_us: bool = False,
    parent_our_comment_id: str | None = None,
    thread_root_id: str | None = None,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO items
                (reddit_id, kind, subreddit, author, permalink, body,
                 matched_keyword, is_reply_to_us, parent_our_comment_id,
                 thread_root_id, status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                reddit_id, kind, subreddit, author, permalink, body,
                matched_keyword, int(is_reply_to_us), parent_our_comment_id,
                thread_root_id, int(time.time()),
            ),
        )


def get_items_by_status(status: str, limit: int = 50, order: str = "ASC"):
    """Fetch items by status.

    order="ASC"  -> oldest first (FIFO; used by the posting agent).
    order="DESC" -> newest first (used by the review dashboard so freshly
                    fetched items appear at the top).
    """
    direction = "DESC" if str(order).upper() == "DESC" else "ASC"
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM items WHERE status = ? ORDER BY fetched_at {direction} LIMIT ?",
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def update_item(reddit_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [reddit_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE items SET {cols} WHERE reddit_id = ?", values)


def get_item(reddit_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM items WHERE reddit_id = ?", (reddit_id,)
        ).fetchone()
        return dict(row) if row else None


def get_our_posted_comment_ids() -> list[str]:
    """Used by reply_tracker.py to know which of our comments to watch."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT posted_comment_id FROM items "
            "WHERE status = 'posted' AND posted_comment_id IS NOT NULL"
        ).fetchall()
        return [r["posted_comment_id"] for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {settings.DB_PATH}")
