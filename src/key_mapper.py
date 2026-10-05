"""
Модуль для раскладко-независимой обработки горячих клавиш.
Поддерживает английскую (QWERTY), русскую (ЙЦУКЕН), казахскую раскладки,
а также физические аппаратные коды клавиш (macOS virtual keycodes) и коды Qt.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Optional, Tuple


class Action(Enum):
    QUIT = auto()
    CLEAR_CANVAS = auto()
    SAVE_CANVAS = auto()
    TOGGLE_DEBUG = auto()
    TOGGLE_SKELETON = auto()
    OPEN_SETTINGS = auto()
    OPEN_SHORTCUTS = auto()
    CLEAR_PINCH_DEC = auto()
    CLEAR_PINCH_INC = auto()
    THICKNESS_INC = auto()
    THICKNESS_DEC = auto()
    SELECT_COLOR = auto()  # ассоциируется с цифрой 0..9


# macOS ANSI виртуальные сканкоды (физическое расположение клавиши)
MAC_VK_MAP = {
    12: Action.QUIT,             # Q
    8: Action.CLEAR_CANVAS,      # C
    1: Action.SAVE_CANVAS,       # S
    2: Action.TOGGLE_DEBUG,      # D
    4: Action.TOGGLE_SKELETON,   # H
    31: Action.OPEN_SETTINGS,    # O
    33: Action.CLEAR_PINCH_DEC,  # [
    30: Action.CLEAR_PINCH_INC,  # ]
    24: Action.THICKNESS_INC,    # = (+)
    27: Action.THICKNESS_DEC,    # -
}

MAC_VK_DIGITS = {
    18: "1",
    19: "2",
    20: "3",
    21: "4",
    23: "5",
    22: "6",
    26: "7",
    28: "8",
    25: "9",
    29: "0",
}


def resolve_qt_key_event(event: Any) -> Tuple[Optional[Action], Optional[str]]:
    """
    Определяет логическое действие по событию PyQt6 QKeyEvent
    с учётом русской, казахской и английской раскладок.
    Возвращает (Action, param_str).
    """
    text = ""
    try:
        text = event.text().lower().strip()
    except Exception:
        pass

    key = 0
    try:
        key = event.key()
    except Exception:
        pass

    vk = None
    try:
        vk = event.nativeVirtualKey()
    except Exception:
        pass

    # 1. Цифры (выбор цвета)
    if text in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        return Action.SELECT_COLOR, text

    # Qt Key Enums для цифр
    from PyQt6.QtCore import Qt
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        digit = str(key - Qt.Key.Key_0)
        return Action.SELECT_COLOR, digit

    # macOS сканкод цифр
    if vk is not None and vk in MAC_VK_DIGITS:
        return Action.SELECT_COLOR, MAC_VK_DIGITS[vk]

    # 2. Текстовые соответствия символов (EN / RU / KK)
    # Выход: Q / q / Й / й
    if text in ("q", "й"):
        return Action.QUIT, None

    # Очистить: C / c / С / с (русская 'с')
    if text in ("c", "с"):
        return Action.CLEAR_CANVAS, None

    # Сохранить: S / s / Ы / ы
    if text in ("s", "ы"):
        return Action.SAVE_CANVAS, None

    # Отладка: D / d / В / в
    if text in ("d", "в"):
        return Action.TOGGLE_DEBUG, None

    # Скелет: H / h / Р / р
    if text in ("h", "р"):
        return Action.TOGGLE_SKELETON, None

    # Настройки: O / o / Щ / щ
    if text in ("o", "щ"):
        return Action.OPEN_SETTINGS, None

    # Справка / клавиши: ? / / / . / , / б / ю
    if text in ("?", "/", ".", ",", "б", "ю"):
        return Action.OPEN_SHORTCUTS, None

    # Порог очистки уменьшить: [ / { / х / ш
    if text in ("[", "{", "х", "ш"):
        return Action.CLEAR_PINCH_DEC, None

    # Порог очистки увеличить: ] / } / ъ / ғ
    if text in ("]", "}", "ъ", "ғ"):
        return Action.CLEAR_PINCH_INC, None

    # Толщина +: + / =
    if text in ("+", "=") or key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
        return Action.THICKNESS_INC, None

    # Толщина -: - / _
    if text in ("-", "_") or key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
        return Action.THICKNESS_DEC, None

    # 3. Qt Key Enums
    qt_key_map = {
        Qt.Key.Key_Q: Action.QUIT,
        Qt.Key.Key_C: Action.CLEAR_CANVAS,
        Qt.Key.Key_S: Action.SAVE_CANVAS,
        Qt.Key.Key_D: Action.TOGGLE_DEBUG,
        Qt.Key.Key_H: Action.TOGGLE_SKELETON,
        Qt.Key.Key_O: Action.OPEN_SETTINGS,
        Qt.Key.Key_BracketLeft: Action.CLEAR_PINCH_DEC,
        Qt.Key.Key_BracketRight: Action.CLEAR_PINCH_INC,
        Qt.Key.Key_F1: Action.OPEN_SHORTCUTS,
        Qt.Key.Key_Help: Action.OPEN_SHORTCUTS,
    }
    if key in qt_key_map:
        return qt_key_map[key], None

    # 4. macOS Hardware Scancode
    if vk is not None and vk in MAC_VK_MAP:
        return MAC_VK_MAP[vk], None

    return None, None


def resolve_cv2_key(code: int) -> Tuple[Optional[Action], Optional[str]]:
    """Для обратной совместимости с cv2.waitKey()."""
    if code < 0:
        return None, None
    char = chr(code & 0xFF).lower() if 0 <= (code & 0xFF) < 128 else ""

    if char in "0123456789":
        return Action.SELECT_COLOR, char
    if char == "q":
        return Action.QUIT, None
    if char == "c":
        return Action.CLEAR_CANVAS, None
    if char == "s":
        return Action.SAVE_CANVAS, None
    if char == "d":
        return Action.TOGGLE_DEBUG, None
    if char == "h":
        return Action.TOGGLE_SKELETON, None
    if char == "o":
        return Action.OPEN_SETTINGS, None
    if char in ("+", "="):
        return Action.THICKNESS_INC, None
    if char in ("-", "_"):
        return Action.THICKNESS_DEC, None
    if char == "[":
        return Action.CLEAR_PINCH_DEC, None
    if char == "]":
        return Action.CLEAR_PINCH_INC, None

    return None, None
