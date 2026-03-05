"""
Edge main entry point.
- Initializes local DB
- Starts SyncDaemon
- Runs the attendance recognition loop
- Posts confirmed attendance to Cloud (or queues offline)

Architecture:
  Camera thread  →  pushes raw JPEG at CAPTURE_FPS (smooth video, no blocking)
  AI thread      →  picks up latest frame, runs pipeline, overlays result JPEG
"""
import queue
import time
import logging
import signal
import sys
import threading
import cv2
from datetime import datetime, timezone

from edge.src.config import config
from edge.src.utils.logger import setup_logging
from edge.src.database import local_db
from edge.src.database.local_db import post_or_queue_attendance, get_all_embeddings
from edge.src.camera.stream import CameraStream
from edge.src.ai.pipeline import AttendancePipeline, LivenessSession
from edge.src.sync.queue_sync import SyncDaemon
from edge.src.core.encryption import decrypt_embedding
from edge.src.database.local_db import post_or_queue_attendance
from edge.src.web.state import shared
from edge.src.web.stream import start_server

setup_logging()
logger = logging.getLogger("edge.main")

COOLDOWN_SEC = 10   # Don't re-recognize same student within N seconds
_recently_marked: dict = {}   # student_id → last_marked timestamp

# Queue used to pass frames from camera loop → AI thread (size=1 = always latest)
_ai_queue: queue.Queue = queue.Queue(maxsize=1)
_shutdown_event = threading.Event()


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


# attendance posting now lives in local_db.post_or_queue_attendance (shared with Flask /mark)


# ──────────────────────────────────────────────────────────────────────────────
# AI inference thread — runs independently from camera loop
# ──────────────────────────────────────────────────────────────────────────────

