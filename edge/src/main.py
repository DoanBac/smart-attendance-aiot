"""
Edge main entry point.
- Initializes local DB
- Starts SyncDaemon
- Runs the attendance recognition loop
- Posts confirmed attendance to Cloud (or queues offline)
"""
import time
import logging
import signal
import sys
import requests
import base64
from datetime import datetime, timezone

from edge.src.config import config
from edge.src.utils.logger import setup_logging
from edge.src.database import local_db
from edge.src.database.local_db import enqueue_attendance, get_all_embeddings
from edge.src.camera.stream import CameraStream
from edge.src.ai.pipeline import AttendancePipeline, LivenessSession
from edge.src.ai.face_embedding import FaceEmbedder
from edge.src.sync.queue_sync import SyncDaemon
from edge.src.core.encryption import decrypt_embedding

setup_logging()
logger = logging.getLogger("edge.main")

COOLDOWN_SEC = 10   # Don't re-recognize same student within N seconds
_recently_marked: dict = {}   # student_id → last_marked timestamp


def _load_embeddings_to_pipeline(pipeline: AttendancePipeline):
    rows = get_all_embeddings()
    decoded = []
    for row in rows:
        try:
            vec = decrypt_embedding(bytes(row["embedding_enc"]))
            decoded.append((row["student_id"], row["student_code"], row["full_name"], vec))
        except Exception as e:
            logger.warning(f"Failed to decrypt embedding for student {row['student_id']}: {e}")
    pipeline.load_local_embeddings(decoded)


def _post_attendance(student_id: int, confidence: float, liveness_score: float):
    ts = datetime.now(timezone.utc)
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
            timeout=10
        )
        if resp.status_code == 201:
            logger.info(f"✅ Attendance posted: student {student_id} ({confidence:.3f})")
            return True
    except Exception as e:
        logger.warning(f"Cloud unreachable, queuing offline: {e}")

    # Offline fallback
    enqueue_attendance(
        student_id=student_id,
        class_id=config.CLASS_ID,
        timestamp=ts,
        confidence=confidence,
        liveness_score=liveness_score,
    )
    return False


def main():
    logger.info("=== AIoT Edge Attendance System Starting ===")

    # Init local DB
    local_db.init_db()

    # Start sync daemon (with exponential backoff)
    daemon = SyncDaemon()
    daemon.start()

    # Give daemon time to pull embeddings on first run
    time.sleep(3)

    # Init AI pipeline
    pipeline = AttendancePipeline()
    _load_embeddings_to_pipeline(pipeline)

    # Open camera using threaded stream
    cam = CameraStream(
        source=config.CAMERA_SOURCE,
        width=config.FRAME_WIDTH,
        height=config.FRAME_HEIGHT,
        fps=config.CAPTURE_FPS,
    ).start()

    logger.info("Camera opened. Recognition loop running...")

    # Graceful shutdown
    def _shutdown(sig, frame):
        logger.info("Shutting down...")
        daemon.stop()
        cam.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Per-face liveness sessions
    active_sessions: dict = {}

    frame_idx = 0
    while True:
        frame = cam.read()
        if frame is None:
            time.sleep(0.05)
            continue

        frame_idx += 1
        # Frame skipping to reduce CPU
        if frame_idx % config.PROCESS_EVERY_N_FRAMES != 0:
            continue

        # Re-load embeddings every 5 minutes (picks up new enrollments)
        if frame_idx % (5 * 60 * config.CAPTURE_FPS // config.PROCESS_EVERY_N_FRAMES) == 0:
            _load_embeddings_to_pipeline(pipeline)

        # Get or create a liveness session (keyed by face position hash — simplified here)
        session_key = "primary"
        if session_key not in active_sessions:
            active_sessions[session_key] = LivenessSession(fps=config.CAPTURE_FPS)

        ls = active_sessions[session_key]

        if ls.timeout:
            logger.debug("Liveness session timed out, resetting.")
            active_sessions[session_key] = LivenessSession(fps=config.CAPTURE_FPS)
            ls = active_sessions[session_key]

        result = pipeline.process_frame_attendance(frame, ls)

        if result.get("recognized"):
            rec = result["recognized"]
            sid = rec["student_id"]
            now = time.time()

            # Cooldown check
            last = _recently_marked.get(sid, 0)
            if now - last < COOLDOWN_SEC:
                continue

            _recently_marked[sid] = now
            logger.info(
                f"Recognized: {rec['name']} (id={sid}, sim={rec['confidence']}, "
                f"live={rec['liveness_score']})"
            )
            _post_attendance(sid, rec["confidence"], rec["liveness_score"])
            # Reset liveness session after successful attendance
            active_sessions.pop(session_key, None)


if __name__ == "__main__":
    main()
