"""
SQLite local database for Edge device.
Stores: local_embeddings (for offline matching) + offline_queue (sync buffer).
"""
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from edge.src.config import config

_lock = threading.Lock()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.LOCAL_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS local_embeddings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id      INTEGER NOT NULL UNIQUE,
                student_code    TEXT NOT NULL,
                full_name       TEXT NOT NULL,
                -- AES-256-GCM encrypted 512-dim float32 vector (synced from Cloud)
                embedding_enc   BLOB NOT NULL,
                updated_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS offline_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id      INTEGER NOT NULL,
                class_id        INTEGER NOT NULL,
                timestamp       TEXT NOT NULL,
                confidence      REAL,
                liveness_score  REAL,
                method          TEXT DEFAULT 'face',
                status          TEXT DEFAULT 'present',
                sync_status     TEXT DEFAULT 'PENDING',
                retry_count     INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_queue_sync ON offline_queue(sync_status);
            CREATE INDEX IF NOT EXISTS idx_embed_student ON local_embeddings(student_id);
        """)
        conn.commit()
        conn.close()

# ── Embeddings ──────────────────────────────────────────────────────────────

def upsert_embedding(student_id: int, student_code: str, full_name: str, enc_bytes: bytes):
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO local_embeddings (student_id, student_code, full_name, embedding_enc, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(student_id) DO UPDATE SET
                student_code = excluded.student_code,
                full_name    = excluded.full_name,
                embedding_enc = excluded.embedding_enc,
                updated_at   = excluded.updated_at
        """, (student_id, student_code, full_name, enc_bytes))
        conn.commit()
        conn.close()

def get_all_embeddings() -> List[sqlite3.Row]:
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT student_id, student_code, full_name, embedding_enc FROM local_embeddings"
        ).fetchall()
        conn.close()
    return rows

# ── Offline Queue ────────────────────────────────────────────────────────────

def enqueue_attendance(
    student_id: int,
    class_id: int,
    timestamp: datetime,
    confidence: float,
    liveness_score: float,
    method: str = "face",
    att_status: str = "present"
):
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO offline_queue
                (student_id, class_id, timestamp, confidence, liveness_score, method, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (student_id, class_id, timestamp.isoformat(), confidence, liveness_score, method, att_status))
        conn.commit()
        conn.close()

def get_pending_records(limit: int = 50) -> List[sqlite3.Row]:
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT * FROM offline_queue
            WHERE sync_status = 'PENDING'
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    return rows

def mark_synced(record_id: int):
    with _lock:
        conn = get_conn()
        conn.execute(
            "UPDATE offline_queue SET sync_status='SYNCED' WHERE id=?", (record_id,)
        )
        conn.commit()
        conn.close()

def increment_retry(record_id: int):
    with _lock:
        conn = get_conn()
        conn.execute("""
            UPDATE offline_queue
            SET retry_count = retry_count + 1,
                sync_status = CASE WHEN retry_count >= 5 THEN 'FAILED' ELSE 'PENDING' END
            WHERE id = ?
        """, (record_id,))
        conn.commit()
        conn.close()