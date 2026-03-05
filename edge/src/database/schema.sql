-- Edge device local SQLite schema
-- Applied automatically by local_db.py:init_db() — this file is for reference.

CREATE TABLE IF NOT EXISTS local_embeddings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL UNIQUE,
    student_code  TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    embedding_enc BLOB    NOT NULL,        -- AES-256-GCM encrypted 512-dim float32
    updated_at    TEXT    DEFAULT (datetime("now"))
);

CREATE TABLE IF NOT EXISTS offline_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL,
    class_id       TEXT NOT NULL,
    timestamp      TEXT    NOT NULL,       -- ISO-8601 UTC
    confidence     REAL,
    liveness_score REAL,
    method         TEXT    DEFAULT "face",
    status         TEXT    DEFAULT "present",
    sync_status    TEXT    DEFAULT "PENDING",  -- PENDING | SYNCED | FAILED
    retry_count    INTEGER DEFAULT 0,
    created_at     TEXT    DEFAULT (datetime("now"))
);

CREATE INDEX IF NOT EXISTS idx_queue_sync    ON offline_queue(sync_status);
CREATE INDEX IF NOT EXISTS idx_embed_student ON local_embeddings(student_id);
