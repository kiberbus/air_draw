"""
Keyboard-layout-independent hotkey handling.

A key press is resolved in several passes so shortcuts work the same on
English (QWERTY), Russian (ЙЦУКЕН) and Kazakh layouts: by typed character,
by Qt key code, and finally by the physical macOS virtual keycode.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Optional, Tuple


class Action(Enum):
    """Logical actions that a hotkey can trigger."""

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
    SELECT_COLOR = auto()  # Parameter: digit "0".."9"


# macOS ANSI virtual keycodes (physical key position, layout-independent)
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
    Map a PyQt6 ``QKeyEvent`` to a logical action, regardless of the active
    keyboard layout (English, Russian or Kazakh).

    Returns ``(action, param)``; ``param`` is the digit for ``SELECT_COLOR``
    and ``None`` otherwise. Returns ``(None, None)`` for unmapped keys.
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

    # 1. Digits (color selection)
    if text in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        return Action.SELECT_COLOR, text

    # Digits via Qt key codes
    from PyQt6.QtCore import Qt
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        digit = str(key - Qt.Key.Key_0)
        return Action.SELECT_COLOR, digit

    # Digits via macOS keycodes
    if vk is not None and vk in MAC_VK_DIGITS:
        return Action.SELECT_COLOR, MAC_VK_DIGITS[vk]

    # 2. Match by typed character (EN / RU / KK).
    # Each action lists the Latin letter and the Cyrillic letter on the same key.
    # Quit: Q / Й
    if text in ("q", "й"):
        return Action.QUIT, None

    # Clear: C / Cyrillic С
    if text in ("c", "с"):
        return Action.CLEAR_CANVAS, None

    # Save: S / Ы
    if text in ("s", "ы"):
        return Action.SAVE_CANVAS, None

    # Debug overlay: D / В
    if text in ("d", "в"):
        return Action.TOGGLE_DEBUG, None

    # Hand skeleton: H / Р
    if text in ("h", "р"):
        return Action.TOGGLE_SKELETON, None

    # Settings: O / Щ
    if text in ("o", "щ"):
        return Action.OPEN_SETTINGS, None

    # Shortcuts help: ? / . , / Б Ю
    if text in ("?", "/", ".", ",", "б", "ю"):
        return Action.OPEN_SHORTCUTS, None

    # Decrease clear threshold: [ { / Х Ш
    if text in ("[", "{", "х", "ш"):
        return Action.CLEAR_PINCH_DEC, None

    # Increase clear threshold: ] } / Ъ Ғ
    if text in ("]", "}", "ъ", "ғ"):
        return Action.CLEAR_PINCH_INC, None

    # Brush thickness +: + / =
    if text in ("+", "=") or key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
        return Action.THICKNESS_INC, None

    # Brush thickness -: - / _
    if text in ("-", "_") or key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
        return Action.THICKNESS_DEC, None

    # 3. Match by Qt key code
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

    # 4. Match by physical macOS keycode
    if vk is not None and vk in MAC_VK_MAP:
        return MAC_VK_MAP[vk], None

    return None, None


def resolve_cv2_key(code: int) -> Tuple[Optional[Action], Optional[str]]:
    """Map a ``cv2.waitKey()`` code to an action (kept for backward compatibility)."""
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
