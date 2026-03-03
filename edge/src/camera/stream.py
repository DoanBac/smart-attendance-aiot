"""
Threaded camera stream. Keeps one-frame buffer always fresh.
Decouples capture from processing so the pipeline never blocks on camera I/O.
"""
import cv2
import threading
import logging
import time
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


class CameraStream:
    """Background thread that continuously reads frames; call read() for latest."""

    def __init__(self, source, width: int = 1280, height: int = 720, fps: int = 10):
        src = int(source) if str(source).isdigit() else source
        self._cap = cv2.VideoCapture(src)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera source: {source}")
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
