"""
Shared state between the AI recognition loop and the Flask web server.
Thread-safe via Lock.
"""
import threading
import time
from collections import deque


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.last_result: dict | None = None        # last recognized info
        self.last_recognized_at: float = 0.0       # epoch seconds
        self.faces_detected: int = 0
        self.liveness_passed: bool = False
        self.best_sim: float = 0.0                  # debug: highest cosine sim this frame
        self.best_name: str | None = None           # debug: closest candidate name
        self.cloud_online: bool = False             # reflects last SyncDaemon check
        # Feature flags — toggled from /settings endpoint
        self.auto_attendance: bool = True           # False = manual confirm required
        self.require_pose: bool = False             # True = reject angled faces
        self.pose_rejected: bool = False            # True = last frame rejected by pose check
        # When auto_attendance=False: pending student waiting for manual confirm
        self.pending_mark: dict | None = None       # {student_id, name, confidence, liveness_score, ts}
        self.pending_mark_ts: float = 0.0           # epoch — for expiry (10s)
        self.instruction: str = ""                  # Real-time feedback for liveness
        # Recent attendance log — last 20 unique recognitions (in-memory, survives restart via SQLite)
        self._recent: deque = deque(maxlen=20)

    def update(self, jpeg_bytes: bytes, result: dict):
        with self._lock:
            self.latest_jpeg = jpeg_bytes
            self.faces_detected = result.get("faces_detected", 0)
            self.liveness_passed = result.get("liveness_passed", False)
            self.best_sim = result.get("best_sim", 0.0)
            self.best_name = result.get("best_name", None)
            if result.get("recognized"):
                self.last_result = result["recognized"]
                self.last_recognized_at = time.time()
                # Append to recent log (deduplicate by student_id within 30s)
                rec = result["recognized"]
                now = time.time()
                last_seen = next(
                    (e["_ts"] for e in self._recent if e.get("student_id") == rec.get("student_id")), 0
                )
                if now - last_seen >= 10:   # same cooldown as COOLDOWN_SEC in main.py
                    self._recent.appendleft({
                        **rec,
                        "_ts": now,
                        "time_str": time.strftime("%H:%M:%S"),
                    })
            self.instruction = result.get("instruction", "")

    def set_cloud_online(self, online: bool):
        """Called by SyncDaemon each cycle to expose cloud connectivity to the kiosk UI."""
        with self._lock:
            self.cloud_online = online

    def update_frame_only(self, jpeg_bytes: bytes):
        """Update only the JPEG; leave AI result state unchanged (called from camera loop)."""
        with self._lock:
            self.latest_jpeg = jpeg_bytes

    def get_jpeg(self) -> bytes | None:
        with self._lock:
            return self.latest_jpeg

    def get_recent(self) -> list:
        with self._lock:
            return [
                {k: v for k, v in e.items() if not k.startswith("_")}
                for e in self._recent
            ]

    def get_status(self) -> dict:
        with self._lock:
            elapsed = time.time() - self.last_recognized_at if self.last_result else None
            # Expire pending_mark after 10s of no recognition
            pm = self.pending_mark
            if pm and time.time() - self.pending_mark_ts > 10:
                pm = None
                self.pending_mark = None
            return {
                "faces_detected": self.faces_detected,
                "liveness_passed": self.liveness_passed,
                "last_recognized": self.last_result,
                "seconds_ago": round(elapsed, 1) if elapsed is not None else None,
                "recent": elapsed is not None and elapsed < 5,
                "cloud_online": self.cloud_online,
                "auto_attendance": self.auto_attendance,
                "require_pose": self.require_pose,
                "pose_rejected": self.pose_rejected,
                "pending_mark": pm,
                "instruction": self.instruction,
                "debug_best_sim": round(self.best_sim, 4),
                "debug_best_name": self.best_name,
            }

    def set_settings(self, auto_attendance: bool | None = None, require_pose: bool | None = None):
        with self._lock:
            if auto_attendance is not None:
                self.auto_attendance = auto_attendance
            if require_pose is not None:
                self.require_pose = require_pose

    def set_pending_mark(self, info: dict | None):
        """AI thread calls this when auto=OFF and a face is recognized."""
        with self._lock:
            self.pending_mark = info
            self.pending_mark_ts = time.time() if info else 0.0

    def consume_pending_mark(self) -> dict | None:
        """Flask /mark endpoint reads pending student and clears it."""
        with self._lock:
            pm = self.pending_mark
            self.pending_mark = None
            return pm


# Singleton — imported by both main.py and stream.py
shared = SharedState()
