"""
Модуль фонового захвата видео с веб-камеры с поддержкой ограничения FPS
и изменения разрешения.
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
    Фоновый захват кадров с веб-камеры.
    Параллельный поток предотвращает задержки основного интерфейса и MediaPipe.
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
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning(f"Не удалось открыть камеру {self.camera_index}, пробуем камеру 0")
                self.cap = cv2.VideoCapture(0)

            if self.requested_width:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
            if self.requested_height:
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)

            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.width = actual_w if actual_w > 0 else (self.requested_width or 640)
            self.height = actual_h if actual_h > 0 else (self.requested_height or 480)

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            logger.info(f"Камера запущена: {self.width}x{self.height}, лимит FPS: {self.fps_limit}")
        except Exception as e:
            logger.error(f"Ошибка запуска камеры: {e}")

    def _loop(self) -> None:
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

            # Ограничение FPS при необходимости
            if self.fps_limit > 0:
                frame_budget = 1.0 / self.fps_limit
                elapsed = time.time() - start_t
                if elapsed < frame_budget:
                    time.sleep(frame_budget - elapsed)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
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
        need_reopen = (camera_index != self.camera_index) or (width != self.requested_width) or (height != self.requested_height)
        self.fps_limit = fps_limit
        if need_reopen:
            self.release()
            self.camera_index = camera_index
            self.requested_width = width
            self.requested_height = height
            self._start_camera()

    def release(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
            self.cap = None
