"""
SQLite database for audit log and content records.

Schema:
    submissions — every classification decision
    appeals     — every appeal filed against a decision
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "audit.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS submissions (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_preview TEXT NOT NULL,
                attribution TEXT NOT NULL,
                ai_probability REAL NOT NULL,
                confidence_score REAL NOT NULL,
                signals_json TEXT NOT NULL,
                appeal_status TEXT NOT NULL DEFAULT 'none'
            );

            CREATE TABLE IF NOT EXISTS appeals (
                id          TEXT PRIMARY KEY,
                submission_id TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                creator_reasoning TEXT NOT NULL,
                FOREIGN KEY (submission_id) REFERENCES submissions(id)
            );

            CREATE TABLE IF NOT EXISTS certificates (
                id          TEXT PRIMARY KEY,
                submission_id TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                creator_statement TEXT NOT NULL,
                verification_token TEXT NOT NULL,
                FOREIGN KEY (submission_id) REFERENCES submissions(id)
            );
        """)


def _make_id(prefix: str) -> str:
    import time, random
    raw = f"{prefix}-{time.time_ns()}-{random.randint(0, 999999)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def log_submission(content: str, result: dict) -> str:
    """Insert a submission into the audit log and return its ID."""
    submission_id = _make_id("sub")
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    content_preview = content[:200] + ("..." if len(content) > 200 else "")
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO submissions
                (id, created_at, content_hash, content_preview, attribution,
                 ai_probability, confidence_score, signals_json, appeal_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'none')
            """,
            (
                submission_id,
                now,
                content_hash,
                content_preview,
                result["attribution"],
                result["ai_probability"],
                result["confidence_score"],
                json.dumps(result["signals"]),
            ),
        )
    return submission_id


def log_appeal(submission_id: str, creator_reasoning: str) -> str:
    """Record an appeal and update the submission's appeal_status."""
    appeal_id = _make_id("app")
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        # Verify submission exists
        row = conn.execute(
            "SELECT id FROM submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Submission {submission_id!r} not found")

        conn.execute(
            "INSERT INTO appeals (id, submission_id, created_at, creator_reasoning) VALUES (?, ?, ?, ?)",
            (appeal_id, submission_id, now, creator_reasoning),
        )
        conn.execute(
            "UPDATE submissions SET appeal_status = 'under_review' WHERE id = ?",
            (submission_id,),
        )
    return appeal_id


def log_certificate(submission_id: str, creator_statement: str) -> dict:
    """Issue a provenance certificate for a submission."""
    import secrets
    cert_id = _make_id("cert")
    now = datetime.now(timezone.utc).isoformat()
    token = secrets.token_urlsafe(24)

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, attribution FROM submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Submission {submission_id!r} not found")

        conn.execute(
            """INSERT INTO certificates
               (id, submission_id, created_at, creator_statement, verification_token)
               VALUES (?, ?, ?, ?, ?)""",
            (cert_id, submission_id, now, creator_statement, token),
        )
    return {"certificate_id": cert_id, "verification_token": token, "issued_at": now}


def get_log(limit: int = 50, offset: int = 0) -> list[dict]:
    """Fetch recent audit log entries (submissions + their appeals)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.created_at, s.content_preview, s.attribution,
                   s.ai_probability, s.confidence_score, s.appeal_status,
                   a.creator_reasoning, a.created_at as appeal_at
            FROM submissions s
            LEFT JOIN appeals a ON a.submission_id = s.id
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    entries = []
    for row in rows:
        entry = dict(row)
        entries.append(entry)
    return entries


def get_submission(submission_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def get_analytics() -> dict:
    """Aggregate stats for the analytics dashboard."""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        ai_count = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE attribution = 'ai'"
        ).fetchone()[0]
        human_count = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE attribution = 'human'"
        ).fetchone()[0]
        uncertain_count = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE attribution = 'uncertain'"
        ).fetchone()[0]
        appeal_count = conn.execute("SELECT COUNT(*) FROM appeals").fetchone()[0]
        appeal_rate = round(appeal_count / total, 4) if total > 0 else 0
        avg_confidence = conn.execute(
            "SELECT AVG(confidence_score) FROM submissions"
        ).fetchone()[0] or 0

        # Recent trend: last 10 submissions
        recent = conn.execute(
            """SELECT attribution, ai_probability, created_at
               FROM submissions ORDER BY created_at DESC LIMIT 10"""
        ).fetchall()

    return {
        "total_submissions": total,
        "attribution_breakdown": {
            "ai": ai_count,
            "human": human_count,
            "uncertain": uncertain_count,
        },
        "appeal_count": appeal_count,
        "appeal_rate": appeal_rate,
        "average_confidence": round(avg_confidence, 4),
        "recent_submissions": [dict(r) for r in recent],
    }
