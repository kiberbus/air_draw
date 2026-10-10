"""
Hand gesture recognition on top of MediaPipe Hands landmarks:

- thumb + index finger pinch  -> draw
- thumb + middle finger pinch -> clear the canvas
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

# MediaPipe Hands landmark indices
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
WRIST = 0
MIDDLE_MCP = 9

# A pinch starts when the fingers come closer than the threshold, and ends only
# after they move this many times further apart. The gap stops a stroke from
# flickering when the distance hovers around the threshold.
PINCH_RELEASE_FACTOR = 1.25


class Gesture(Enum):
    IDLE = auto()
    DRAW = auto()
    CLEAR = auto()


@dataclass
class GestureInfo:
    """Result of gesture classification for a single frame."""

    gesture: Gesture
    point: Tuple[int, int]      # Index fingertip position in pixels (the brush tip)
    draw_dist: float            # Thumb-to-index distance in pixels
    clear_dist: float           # Thumb-to-middle distance in pixels
    draw_threshold: float       # Pinch threshold for DRAW in pixels (after hysteresis)
    clear_threshold: float      # Pinch threshold for CLEAR in pixels (after hysteresis)


def landmark_to_px(landmark, width: int, height: int) -> Tuple[int, int]:
    """Convert a normalized landmark (0..1) to pixel coordinates."""
    return int(landmark.x * width), int(landmark.y * height)


def hand_scale(landmarks, width: int, height: int) -> float:
    """
    Return the wrist -> middle finger MCP distance as the "hand size".

    Pinch thresholds are expressed relative to this value, so gestures work
    the same regardless of how far the hand is from the camera.
    """
    wx, wy = landmark_to_px(landmarks[WRIST], width, height)
    mx, my = landmark_to_px(landmarks[MIDDLE_MCP], width, height)
    return max(math.hypot(wx - mx, wy - my), 1.0)


class OneEuroFilter:
    """
    1€ filter (Casiez, Roussel, Vogel, 2012) for a single scalar signal.

    While the signal is still it is smoothed heavily (less jitter); when it moves
    fast the cutoff rises, so the output keeps up with the hand (less lag).
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.03, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: Optional[float] = None
        self._dx = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self) -> None:
        self._x = None
        self._dx = 0.0

    def __call__(self, x: float, dt: float) -> float:
        """Filter one sample taken ``dt`` seconds after the previous one."""
        if self._x is None:
            self._x = x
            return x
        dt = max(dt, 1e-6)

        # Estimate the speed, smooth it, and use it to pick the cutoff
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1.0 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)

        a = self._alpha(cutoff, dt)
        self._x = a * x + (1.0 - a) * self._x
        return self._x


class PointSmoother:
    """One Euro filter applied to both coordinates of a pixel point."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.03) -> None:
        self._fx = OneEuroFilter(min_cutoff, beta)
        self._fy = OneEuroFilter(min_cutoff, beta)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()

    def update(self, point: Tuple[int, int], dt: float) -> Tuple[int, int]:
        return int(round(self._fx(point[0], dt))), int(round(self._fy(point[1], dt)))


def classify_gesture(
    landmarks,
    width: int,
    height: int,
    draw_ratio: float = 0.17,
    clear_ratio: float = 0.17,
    previous: Gesture = Gesture.IDLE,
) -> GestureInfo:
    """
    Classify the current hand pose:

    - ``clear_dist < clear_threshold`` -> CLEAR (takes priority over DRAW)
    - ``draw_dist < draw_threshold``   -> DRAW
    - otherwise                        -> IDLE

    Thresholds are ``hand_scale * ratio``. While a pinch is already held
    (``previous``), its threshold is relaxed by ``PINCH_RELEASE_FACTOR``.
    """
    scale = hand_scale(landmarks, width, height)
    draw_threshold = scale * draw_ratio
    clear_threshold = scale * clear_ratio
    if previous is Gesture.DRAW:
        draw_threshold *= PINCH_RELEASE_FACTOR
    elif previous is Gesture.CLEAR:
        clear_threshold *= PINCH_RELEASE_FACTOR

    tx, ty = landmark_to_px(landmarks[THUMB_TIP], width, height)
    ix, iy = landmark_to_px(landmarks[INDEX_TIP], width, height)
    mx, my = landmark_to_px(landmarks[MIDDLE_TIP], width, height)

    draw_dist = math.hypot(tx - ix, ty - iy)
    clear_dist = math.hypot(tx - mx, ty - my)

    if clear_dist < clear_threshold:
        gesture = Gesture.CLEAR
    elif draw_dist < draw_threshold:
        gesture = Gesture.DRAW
    else:
        gesture = Gesture.IDLE

    return GestureInfo(
        gesture=gesture,
        point=(ix, iy),
        draw_dist=draw_dist,
        clear_dist=clear_dist,
        draw_threshold=draw_threshold,
        clear_threshold=clear_threshold,
    )