def _ai_worker(pipeline: AttendancePipeline):
    """
    Continuously pull the latest frame from _ai_queue, run the full pipeline,
    annotate, and push the annotated JPEG to shared state.
    Runs in its own thread so camera loop is never blocked.
    """
    active_sessions: dict = {}
    embed_reload_counter = 0
    RELOAD_EVERY = max(1, (5 * 60 * config.CAPTURE_FPS) // max(config.PROCESS_EVERY_N_FRAMES, 1))

    while not _shutdown_event.is_set():
        try:
            frame = _ai_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        embed_reload_counter += 1
        if embed_reload_counter >= RELOAD_EVERY:
            embed_reload_counter = 0
            _load_embeddings_to_pipeline(pipeline)

        # Liveness session management
        session_key = "primary"
        if session_key not in active_sessions:
            active_sessions[session_key] = LivenessSession(fps=config.CAPTURE_FPS)

        ls = active_sessions[session_key]
        if ls.timeout:
            logger.debug("Liveness session timed out, resetting.")
            active_sessions[session_key] = LivenessSession(fps=config.CAPTURE_FPS)
            ls = active_sessions[session_key]

        try:
            result = pipeline.process_frame_attendance(frame, ls)
        except Exception as e:
            logger.warning(f"AI pipeline error: {e}")
            continue

        # Annotate frame
        display = frame.copy()
        bbox = result.get("face_bbox")
        if bbox:
            x1, y1, x2, y2 = bbox
            rec = result.get("recognized")
            if rec:
                color = (0, 255, 0)  # green — recognized
                label = f"{rec['name']} {rec['confidence']:.0%}"
            elif result.get("liveness_passed") is False and result["faces_detected"] > 0:
                color = (0, 165, 255)  # orange — liveness check in progress
                label = "Checking..."
            else:
                color = (0, 0, 255)   # red — face detected, unrecognized
                label = "Unknown"
            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display, label, (x1, max(y1 - 8, 16)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        _, buf = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 75])
        shared.update(buf.tobytes(), result)

        # ── Pose check (optional) ───────────────────────────────────────────
        pose_ok = True
        if shared.require_pose and result.get("faces_detected", 0) > 0:
            lm5 = result.get("landmarks")
            bbox = result.get("face_bbox")
            if lm5 is not None and bbox is not None:
                from edge.src.ai.liveness.head_movement import HeadPoseEstimator
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                est = HeadPoseEstimator(max(bw, 1), max(bh, 1))
                yaw, pitch, _roll = est.estimate(lm5)
                pose_ok = abs(yaw) < 22 and abs(pitch) < 22
        with shared._lock:
            shared.pose_rejected = (shared.require_pose and not pose_ok)

        if result.get("recognized"):
            rec = result["recognized"]
            sid = rec["student_id"]
            now = time.time()

            last = _recently_marked.get(sid, 0)
            if now - last < COOLDOWN_SEC:
                continue

            if shared.require_pose and not pose_ok:
                logger.debug(f"Pose check failed for {rec['name']} — skipping mark")
                continue

            _recently_marked[sid] = now
            logger.info(
                f"Recognized: {rec['name']} (id={sid}, sim={rec['confidence']:.3f}, "
                f"live={rec['liveness_score']:.2f})"
            )

            if shared.auto_attendance:
                post_or_queue_attendance(sid, rec["confidence"], rec["liveness_score"])
                active_sessions.pop(session_key, None)
            else:
                # Manual mode — expose to kiosk UI for confirmation
                shared.set_pending_mark({
                    "student_id": sid,
                    "name": rec["name"],
                    "student_code": rec.get("student_code", ""),
                    "confidence": round(rec["confidence"], 3),
                    "liveness_score": round(rec["liveness_score"], 3),
                })
                logger.info(f"Manual mode — waiting confirm for {rec['name']}")


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    logger.info("=== AIoT Edge Attendance System Starting ===")

    # Start web stream server in background thread
    web_thread = threading.Thread(target=start_server, daemon=True)
    web_thread.start()

    # Init local DB
    local_db.init_db()

    # Start sync daemon (with exponential backoff)
    daemon = SyncDaemon()
    daemon.start()

    # Give daemon time to pull embeddings on first run
    time.sleep(3)

    # Init AI pipeline
    logger.info("Initializing AI pipeline...")
    try:
        pipeline = AttendancePipeline()
    except Exception as e:
        logger.exception(f"FATAL: AttendancePipeline init failed: {e}")
        sys.exit(1)
    _load_embeddings_to_pipeline(pipeline)

    # Open camera using threaded stream
    logger.info(f"Opening camera source={config.CAMERA_SOURCE}...")
    try:
        cam = CameraStream(
            source=config.CAMERA_SOURCE,
            width=config.FRAME_WIDTH,
            height=config.FRAME_HEIGHT,
            fps=config.CAPTURE_FPS,
        ).start()
    except Exception as e:
        logger.exception(f"FATAL: Camera open failed (source={config.CAMERA_SOURCE}): {e}")
        sys.exit(1)

    logger.info("Camera opened. Starting AI worker thread...")

    # Start AI worker thread
    ai_thread = threading.Thread(target=_ai_worker, args=(pipeline,), daemon=True, name="ai-worker")
    ai_thread.start()

    # Graceful shutdown
    def _shutdown(sig, frame):
        logger.info("Shutting down...")
        _shutdown_event.set()
        daemon.stop()
        cam.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Recognition loop running — camera pushes frames, AI thread processes async.")

    frame_idx = 0
    while not _shutdown_event.is_set():
        frame = cam.read()
        if frame is None:
            time.sleep(0.01)
            continue

        frame_idx += 1

        # Always push raw frame immediately → smooth video at full camera FPS
        _, raw_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
        shared.update_frame_only(raw_buf.tobytes())

        # Every Nth frame: enqueue for AI processing (drop if AI still busy)
        if frame_idx % max(config.PROCESS_EVERY_N_FRAMES, 1) == 0:
            try:
                _ai_queue.put_nowait(frame.copy())
            except queue.Full:
                pass  # AI busy → skip this frame, try next cycle


if __name__ == "__main__":
    main()
