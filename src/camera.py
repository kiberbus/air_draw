"""
Background webcam capture with an optional FPS limit and runtime
resolution changes.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("air_draw.camera")


class ThreadedCamera:
    """
    Grabs webcam frames on a background thread.

    Reading from the camera in a separate thread keeps blocking I/O away from
    the UI and MediaPipe processing; consumers always get the latest frame.
    """

    def __init__(
        self,
        camera_index: int = 0,
        width: Optional[int] = 960,
        height: Optional[int] = 540,
        fps_limit: int = 30,
    ) -> None:
        self.camera_index = camera_index
        self.requested_width = width
        self.requested_height = height
        self.fps_limit = fps_limit

        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._ok = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.cap: Optional[cv2.VideoCapture] = None
        self.width = 640
        self.height = 480

        self._start_camera()

    def _start_camera(self) -> None:
        """Open the capture device and start the reader thread."""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning(f"Could not open camera {self.camera_index}, falling back to camera 0")
                self.cap = cv2.VideoCapture(0)

            if self.requested_width:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
            if self.requested_height:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)

            # The driver may not support the requested size — use what it actually gives us
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.width = actual_w if actual_w > 0 else (self.requested_width or 640)
            self.height = actual_h if actual_h > 0 else (self.requested_height or 480)

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            logger.info(f"Camera started: {self.width}x{self.height}, FPS limit: {self.fps_limit}")
        except Exception as e:
            logger.error(f"Failed to start camera: {e}")

    def _loop(self) -> None:
        """Reader thread: continuously grab frames into the shared buffer."""
        while self._running:
            start_t = time.time()
            if self.cap is not None and self.cap.isOpened():
                ok, frame = self.cap.read()
                with self._lock:
                    self._ok = ok
                    self._frame = frame if ok else None
                if not ok:
                    time.sleep(0.01)
            else:
                time.sleep(0.05)

            # Throttle to the FPS limit (0 means unlimited)
            if self.fps_limit > 0:
                frame_budget = 1.0 / self.fps_limit
                elapsed = time.time() - start_t
                if elapsed < frame_budget:
                    time.sleep(frame_budget - elapsed)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Return ``(ok, frame)`` with a copy of the most recent frame."""
        with self._lock:
            if self._frame is None:
                return False, None
            return self._ok, self._frame.copy()

    def is_opened(self) -> bool:
        return bool(self.cap and self.cap.isOpened())

    def update_settings(
        self,
        camera_index: int,
        width: Optional[int],
        height: Optional[int],
        fps_limit: int,
    ) -> None:
        """Apply new settings, reopening the device only when necessary."""
        need_reopen = (camera_index != self.camera_index) or (width != self.requested_width) or (height != self.requested_height)
        self.fps_limit = fps_limit
        if need_reopen:
            self.release()
            self.camera_index = camera_index
            self.requested_width = width
            self.requested_height = height
            self._start_camera()

    def release(self) -> None:
        """Stop the reader thread and release the capture device."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
            self.cap = None
