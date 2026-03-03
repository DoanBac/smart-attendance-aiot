"""
Background daemon: sync offline_queue to Cloud with exponential backoff.
Also syncs embeddings from Cloud to local SQLite cache.
"""
import time
import base64
import logging
import threading
import requests
from typing import Optional
import numpy as np

from edge.src.config import config
from edge.src.database import local_db
from edge.src.core.encryption import decrypt_embedding

logger = logging.getLogger(__name__)

def _headers() -> dict:
    return {"X-Device-Token": config.DEVICE_TOKEN, "Content-Type": "application/json"}

def _is_online() -> bool:
    try:
        requests.get(f"{config.CLOUD_API_URL}/health", timeout=5)
        return True
    except Exception:
        return False

def sync_attendance_queue():
    """Push PENDING records from offline_queue to Cloud."""
    if not _is_online():
        return

    pending = local_db.get_pending_records(limit=50)
    if not pending:
        return

    logger.info(f"Syncing {len(pending)} pending records...")
    records = []
    ids = []
    for row in pending:
        records.append({
            "student_id": row["student_id"],
            "class_id": row["class_id"],
            "timestamp": row["timestamp"],
            "confidence": row["confidence"],
            "liveness_score": row["liveness_score"],
            "method": row["method"],
            "status": row["status"],
        })
        ids.append(row["id"])

    try:
        resp = requests.post(
            f"{config.CLOUD_API_URL}/api/attendance/bulk-sync",
            json={"records": records, "device_token": config.DEVICE_TOKEN},
            headers=_headers(),
            timeout=30
        )
        if resp.status_code == 200:
            for rid in ids:
                local_db.mark_synced(rid)
            logger.info(f"Synced {len(ids)} records.")
        else:
            for rid in ids:
                local_db.increment_retry(rid)
            logger.warning(f"Sync failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        for rid in ids:
            local_db.increment_retry(rid)
        logger.error(f"Sync request error: {e}")

def sync_embeddings_from_cloud():
    """Download latest embeddings from Cloud and store in local SQLite."""
    if not _is_online():
        return

    logger.info("Refreshing local embeddings from Cloud...")
    try:
        resp = requests.get(
            f"{config.CLOUD_API_URL}/api/devices/embeddings/{config.CLASS_ID}",
            headers=_headers(),
            timeout=60
        )
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch embeddings: {resp.status_code}")
            return

        data = resp.json()
        for student in data.get("students", []):
            enc_bytes = base64.b64decode(student["embedding_enc_b64"])
            local_db.upsert_embedding(
                student_id=student["student_id"],
                student_code=student["student_code"],
                full_name=student["full_name"],
                enc_bytes=enc_bytes   # Still AES-encrypted, decrypted at inference time
            )
        logger.info(f"Updated {len(data.get('students', []))} embeddings locally.")
    except Exception as e:
        logger.error(f"Embedding sync error: {e}")

def send_heartbeat():
    if not _is_online():
        return
    try:
        requests.post(
            f"{config.CLOUD_API_URL}/api/devices/heartbeat",
            json={"status": "active"},
            headers=_headers(),
            timeout=10
        )
    except Exception:
        pass

class SyncDaemon(threading.Thread):
    """Background thread: sync queue + pull embeddings with exponential backoff when offline."""

    MIN_INTERVAL = 5       # seconds — fastest retry when online
    MAX_INTERVAL = 300     # seconds — cap at 5 min when offline

    def __init__(self):
        super().__init__(daemon=True, name="SyncDaemon")
        self._stop_event = threading.Event()
        self._online = False
        self._backoff = self.MIN_INTERVAL

    def run(self):
        logger.info("SyncDaemon started.")
        # Pull embeddings immediately on startup
        sync_embeddings_from_cloud()

        embed_counter = 0
        EMBED_EVERY_N = 10  # re-pull embeddings every ~10 successful sync cycles

        while not self._stop_event.is_set():
            try:
                online = _is_online()
                if online != self._online:
                    logger.info("Network %s", "ONLINE" if online else "OFFLINE")
                self._online = online

                if online:
                    sync_attendance_queue()
                    send_heartbeat()
                    embed_counter += 1
                    if embed_counter >= EMBED_EVERY_N:
                        sync_embeddings_from_cloud()
                        embed_counter = 0
                    # Reset backoff on success
                    self._backoff = self.MIN_INTERVAL
                else:
                    # Exponential backoff: 5s → 10s → 20s → ... → 300s
                    self._backoff = min(self._backoff * 2, self.MAX_INTERVAL)
                    logger.debug("Offline — next retry in %ds", self._backoff)

            except Exception as e:
                logger.error("SyncDaemon error: %s", e)
                self._backoff = min(self._backoff * 2, self.MAX_INTERVAL)

            self._stop_event.wait(timeout=self._backoff)

        logger.info("SyncDaemon stopped.")

    @property
    def is_online(self) -> bool:
        return self._online

    def stop(self):
        self._stop_event.set()