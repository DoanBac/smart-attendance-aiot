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
                updated_at      TEXT DEFAULT (datetime('now')),
                is_local        INTEGER DEFAULT 0  -- 1 = enrolled directly on edge (takes priority over cloud sync)
            );

            CREATE TABLE IF NOT EXISTS offline_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id      INTEGER NOT NULL,
                class_id        TEXT NOT NULL,
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
        # Migrate: add is_local column if it doesn't exist (safe on old DBs)
        try:
            cur.execute("ALTER TABLE local_embeddings ADD COLUMN is_local INTEGER DEFAULT 0")
        except Exception:
            pass  # Column already exists
        conn.commit()
        conn.close()

# ── Embeddings ──────────────────────────────────────────────────────────────

def upsert_embedding(student_id: int, student_code: str, full_name: str, enc_bytes: bytes):
    """Upsert cloud-synced embedding. Skips update if student has a local (edge-enrolled) embedding."""
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO local_embeddings (student_id, student_code, full_name, embedding_enc, updated_at, is_local)
            VALUES (?, ?, ?, ?, datetime('now'), 0)
            ON CONFLICT(student_id) DO UPDATE SET
                student_code  = excluded.student_code,
                full_name     = excluded.full_name,
                embedding_enc = excluded.embedding_enc,
                updated_at    = excluded.updated_at
            WHERE is_local = 0
        """, (student_id, student_code, full_name, enc_bytes))
        conn.commit()
        conn.close()


def lookup_by_code(student_code: str) -> Optional[Dict[str, Any]]:
    """Return student info {student_id, student_code, full_name} from local cache by student_code, or None."""
    with _lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT student_id, student_code, full_name FROM local_embeddings WHERE student_code = ? LIMIT 1",
            (student_code,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def enroll_locally(student_id: str, student_code: str, full_name: str, enc_bytes: bytes):
    """Store an embedding extracted on-device. Marked is_local=1 — cloud sync cannot overwrite."""
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO local_embeddings (student_id, student_code, full_name, embedding_enc, updated_at, is_local)
            VALUES (?, ?, ?, ?, datetime('now'), 1)
            ON CONFLICT(student_id) DO UPDATE SET
                student_code  = excluded.student_code,
                full_name     = excluded.full_name,
                embedding_enc = excluded.embedding_enc,
                updated_at    = excluded.updated_at,
                is_local      = 1
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
    class_id: str,
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

def get_recent_attendance(limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent attendance records from offline_queue, enriched with student name."""
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT q.id, q.student_id, q.timestamp, q.confidence, q.liveness_score,
                   q.sync_status, e.student_code, e.full_name
            FROM offline_queue q
            LEFT JOIN local_embeddings e ON q.student_id = e.student_id
            ORDER BY q.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    return [dict(r) for r in rows]


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


def get_pending_count() -> int:
    """Return count of queue records with sync_status='PENDING'."""
    with _lock:
        conn = get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM offline_queue WHERE sync_status='PENDING'"
        ).fetchone()[0]
        conn.close()
    return count


def post_or_queue_attendance(
    student_id: str,
    confidence: float,
    liveness_score: float,
) -> bool:
    """
    Try to POST attendance to cloud; fall back to offline queue on failure.
    Shared by AI thread (main.py) and Flask /mark endpoint (stream.py).
    Returns True if cloud POST succeeded.
    """
    import requests
    from datetime import datetime
    from edge.src.config import config

    ts = datetime.now()  # local time (UTC+7) — stored & displayed consistently
    try:
        resp = requests.post(
            f"{config.CLOUD_API_URL}/api/attendance/",
            json={
                "student_id": student_id,
                "class_id": config.CLASS_ID,
                "timestamp": ts.isoformat(),
                "confidence": confidence,
                "liveness_score": liveness_score,
                "method": "face",
                "status": "present",
            },
            headers={"X-Device-Token": config.DEVICE_TOKEN, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 201:
            return True
    except Exception:
        pass

    # Offline fallback
    enqueue_attendance(
        student_id=student_id,
        class_id=config.CLASS_ID,
        timestamp=ts,
        confidence=confidence,
        liveness_score=liveness_score,
    )
    return False