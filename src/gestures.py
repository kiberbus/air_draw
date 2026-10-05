"""
Hand gesture recognition on top of MediaPipe Hands landmarks:

- thumb + index finger pinch  -> draw
- thumb + middle finger pinch -> clear the canvas
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

# MediaPipe Hands landmark indices
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
WRIST = 0
MIDDLE_MCP = 9


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
    draw_threshold: float       # Pinch threshold for DRAW in pixels
    clear_threshold: float      # Pinch threshold for CLEAR in pixels


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


def smooth_point(buffer: deque, point: Tuple[int, int]) -> Tuple[int, int]:
    """Smooth a point with a moving average over the buffer window."""
    buffer.append(point)
    xs, ys = zip(*buffer)
    return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))


def classify_gesture(
    landmarks,
    width: int,
    height: int,
    draw_ratio: float = 0.17,
    clear_ratio: float = 0.17,
) -> GestureInfo:
    """
    Classify the current hand pose:

    - ``clear_dist < clear_threshold`` -> CLEAR (takes priority over DRAW)
    - ``draw_dist < draw_threshold``   -> DRAW
    - otherwise                        -> IDLE

    Thresholds are ``hand_scale * ratio``.
    """
    scale = hand_scale(landmarks, width, height)
    draw_threshold = scale * draw_ratio
    clear_threshold = scale * clear_ratio

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
