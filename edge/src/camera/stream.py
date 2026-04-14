"""
Threaded camera stream. Keeps one-frame buffer always fresh.
Decouples capture from processing so the pipeline never blocks on camera I/O.

Camera opening strategy (tried in order):
  1. Default backend with integer index  ← simplest, works on Pi with FFMPEG
  2. V4L2 backend with integer index
  3. Default backend with device path string
  Retries up to max_retries times with retry_delay seconds between attempts,
  to handle the case where the OS needs time to release the device after reboot.
"""
import cv2
import threading
import logging
import time
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


def _dev_index(source: str) -> Optional[int]:
    """'0' or '/dev/video0' → 0, else None."""
    s = str(source).strip()
    if s.isdigit():
        return int(s)
    if s.startswith("/dev/video"):
        try:
            return int(s.replace("/dev/video", ""))
        except ValueError:
            pass
    return None


def _try_open(source_arg, backend=None) -> Optional[cv2.VideoCapture]:
    """Single open attempt; returns opened VideoCapture or None."""
    try:
        cap = (cv2.VideoCapture(source_arg, backend)
               if backend is not None
               else cv2.VideoCapture(source_arg))
        if cap.isOpened():
            ret, _ = cap.read()   # confirm we can actually pull a frame
            if ret:
                return cap
        cap.release()
    except Exception:
        pass
    return None


def _open_camera(source, width: int, height: int, fps: int,
                 max_retries: int = 20, retry_delay: float = 3.0) -> cv2.VideoCapture:
    """Open camera with retry; returns VideoCapture or raises RuntimeError."""
    idx = _dev_index(str(source))
    is_local = idx is not None

    for attempt in range(1, max_retries + 1):
        if is_local:
            # 1 — default backend (FFMPEG on Pi ARM image)
            cap = _try_open(idx)
            if cap:
                logger.info("Camera opened: default backend index=%d (attempt %d)", idx, attempt)
                return cap
            # 2 — explicit V4L2
            cap = _try_open(idx, cv2.CAP_V4L2)
            if cap:
                logger.info("Camera opened: CAP_V4L2 index=%d (attempt %d)", idx, attempt)
                return cap
            # 3 — path string
            cap = _try_open(f"/dev/video{idx}")
            if cap:
                logger.info("Camera opened: path /dev/video%d (attempt %d)", idx, attempt)
                return cap
        else:
            cap = _try_open(str(source))
            if cap:
                logger.info("Camera opened: source=%r (attempt %d)", source, attempt)
                return cap

        logger.warning("Camera not ready (attempt %d/%d, source=%r) — retry in %.0fs …",
                       attempt, max_retries, source, retry_delay)
        time.sleep(retry_delay)

    raise RuntimeError(f"Cannot open camera source {source!r} after {max_retries} attempts")


class CameraStream:
    """Background thread that continuously reads frames; call read() for latest."""

    def __init__(self, source, width: int = 1280, height: int = 720, fps: int = 10):
        self._cap = _open_camera(source, width, height, fps)
        # Best-effort props (GStreamer pipeline may override via caps)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0

    def start(self) -> "CameraStream":
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="CameraStream")
        self._thread.start()
        logger.info("CameraStream started (source=%s)", self._cap)
        return self

    def _loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Frame read failed, retrying in 0.1 s")
                time.sleep(0.1)
                continue
            with self._lock:
                self._frame = frame
                self._frame_count += 1

    def read(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def is_opened(self) -> bool:
        return self._cap.isOpened()

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._cap.release()
        logger.info("CameraStream stopped.")

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
