"""
SQLite storage.

Two tables: `decisions` (one row per verdict, with the per-signal scores kept
as JSON so the log can show why we decided what we did) and `appeals` (one row
per appeal, tied back to a decision by content_id). Filing an appeal sets the
decision's status to 'under_review'. The whole thing is one file that gets
created the first time we connect.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

# Keep the db file next to this module so it doesn't matter where you run from.
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "provenance_guard.db")


def _connect():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Make the tables if they aren't there yet. Fine to call on every boot."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                content_id      TEXT PRIMARY KEY,
                content_type    TEXT NOT NULL,
                excerpt         TEXT NOT NULL,
                result          TEXT NOT NULL,
                ai_probability  REAL NOT NULL,
                confidence      REAL NOT NULL,
                signals_json    TEXT NOT NULL,
                label           TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'classified',
                created_at      TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appeals (
                id          TEXT PRIMARY KEY,
                content_id  TEXT NOT NULL,
                reasoning   TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (content_id) REFERENCES decisions (content_id)
            )
            """
        )


def insert_decision(*, content_type, excerpt, result, ai_probability,
                    confidence, signals, label):
    """Save a decision, hand back the new content_id."""
    content_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO decisions (content_id, content_type, excerpt, result,
                                   ai_probability, confidence, signals_json,
                                   label, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'classified', ?)
            """,
            (
                content_id,
                content_type,
                excerpt,
                result,
                ai_probability,
                confidence,
                json.dumps(signals),
                label,
                _now(),
            ),
        )
    return content_id


def get_decision(content_id):
    """One decision as a dict, or None if we don't have it."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM decisions WHERE content_id = ?", (content_id,)
        ).fetchone()
    return _decision_to_dict(row) if row else None


def insert_appeal(*, content_id, reasoning):
    """Log an appeal and mark the decision under_review.

    Returns the appeal id, or None if the content_id doesn't exist.
    """
    with _connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM decisions WHERE content_id = ?", (content_id,)
        ).fetchone()
        if existing is None:
            return None
        appeal_id = uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO appeals (id, content_id, reasoning, created_at) "
            "VALUES (?, ?, ?, ?)",
            (appeal_id, content_id, reasoning, _now()),
        )
        conn.execute(
            "UPDATE decisions SET status = 'under_review' WHERE content_id = ?",
            (content_id,),
        )
    return appeal_id


def set_status(content_id, status):
    with _connect() as conn:
        conn.execute(
            "UPDATE decisions SET status = ? WHERE content_id = ?",
            (status, content_id),
        )


def get_log():
    """Every decision, newest first, with its appeals attached."""
    with _connect() as conn:
        decisions = conn.execute(
            "SELECT * FROM decisions ORDER BY created_at DESC"
        ).fetchall()
        appeals = conn.execute(
            "SELECT * FROM appeals ORDER BY created_at ASC"
        ).fetchall()

    appeals_by_content = {}
    for a in appeals:
        appeals_by_content.setdefault(a["content_id"], []).append(
            {
                "appeal_id": a["id"],
                "reasoning": a["reasoning"],
                "created_at": a["created_at"],
            }
        )

    log = []
    for row in decisions:
        entry = _decision_to_dict(row)
        entry["appeals"] = appeals_by_content.get(row["content_id"], [])
        log.append(entry)
    return log


def _decision_to_dict(row):
    return {
        "content_id": row["content_id"],
        "content_type": row["content_type"],
        "excerpt": row["excerpt"],
        "result": row["result"],
        "ai_probability": row["ai_probability"],
        "confidence": row["confidence"],
        "signals": json.loads(row["signals_json"]),
        "label": row["label"],
        "status": row["status"],
        "created_at": row["created_at"],
    }
