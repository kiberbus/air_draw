"""
Модуль распознавания жестов руки с помощью MediaPipe Hands:
- Пинч большой + указательный палец -> рисование
- Пинч большой + средний палец      -> очистка холста
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

# Индексы landmark'ов MediaPipe Hands
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
    gesture: Gesture
    point: Tuple[int, int]
    draw_dist: float
    clear_dist: float
    draw_threshold: float
    clear_threshold: float


def landmark_to_px(landmark, width: int, height: int) -> Tuple[int, int]:
    """Переводит нормализованные координаты landmark (0..1) в пиксели."""
    return int(landmark.x * width), int(landmark.y * height)


def hand_scale(landmarks, width: int, height: int) -> float:
    """
    Расстояние wrist -> middle_finger_mcp используется как 'масштаб руки':
    порог пинча остаётся адекватным независимо от расстояния до камеры.
    """
    wx, wy = landmark_to_px(landmarks[WRIST], width, height)
    mx, my = landmark_to_px(landmarks[MIDDLE_MCP], width, height)
    return max(math.hypot(wx - mx, wy - my), 1.0)


def smooth_point(buffer: deque, point: Tuple[int, int]) -> Tuple[int, int]:
    """Сглаживает координаты точки скользящим средним."""
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
    Определяет текущий жест:
    - draw_dist < draw_threshold -> DRAW
    - clear_dist < clear_threshold -> CLEAR (приоритет над DRAW)
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
