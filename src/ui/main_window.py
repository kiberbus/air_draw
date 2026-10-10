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
from ..config import PALETTE_KEYS, AppConfig, clamp_setting, get_data_dir, save_config, tr
from ..gestures import Gesture, GestureInfo, PointSmoother, classify_gesture
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

        self.output_dir = get_data_dir() / "air_draw_captures"
        self.output_dir.mkdir(exist_ok=True)

        # Camera
        self.camera = ThreadedCamera(
            camera_index=self.config.camera_index,
            width=self.config.width,
            height=self.config.height,
            fps_limit=self.config.fps_limit,
        )

        # Canvas: color strokes plus a mask of painted pixels used for compositing
        self._reset_canvas(self.camera.width, self.camera.height)

        # Fingertip smoothing, the previous stroke point and the last gesture (for pinch hysteresis)
        self.smoother = self._make_smoother()
        self.prev_point: Optional[Tuple[int, int]] = None
        self.gesture = Gesture.IDLE

        # MediaPipe
        self._init_mediapipe()

        # FPS measurement, based on new camera frames
        self._frame_times: deque = deque(maxlen=30)
        self._last_frame_time = time.monotonic()
        self.current_fps = 0.0

        # UI
        self.palette_buttons: Dict[str, QPushButton] = {}
        self._init_ui()
        self._report_camera_state()

        # Frame timer: polls the camera and renders at the configured FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame_tick)
        self.timer.start(self._frame_interval_ms())

    # ----------------- Setup ----------------- #

    def _make_smoother(self) -> PointSmoother:
        return PointSmoother(self.config.smoothing_min_cutoff, self.config.smoothing_beta)

    def _frame_interval_ms(self) -> int:
        return max(1, int(1000 / self.config.fps_limit)) if self.config.fps_limit > 0 else 16

    def _reset_canvas(self, width: int, height: int) -> None:
        self.frame_width = width
        self.frame_height = height
        self.canvas = np.zeros((height, width, 3), dtype=np.uint8)
        self.canvas_mask = np.zeros((height, width), dtype=np.uint8)
        self.prev_point = None

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
        self.video_label.setWordWrap(True)
        self.video_label.setStyleSheet("background-color: #1a1a1a; color: #dddddd; border-radius: 4px;")
        main_layout.addWidget(self.video_label, stretch=1)

        # 3. Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_proc_label = QLabel()
        self.status_load_label = QLabel()
        self.status_fps_label = QLabel()
        self.status_gesture_label = QLabel()
        self.status_color_label = QLabel()

        self.status_bar.addWidget(self.status_proc_label, 2)
        self.status_bar.addWidget(self.status_load_label, 1)
        self.status_bar.addWidget(self.status_fps_label, 1)
        self.status_bar.addWidget(self.status_gesture_label, 1)
        self.status_bar.addWidget(self.status_color_label, 1)

        self._update_status_bar(None)

    def _build_palette_buttons(self) -> None:
        """Create the palette buttons once; their colors are refreshed by ``_refresh_palette_buttons``."""
        for d in PALETTE_KEYS:
            btn = QPushButton(d)
            btn.setFixedSize(30, 30)
            btn.clicked.connect(lambda _, key=d: self._select_color(key))
            self.toolbar_palette_layout.addWidget(btn)
            self.palette_buttons[d] = btn
        self._refresh_palette_buttons()

    def _refresh_palette_buttons(self) -> None:
        """Show each button in its palette color, highlighting the active one."""
        for d, btn in self.palette_buttons.items():
            bgr = self.config.palette.get(d, [0, 255, 0])
            r, g, b = bgr[2], bgr[1], bgr[0]  # BGR -> RGB for CSS
            is_active = d == self.config.current_color_key
            border = "2px solid white" if is_active else "1px solid #555"
            btn.setStyleSheet(
                f"background-color: rgb({r}, {g}, {b}); color: {'#000' if (r + g + b) > 400 else '#fff'}; "
                f"font-weight: bold; border: {border}; border-radius: 4px;"
            )

    def _select_color(self, key: str) -> None:
        self.config.current_color_key = key
        self._refresh_palette_buttons()
        self._update_status_bar(None)

    def _set_thickness(self, value: int) -> None:
        self.config.thickness = clamp_setting("thickness", value)
        self.lbl_thickness.setText(tr("thickness_label", self.lang, val=self.config.thickness))

    def _increase_thickness(self) -> None:
        self._set_thickness(self.config.thickness + 1)

    def _decrease_thickness(self) -> None:
        self._set_thickness(self.config.thickness - 1)

    def _nudge_clear_pinch(self, delta: int) -> None:
        self.config.clear_pinch_ratio = clamp_setting("clear_pinch_ratio", self.config.clear_pinch_ratio + delta)
        logger.info("Clear threshold: %d", self.config.clear_pinch_ratio)

    def _clear_canvas(self) -> None:
        self.canvas[:] = 0
        self.canvas_mask[:] = 0
        self.prev_point = None
        self.status_bar.showMessage(tr("status_cleared", self.lang), 3000)

    def _next_capture_path(self) -> Path:
        """A new file name per save, with millisecond precision so quick saves never overwrite each other."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = self.output_dir / f"drawing_{stamp}.png"
        n = 1
        while path.exists():
            path = self.output_dir / f"drawing_{stamp}_{n}.png"
            n += 1
        return path

    def _save_canvas(self) -> None:
        """Save the strokes as a PNG with a transparent background (alpha = stroke mask)."""
        filename = self._next_capture_path()
        rgba = np.concatenate([self.canvas, self.canvas_mask[:, :, None]], axis=2)
        if cv2.imwrite(str(filename), rgba):
            self.status_bar.showMessage(tr("status_saved", self.lang, filename=filename.name), 4000)
            logger.info("Canvas saved: %s", filename)
        else:
            self.status_bar.showMessage(tr("status_save_failed", self.lang, filename=filename.name), 6000)
            logger.error("Could not write %s", filename)

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

        # Camera (reopened only if index/resolution changed or it is not running)
        self.camera.update_settings(
            camera_index=self.config.camera_index,
            width=self.config.width,
            height=self.config.height,
            fps_limit=self.config.fps_limit,
        )
        if (self.camera.width != self.frame_width) or (self.camera.height != self.frame_height):
            self._reset_canvas(self.camera.width, self.camera.height)

        # Frame timer interval
        self.timer.setInterval(self._frame_interval_ms())

        # Recreate MediaPipe Hands and the smoother with the new parameters
        self.hands.close()
        self._init_mediapipe()
        self.smoother = self._make_smoother()
        self.gesture = Gesture.IDLE

        self._refresh_palette_buttons()
        self._report_camera_state()
        self._update_status_bar(None)

    def _report_camera_state(self) -> None:
        """Tell the user when no camera is running, instead of showing an empty window."""
        if self.camera.is_opened():
            self.video_label.setText("")
            return
        message = tr("camera_error", self.lang, index=self.camera.camera_index)
        self.video_label.setText(message)
        self.status_bar.showMessage(message)

    # ----------------- Frame processing ----------------- #

    def _on_frame_tick(self) -> None:
        """Process and display one new camera frame."""
        ok, frame = self.camera.read()
        if not ok or frame is None:
            # No new frame yet: the camera is still starting or this tick repeats the last one
            return

        now = time.monotonic()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        self._frame_times.append(dt)
        avg_dt = sum(self._frame_times) / len(self._frame_times)
        self.current_fps = 1.0 / avg_dt if avg_dt > 0 else 0.0

        # Mirror the image so movements feel natural
        frame = cv2.flip(frame, 1)

        # Keep the canvas the same size as the frame
        fh, fw = frame.shape[:2]
        if fw != self.frame_width or fh != self.frame_height:
            self._reset_canvas(fw, fh)

        # Hand tracking and gesture-driven drawing
        info = self._process_hand(frame, dt)

        # Fingertip marker, gesture label and debug info
        self._render_overlay(frame, info)

        # Overlay the canvas on top of the frame
        composite = self._composite(frame)

        # Show the result in the QLabel
        self._display_frame(composite)

        # Refresh the status bar
        self._update_status_bar(info)

    def _process_hand(self, frame: np.ndarray, dt: float) -> Optional[GestureInfo]:
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
            # Hand lost: end the stroke and forget old positions so the next
            # appearance does not start from a stale, averaged point
            self.prev_point = None
            self.smoother.reset()
            self.gesture = Gesture.IDLE
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
            self.frame_width,
            self.frame_height,
            draw_ratio=self.config.draw_pinch_float,
            clear_ratio=self.config.clear_pinch_float,
            previous=self.gesture,
        )
        self.gesture = info.gesture
        point = self.smoother.update(info.point, dt)
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
            frame, label, (12, self.frame_height - 20),
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
                    frame, text, (12, self.frame_height - 55 - 24 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA,
                )

    def _composite(self, frame: np.ndarray) -> np.ndarray:
        """Put canvas strokes over the frame wherever the mask is set."""
        mask_inv = cv2.bitwise_not(self.canvas_mask)
        background = cv2.bitwise_and(frame, frame, mask=mask_inv)
        foreground = cv2.bitwise_and(self.canvas, self.canvas, mask=self.canvas_mask)
        return cv2.add(background, foreground)

    def _display_frame(self, frame: np.ndarray) -> None:
        target = self.video_label.size()
        if target.width() <= 0 or target.height() <= 0:
            return  # The label has not been laid out yet

        # Scale to the label size, keeping the aspect ratio. OpenCV is much
        # cheaper than scaling a QPixmap with smooth filtering on every frame.
        h, w = frame.shape[:2]
        scale = min(target.width() / w, target.height() / h)
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        if (new_w, new_h) != (w, h):
            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            frame = cv2.resize(frame, (new_w, new_h), interpolation=interpolation)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        # fromImage copies the pixels, so the numpy buffer may be reused afterwards
        self.video_label.setPixmap(QPixmap.fromImage(q_img))

    def _update_status_bar(self, info: Optional[GestureInfo]) -> None:
        # CPU
        cpu_load = self.proc_info.get_cpu_load()
        self.status_proc_label.setText(
            tr("bar_proc", self.lang, brand=self.proc_info.brand, cores=self.proc_info.logical_cores)
        )
        self.status_load_label.setText(
            tr("bar_load", self.lang, load=f"{cpu_load:.0f}") if cpu_load is not None else ""
        )

        # FPS
        target = f"/{self.config.fps_limit}" if self.config.fps_limit > 0 else ""
        self.status_fps_label.setText(tr("bar_fps", self.lang, fps=f"{self.current_fps:.0f}", target=target))

        # Gesture
        gesture_name = tr("status_idle", self.lang)
        if info:
            if info.gesture is Gesture.DRAW:
                gesture_name = tr("status_draw", self.lang)
            elif info.gesture is Gesture.CLEAR:
                gesture_name = tr("status_clear", self.lang)
        self.status_gesture_label.setText(tr("gesture_label", self.lang, name=gesture_name))

        # Active color
        self.status_color_label.setText(tr("current_color_label", self.lang, key=self.config.current_color_key))

    # ----------------- Keyboard handling ----------------- #

    def keyPressEvent(self, event: QKeyEvent) -> None:
        action, param = resolve_qt_key_event(event)
        if action is None:
            super().keyPressEvent(event)
            return

        # Toggles are kept in memory and written to config.json when the window closes
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
        elif action is Action.TOGGLE_SKELETON:
            self.config.show_skeleton = not self.config.show_skeleton
        elif action is Action.CLEAR_PINCH_DEC:
            self._nudge_clear_pinch(-1)
        elif action is Action.CLEAR_PINCH_INC:
            self._nudge_clear_pinch(+1)
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
