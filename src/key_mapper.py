"""
Keyboard-layout-independent hotkey handling.

A key press is resolved in several passes so shortcuts work the same on
English (QWERTY), Russian (ЙЦУКЕН) and Kazakh layouts: by typed character,
by Qt key code, and finally by the physical macOS virtual keycode.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt


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

# Typed character -> action. Each action lists the Latin letter and the Cyrillic
# letter on the same key.
CHAR_MAP: Dict[str, Action] = {
    "q": Action.QUIT, "й": Action.QUIT,
    "c": Action.CLEAR_CANVAS, "с": Action.CLEAR_CANVAS,
    "s": Action.SAVE_CANVAS, "ы": Action.SAVE_CANVAS,
    "d": Action.TOGGLE_DEBUG, "в": Action.TOGGLE_DEBUG,
    "h": Action.TOGGLE_SKELETON, "р": Action.TOGGLE_SKELETON,
    "o": Action.OPEN_SETTINGS, "щ": Action.OPEN_SETTINGS,
    "?": Action.OPEN_SHORTCUTS, "/": Action.OPEN_SHORTCUTS, ".": Action.OPEN_SHORTCUTS,
    ",": Action.OPEN_SHORTCUTS, "б": Action.OPEN_SHORTCUTS, "ю": Action.OPEN_SHORTCUTS,
    "[": Action.CLEAR_PINCH_DEC, "{": Action.CLEAR_PINCH_DEC, "х": Action.CLEAR_PINCH_DEC, "ш": Action.CLEAR_PINCH_DEC,
    "]": Action.CLEAR_PINCH_INC, "}": Action.CLEAR_PINCH_INC, "ъ": Action.CLEAR_PINCH_INC, "ғ": Action.CLEAR_PINCH_INC,
    "+": Action.THICKNESS_INC, "=": Action.THICKNESS_INC,
    "-": Action.THICKNESS_DEC, "_": Action.THICKNESS_DEC,
}

# Qt key code -> action (used when the typed text is empty, e.g. with modifiers)
QT_KEY_MAP: Dict[Any, Action] = {
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
    Qt.Key.Key_Plus: Action.THICKNESS_INC,
    Qt.Key.Key_Equal: Action.THICKNESS_INC,
    Qt.Key.Key_Minus: Action.THICKNESS_DEC,
    Qt.Key.Key_Underscore: Action.THICKNESS_DEC,
}

DIGITS = "0123456789"


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

    # 1. Digits (color selection): by typed character, Qt key code, then macOS keycode
    if len(text) == 1 and text in DIGITS:
        return Action.SELECT_COLOR, text
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return Action.SELECT_COLOR, str(key - Qt.Key.Key_0)
    if vk is not None and vk in MAC_VK_DIGITS:
        return Action.SELECT_COLOR, MAC_VK_DIGITS[vk]

    # 2. Typed character (EN / RU / KK)
    if text in CHAR_MAP:
        return CHAR_MAP[text], None

    # 3. Qt key code
    if key in QT_KEY_MAP:
        return QT_KEY_MAP[key], None

    # 4. Physical macOS keycode
    if vk is not None and vk in MAC_VK_MAP:
        return MAC_VK_MAP[vk], None

    return None, None
