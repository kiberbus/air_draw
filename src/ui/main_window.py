"""
Air Draw main window (PyQt6).

Shows the mirrored camera feed with the drawing canvas on top, the toolbar,
the status bar, and handles layout-independent hotkeys.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..camera import ThreadedCamera
from ..config import AppConfig, save_config, tr
from ..gestures import (
    Gesture,
    GestureInfo,
    classify_gesture,
    smooth_point,
)
from ..key_mapper import Action, resolve_qt_key_event
from ..processor_info import detect_processor
from .settings_dialog import SettingsDialog
from .shortcuts_dialog import ShortcutsDialog

logger = logging.getLogger("air_draw.main_window")


class MainWindow(QMainWindow):
    """
    Main application window.

    A ``QTimer`` drives the pipeline: grab frame -> detect hand -> classify
    gesture -> draw on canvas -> composite over the frame -> display.
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.lang = config.language
        self.proc_info = detect_processor()

        self.output_dir = Path("air_draw_captures")
        self.output_dir.mkdir(exist_ok=True)

        # Camera
        self.camera = ThreadedCamera(
            camera_index=self.config.camera_index,
            width=self.config.width,
            height=self.config.height,
            fps_limit=self.config.fps_limit,
        )

        # Canvas: color strokes plus a mask of painted pixels used for compositing
        self.width = self.camera.width
        self.height = self.camera.height
        self.canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self.canvas_mask = np.zeros((self.height, self.width), dtype=np.uint8)

        # Fingertip smoothing and the previous stroke point
        self.smoothing_buffer: deque = deque(maxlen=self.config.smoothing_window)
        self.prev_point: Optional[Tuple[int, int]] = None

        # MediaPipe
        self._init_mediapipe()

        # FPS measurement
        self._frame_times: deque = deque(maxlen=30)
        self._last_frame_time = time.time()
        self.current_fps = 0.0

        # UI
        self.palette_buttons: Dict[str, QPushButton] = {}
        self._init_ui()

        # Frame timer: polls the camera and renders at the configured FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame_tick)
        interval_ms = int(1000 / self.config.fps_limit) if self.config.fps_limit > 0 else 16
        self.timer.start(max(1, interval_ms))

    def _init_mediapipe(self) -> None:
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,
            model_complexity=self.config.model_complexity,
            min_detection_confidence=self.config.detection_confidence,
            min_tracking_confidence=self.config.tracking_confidence,
        )

    def _init_ui(self) -> None:
        self.setWindowTitle(tr("app_title", self.lang))
        self.setMinimumSize(800, 600)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top toolbar
        toolbar = QHBoxLayout()

        # Palette buttons 1..9, 0
        self.toolbar_palette_layout = QHBoxLayout()
        self._build_palette_buttons()
        toolbar.addLayout(self.toolbar_palette_layout)

        toolbar.addSpacing(15)

        # Brush thickness
        self.btn_thick_minus = QPushButton("–")
        self.btn_thick_minus.setFixedSize(30, 30)
        self.btn_thick_minus.clicked.connect(self._decrease_thickness)
        toolbar.addWidget(self.btn_thick_minus)

        self.lbl_thickness = QLabel(tr("thickness_label", self.lang, val=self.config.thickness))
        toolbar.addWidget(self.lbl_thickness)

        self.btn_thick_plus = QPushButton("+")
        self.btn_thick_plus.setFixedSize(30, 30)
        self.btn_thick_plus.clicked.connect(self._increase_thickness)
        toolbar.addWidget(self.btn_thick_plus)

        toolbar.addStretch()

        # Clear
        self.btn_clear = QPushButton(tr("btn_clear_canvas", self.lang))
        self.btn_clear.clicked.connect(self._clear_canvas)
        toolbar.addWidget(self.btn_clear)

        # Save
        self.btn_save = QPushButton(tr("btn_save_canvas", self.lang))
        self.btn_save.clicked.connect(self._save_canvas)
        toolbar.addWidget(self.btn_save)

        # Settings
        self.btn_settings = QPushButton(tr("btn_open_settings", self.lang))
        self.btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(self.btn_settings)

        # Shortcuts help
        self.btn_shortcuts = QPushButton(tr("btn_open_shortcuts", self.lang))
        self.btn_shortcuts.clicked.connect(self._open_shortcuts)
        toolbar.addWidget(self.btn_shortcuts)

        main_layout.addLayout(toolbar)

        # 2. Video display
        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        main_layout.addWidget(self.video_label, stretch=1)

        # 3. Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_proc_label = QLabel()
        self.status_fps_label = QLabel()
        self.status_gesture_label = QLabel()
        self.status_color_label = QLabel()

        self.status_bar.addWidget(self.status_proc_label, 2)
        self.status_bar.addWidget(self.status_fps_label, 1)
        self.status_bar.addWidget(self.status_gesture_label, 1)
        self.status_bar.addWidget(self.status_color_label, 1)

        self._update_status_bar(None)

    def _build_palette_buttons(self) -> None:
        """(Re)create the palette buttons, highlighting the active color."""
        # Remove old buttons
        for btn in self.palette_buttons.values():
            btn.deleteLater()
        self.palette_buttons.clear()

        digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        for d in digits:
            bgr = self.config.palette.get(d, [0, 255, 0])
            r, g, b = bgr[2], bgr[1], bgr[0]  # BGR -> RGB for CSS
            btn = QPushButton(d)
            btn.setFixedSize(30, 30)
            is_active = (d == self.config.current_color_key)
            border = "2px solid white" if is_active else "1px solid #555"
            btn.setStyleSheet(
                f"background-color: rgb({r}, {g}, {b}); color: {'#000' if (r+g+b)>400 else '#fff'}; "
                f"font-weight: bold; border: {border}; border-radius: 4px;"
            )
            btn.clicked.connect(lambda _, key=d: self._select_color(key))
            self.toolbar_palette_layout.addWidget(btn)
            self.palette_buttons[d] = btn

    def _select_color(self, key: str) -> None:
        self.config.current_color_key = key
        self._build_palette_buttons()
        self._update_status_bar(None)

    def _increase_thickness(self) -> None:
        self.config.thickness = min(30, self.config.thickness + 1)
        self.lbl_thickness.setText(tr("thickness_label", self.lang, val=self.config.thickness))

    def _decrease_thickness(self) -> None:
        self.config.thickness = max(1, self.config.thickness - 1)
        self.lbl_thickness.setText(tr("thickness_label", self.lang, val=self.config.thickness))

    def _clear_canvas(self) -> None:
        self.canvas[:] = 0
        self.canvas_mask[:] = 0
        self.prev_point = None
        self.status_bar.showMessage(tr("status_cleared", self.lang), 3000)

    def _save_canvas(self) -> None:
        filename = self.output_dir / f"drawing_{datetime.now():%Y%m%d_%H%M%S}.png"
        cv2.imwrite(str(filename), self.canvas)
        self.status_bar.showMessage(tr("status_saved", self.lang, filename=filename.name), 4000)
        logger.info("Canvas saved: %s", filename)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            # Settings were saved — apply them
            self.lang = self.config.language
            self._apply_updated_config()

    def _open_shortcuts(self) -> None:
        dlg = ShortcutsDialog(self.config, self)
        dlg.exec()

    def _apply_updated_config(self) -> None:
        """Apply changed settings to the running window without restarting."""
        # Retranslate the UI
        self.setWindowTitle(tr("app_title", self.lang))
        self.btn_clear.setText(tr("btn_clear_canvas", self.lang))
        self.btn_save.setText(tr("btn_save_canvas", self.lang))
        self.btn_settings.setText(tr("btn_open_settings", self.lang))
        self.btn_shortcuts.setText(tr("btn_open_shortcuts", self.lang))
        self.lbl_thickness.setText(tr("thickness_label", self.lang, val=self.config.thickness))

        # Camera (reopened only if index/resolution changed)
        self.camera.update_settings(
            camera_index=self.config.camera_index,
            width=self.config.width,
            height=self.config.height,
            fps_limit=self.config.fps_limit,
        )
        if (self.camera.width != self.width) or (self.camera.height != self.height):
            self.width = self.camera.width
            self.height = self.camera.height
            self.canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            self.canvas_mask = np.zeros((self.height, self.width), dtype=np.uint8)

        # Frame timer interval
        interval_ms = int(1000 / self.config.fps_limit) if self.config.fps_limit > 0 else 16
        self.timer.setInterval(max(1, interval_ms))

        # Recreate MediaPipe Hands with the new model parameters
        self.hands.close()
        self._init_mediapipe()

        # Smoothing window
        self.smoothing_buffer = deque(maxlen=self.config.smoothing_window)

        # Palette buttons
        self._build_palette_buttons()
        self._update_status_bar(None)

    # ----------------- Frame processing ----------------- #

    def _on_frame_tick(self) -> None:
        """Process and display one camera frame."""
        ok, frame = self.camera.read()
        if not ok or frame is None:
            return

        now = time.time()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        self._frame_times.append(dt)
        avg_dt = sum(self._frame_times) / len(self._frame_times)
        self.current_fps = 1.0 / avg_dt if avg_dt > 0 else 0.0

        # Mirror the image so movements feel natural
        frame = cv2.flip(frame, 1)

        # Keep the canvas the same size as the frame
        fh, fw = frame.shape[:2]
        if fw != self.width or fh != self.height:
            self.width = fw
            self.height = fh
            self.canvas = cv2.resize(self.canvas, (fw, fh))
            self.canvas_mask = cv2.resize(self.canvas_mask, (fw, fh))

        # Hand tracking and gesture-driven drawing
        info = self._process_hand(frame)

        # Fingertip marker, gesture label and debug info
        self._render_overlay(frame, info)

        # Overlay the canvas on top of the frame
        composite = self._composite(frame)

        # Show the result in the QLabel
        self._display_frame(composite)

        # Refresh the status bar
        self._update_status_bar(info)

    def _process_hand(self, frame: np.ndarray) -> Optional[GestureInfo]:
        """
        Run MediaPipe on ``frame``, classify the gesture and update the canvas.

        Returns ``None`` when no hand is detected.
        """
        # Optionally downscale the detector input to save CPU. Landmarks are
        # normalized (0..1), so they still map onto the full-size frame.
        if self.config.detection_scale != 1.0:
            scale = self.config.detection_scale
            det_input = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        else:
            det_input = frame

        rgb = cv2.cvtColor(det_input, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False  # Lets MediaPipe avoid an extra copy
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.prev_point = None
            return None

        landmarks = results.multi_hand_landmarks[0].landmark

        if self.config.show_skeleton:
            self.mp_drawing.draw_landmarks(
                frame,
                results.multi_hand_landmarks[0],
                self.mp_hands.HAND_CONNECTIONS,
                self.mp_drawing_styles.get_default_hand_landmarks_style(),
                self.mp_drawing_styles.get_default_hand_connections_style(),
            )

        info = classify_gesture(
            landmarks,
            self.width,
            self.height,
            draw_ratio=self.config.draw_pinch_float,
            clear_ratio=self.config.clear_pinch_float,
        )
        point = smooth_point(self.smoothing_buffer, info.point)
        info.point = point

        active_color = self.config.get_color_bgr()

        if info.gesture is Gesture.CLEAR:
            self.canvas[:] = 0
            self.canvas_mask[:] = 0
            self.prev_point = None
        elif info.gesture is Gesture.DRAW:
            # Connect consecutive points with a line so fast strokes stay continuous
            if self.prev_point is not None:
                cv2.line(
                    self.canvas,
                    self.prev_point,
                    point,
                    active_color,
                    self.config.thickness,
                    cv2.LINE_AA,
                )
                cv2.line(
                    self.canvas_mask,
                    self.prev_point,
                    point,
                    255,
                    self.config.thickness,
                    cv2.LINE_AA,
                )
            self.prev_point = point
        else:
            # Pinch released — the next DRAW starts a new stroke
            self.prev_point = None

        return info

    def _render_overlay(self, frame: np.ndarray, info: Optional[GestureInfo]) -> None:
        gesture = info.gesture if info else Gesture.IDLE
        active_color = self.config.get_color_bgr()

        if info is not None:
            marker_color = {
                Gesture.DRAW: active_color,
                Gesture.CLEAR: (0, 0, 255),
                Gesture.IDLE: (200, 200, 200),
            }[gesture]
            cv2.circle(frame, info.point, 8, marker_color, -1, cv2.LINE_AA)

        # Gesture label
        label = {
            Gesture.DRAW: tr("status_draw", self.lang),
            Gesture.CLEAR: tr("status_clear", self.lang),
            Gesture.IDLE: tr("status_idle", self.lang),
        }[gesture]
        cv2.putText(
            frame, label, (12, self.height - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA,
        )

        # Debug overlay: current distance / threshold for each pinch
        if self.config.show_debug and info is not None:
            lines = [
                f"draw:  {info.draw_dist:5.1f} / {info.draw_threshold:5.1f} (ratio {self.config.draw_pinch_ratio})",
                f"clear: {info.clear_dist:5.1f} / {info.clear_threshold:5.1f} (ratio {self.config.clear_pinch_ratio})",
            ]
            for i, text in enumerate(lines):
                cv2.putText(
                    frame, text, (12, self.height - 55 - 24 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA,
                )

    def _composite(self, frame: np.ndarray) -> np.ndarray:
        """Put canvas strokes over the frame wherever the mask is set."""
        mask_inv = cv2.bitwise_not(self.canvas_mask)
        background = cv2.bitwise_and(frame, frame, mask=mask_inv)
        foreground = cv2.bitwise_and(self.canvas, self.canvas, mask=self.canvas_mask)
        return cv2.add(background, foreground)

    def _display_frame(self, frame: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        # Scale to the QLabel size, keeping the aspect ratio
        target_size = self.video_label.size()
        pixmap = QPixmap.fromImage(q_img).scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_label.setPixmap(pixmap)

    def _update_status_bar(self, info: Optional[GestureInfo]) -> None:
        # CPU
        cpu_load = self.proc_info.get_cpu_load()
        load_s = f" | CPU: {cpu_load:.0f}%" if cpu_load is not None else ""
        self.status_proc_label.setText(f"CPU: {self.proc_info.brand} ({self.proc_info.logical_cores} cores{load_s})")

        # FPS
        target_fps = f"/{self.config.fps_limit}" if self.config.fps_limit > 0 else ""
        self.status_fps_label.setText(f"FPS: {self.current_fps:.0f}{target_fps}")

        # Gesture
        gesture_name = tr("status_idle", self.lang)
        if info:
            if info.gesture is Gesture.DRAW:
                gesture_name = tr("status_draw", self.lang)
            elif info.gesture is Gesture.CLEAR:
                gesture_name = tr("status_clear", self.lang)
        self.status_gesture_label.setText(tr("gesture_label", self.lang, name=gesture_name))

        # Active color
        self.status_color_label.setText(
            f"{tr('current_color_label', self.lang, key=self.config.current_color_key)}"
        )

    # ----------------- Keyboard handling ----------------- #

    def keyPressEvent(self, event: QKeyEvent) -> None:
        action, param = resolve_qt_key_event(event)
        if action is None:
            super().keyPressEvent(event)
            return

        if action is Action.QUIT:
            self.close()
        elif action is Action.CLEAR_CANVAS:
            self._clear_canvas()
        elif action is Action.SAVE_CANVAS:
            self._save_canvas()
        elif action is Action.SELECT_COLOR and param:
            self._select_color(param)
        elif action is Action.THICKNESS_INC:
            self._increase_thickness()
        elif action is Action.THICKNESS_DEC:
            self._decrease_thickness()
        elif action is Action.TOGGLE_DEBUG:
            self.config.show_debug = not self.config.show_debug
            save_config(self.config)
        elif action is Action.TOGGLE_SKELETON:
            self.config.show_skeleton = not self.config.show_skeleton
            save_config(self.config)
        elif action is Action.CLEAR_PINCH_DEC:
            self.config.clear_pinch_ratio = max(5, self.config.clear_pinch_ratio - 1)
            save_config(self.config)
            logger.info("Clear threshold: %d", self.config.clear_pinch_ratio)
        elif action is Action.CLEAR_PINCH_INC:
            self.config.clear_pinch_ratio = min(50, self.config.clear_pinch_ratio + 1)
            save_config(self.config)
            logger.info("Clear threshold: %d", self.config.clear_pinch_ratio)
        elif action is Action.OPEN_SETTINGS:
            self._open_settings()
        elif action is Action.OPEN_SHORTCUTS:
            self._open_shortcuts()

    def closeEvent(self, event) -> None:
        """Release the camera and MediaPipe, then persist settings."""
        self.timer.stop()
        self.camera.release()
        self.hands.close()
        save_config(self.config)
        event.accept()
