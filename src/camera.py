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

# How long release() waits for the reader thread before giving up on it
RELEASE_TIMEOUT_S = 2.0


class ThreadedCamera:
    """
    Grabs webcam frames on a background thread.

    The reader thread owns the capture device: it opens nothing itself, but it
    is the only code that reads from the device and it releases the device when
    it exits. Consumers receive each captured frame exactly once via ``read()``.
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
        self._frame_is_new = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.width = 640
        self.height = 480

        self._start_camera()

    def _start_camera(self) -> None:
        """Open the capture device and start the reader thread. Failures are logged, not raised."""
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            cap.release()
            logger.error("Could not open camera %s", self.camera_index)
            return

        try:
            if self.requested_width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
            if self.requested_height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)

            # The driver may not support the requested size — use what it actually gives us
            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.width = actual_w if actual_w > 0 else (self.requested_width or 640)
            self.height = actual_h if actual_h > 0 else (self.requested_height or 480)

            self._running = True
            self._thread = threading.Thread(target=self._loop, args=(cap,), daemon=True)
            self._thread.start()
            logger.info("Camera %s started: %dx%d, FPS limit: %d",
                        self.camera_index, self.width, self.height, self.fps_limit)
        except Exception as e:
            logger.error("Failed to start camera %s: %s", self.camera_index, e)
            self._running = False
            cap.release()

    def _loop(self, cap: cv2.VideoCapture) -> None:
        """Reader thread: capture frames into the shared buffer until stopped."""
        try:
            while self._running:
                start_t = time.monotonic()
                ok, frame = cap.read()
                with self._lock:
                    if ok:
                        self._frame = frame
                        self._frame_is_new = True

                if not ok:
                    time.sleep(0.01)

                # Throttle to the FPS limit (0 means unlimited)
                if self.fps_limit > 0:
                    frame_budget = 1.0 / self.fps_limit
                    elapsed = time.monotonic() - start_t
                    if elapsed < frame_budget:
                        time.sleep(frame_budget - elapsed)
        finally:
            cap.release()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Return ``(True, frame)`` with a copy of a frame that has not been returned yet.

        Returns ``(False, None)`` when no new frame has arrived since the last call,
        so the same frame is never processed twice.
        """
        with self._lock:
            if not self._frame_is_new or self._frame is None:
                return False, None
            self._frame_is_new = False
            return True, self._frame.copy()

    def is_opened(self) -> bool:
        """True while the device is open and the reader thread is running."""
        return self._running

    def update_settings(
        self,
        camera_index: int,
        width: Optional[int],
        height: Optional[int],
        fps_limit: int,
    ) -> None:
        """Apply new settings, reopening the device only when necessary."""
        need_reopen = (
            not self.is_opened()
            or camera_index != self.camera_index
            or width != self.requested_width
            or height != self.requested_height
        )
        self.fps_limit = fps_limit
        if need_reopen:
            self.release()
            self.camera_index = camera_index
            self.requested_width = width
            self.requested_height = height
            self._start_camera()

    def release(self) -> None:
        """
        Stop the reader thread. The thread releases the device when it exits, so the
        device is never touched from two threads at once.
        """
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=RELEASE_TIMEOUT_S)
            if self._thread.is_alive():
                logger.warning("Camera thread is still busy; the device will be released when it returns")
        self._thread = None
        with self._lock:
            self._frame = None
            self._frame_is_new = False
