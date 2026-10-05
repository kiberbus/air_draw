"""
Unit tests for the Air Draw components.

Run with ``pytest`` or ``python -m tests.test_air_draw`` from the project root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Run Qt headless so the tests work without a display
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.config import (
    RECOMMENDED_DEFAULTS,
    TRANSLATIONS,
    get_recommended_config,
    load_config,
    save_config,
    tr,
)
from src.gestures import (
    Gesture,
    classify_gesture,
    hand_scale,
    landmark_to_px,
    smooth_point,
)
from src.key_mapper import Action, resolve_qt_key_event
from src.processor_info import detect_processor


class MockLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class MockKeyEvent:
    def __init__(self, text: str, key: int = 0, vk: int = -1) -> None:
        self._text = text
        self._key = key
        self._vk = vk

    def text(self) -> str:
        return self._text

    def key(self) -> int:
        return self._key

    def nativeVirtualKey(self) -> int:
        return self._vk


def test_config() -> None:
    print("--- 1. Testing Config ---")
    rec = get_recommended_config()
    assert rec.draw_pinch_ratio == 17, f"Expected 17, got {rec.draw_pinch_ratio}"
    assert rec.clear_pinch_ratio == 17, f"Expected 17, got {rec.clear_pinch_ratio}"
    assert rec.fps_limit == 30, f"Expected 30, got {rec.fps_limit}"
    assert len(rec.palette) == 10, f"Expected 10 palette digits, got {len(rec.palette)}"

    # Save and reload
    save_config(rec)
    loaded = load_config()
    assert loaded.draw_pinch_ratio == 17
    assert loaded.clear_pinch_ratio == 17
    assert loaded.fps_limit == 30
    assert loaded.palette["1"] == [0, 255, 0]

    # Localization
    for lang in ["ru", "kk", "en"]:
        assert lang in TRANSLATIONS
        title = tr("app_title", lang)
        assert len(title) > 5, f"Title too short for {lang}"
        save_btn = tr("save_and_close", lang)
        assert len(save_btn) > 3, f"Save button text missing for {lang}"

    print("Config tests passed!")


def test_processor() -> None:
    print("--- 2. Testing Processor Detection ---")
    proc = detect_processor()
    print(f"Detected brand: {proc.brand}")
    print(f"Architecture: {proc.architecture}")
    print(f"Logical cores: {proc.logical_cores}, Physical cores: {proc.physical_cores}")
    assert proc.brand, "Brand should not be empty"
    assert proc.logical_cores >= 1, "Should detect at least 1 core"
    print("Processor detection passed!")


def test_key_mapper() -> None:
    print("--- 3. Testing Layout-Agnostic Key Mapper ---")
    # English vs Russian vs Kazakh
    cases = [
        # Quit
        ("q", Action.QUIT, None),
        ("й", Action.QUIT, None),
        # Clear
        ("c", Action.CLEAR_CANVAS, None),
        ("с", Action.CLEAR_CANVAS, None),
        # Save
        ("s", Action.SAVE_CANVAS, None),
        ("ы", Action.SAVE_CANVAS, None),
        # Debug
        ("d", Action.TOGGLE_DEBUG, None),
        ("в", Action.TOGGLE_DEBUG, None),
        # Skeleton
        ("h", Action.TOGGLE_SKELETON, None),
        ("р", Action.TOGGLE_SKELETON, None),
        # Settings
        ("o", Action.OPEN_SETTINGS, None),
        ("щ", Action.OPEN_SETTINGS, None),
        # Clear pinch adjust
        ("[", Action.CLEAR_PINCH_DEC, None),
        ("х", Action.CLEAR_PINCH_DEC, None),
        ("]", Action.CLEAR_PINCH_INC, None),
        ("ъ", Action.CLEAR_PINCH_INC, None),
        # Digits 0..9
        ("1", Action.SELECT_COLOR, "1"),
        ("2", Action.SELECT_COLOR, "2"),
        ("7", Action.SELECT_COLOR, "7"),
        ("0", Action.SELECT_COLOR, "0"),
        # Thickness
        ("+", Action.THICKNESS_INC, None),
        ("-", Action.THICKNESS_DEC, None),
    ]

    for char, expected_action, expected_param in cases:
        ev = MockKeyEvent(text=char)
        act, param = resolve_qt_key_event(ev)
        assert act == expected_action, f"For '{char}': expected {expected_action}, got {act}"
        if expected_param is not None:
            assert param == expected_param, f"For '{char}': expected param {expected_param}, got {param}"

    # macOS Virtual Scancode test (even if text is unknown/exotic)
    ev_mac_q = MockKeyEvent(text="", key=0, vk=12)
    assert resolve_qt_key_event(ev_mac_q)[0] == Action.QUIT
    ev_mac_c = MockKeyEvent(text="", key=0, vk=8)
    assert resolve_qt_key_event(ev_mac_c)[0] == Action.CLEAR_CANVAS

    print("Key mapper tests passed!")


def test_gestures() -> None:
    print("--- 4. Testing Gestures Classification ---")
    # 21 landmarks
    landmarks = [MockLandmark(0.5, 0.5) for _ in range(21)]
    # Wrist = (0.5, 0.8), Middle_MCP = (0.5, 0.5) -> distance = 0.3 * 1000 = 300px
    landmarks[0] = MockLandmark(0.5, 0.8)
    landmarks[9] = MockLandmark(0.5, 0.5)

    scale = hand_scale(landmarks, 1000, 1000)
    assert abs(scale - 300.0) < 1.0, f"Scale expected ~300, got {scale}"

    # Threshold with ratio 0.17 is 300 * 0.17 = 51px
    # Case A: Thumb (4) and Index (8) close (< 51px) -> DRAW
    landmarks[4] = MockLandmark(0.5, 0.5)
    landmarks[8] = MockLandmark(0.5, 0.52)  # dist = 20px
    landmarks[12] = MockLandmark(0.5, 0.7)  # dist = 200px
    info = classify_gesture(landmarks, 1000, 1000, draw_ratio=0.17, clear_ratio=0.17)
    assert info.gesture == Gesture.DRAW, f"Expected DRAW, got {info.gesture}"

    # Case B: Thumb (4) and Middle (12) close (< 51px) -> CLEAR
    landmarks[4] = MockLandmark(0.5, 0.5)
    landmarks[8] = MockLandmark(0.5, 0.7)
    landmarks[12] = MockLandmark(0.5, 0.52)
    info = classify_gesture(landmarks, 1000, 1000, draw_ratio=0.17, clear_ratio=0.17)
    assert info.gesture == Gesture.CLEAR, f"Expected CLEAR, got {info.gesture}"

    # Case C: Far away -> IDLE
    landmarks[4] = MockLandmark(0.5, 0.5)
    landmarks[8] = MockLandmark(0.5, 0.7)
    landmarks[12] = MockLandmark(0.5, 0.7)
    info = classify_gesture(landmarks, 1000, 1000, draw_ratio=0.17, clear_ratio=0.17)
    assert info.gesture == Gesture.IDLE, f"Expected IDLE, got {info.gesture}"

    print("Gestures tests passed!")


def test_qt_ui() -> None:
    print("--- 5. Testing PyQt6 UI Widgets ---")
    from PyQt6.QtWidgets import QApplication
    from src.ui.shortcuts_dialog import ShortcutsDialog
    from src.ui.settings_dialog import SettingsDialog

    app = QApplication(sys.argv)
    cfg = get_recommended_config()

    # Test ShortcutsDialog
    sc_dlg = ShortcutsDialog(cfg)
    assert sc_dlg.windowTitle() == tr("shortcuts_title", cfg.language)
    sc_dlg.chk_dont_show.setChecked(True)
    sc_dlg._on_ok()
    assert cfg.show_shortcuts_on_start is False

    # Test SettingsDialog
    st_dlg = SettingsDialog(cfg)
    assert st_dlg.windowTitle() == tr("settings", cfg.language)
    # Test reset to recommended
    st_dlg.spin_draw_pinch.setValue(25)
    st_dlg.spin_clear_pinch.setValue(25)
    assert st_dlg.spin_draw_pinch.value() == 25
    # Reset
    rec = get_recommended_config()
    st_dlg.spin_draw_pinch.setValue(rec.draw_pinch_ratio)
    st_dlg.spin_clear_pinch.setValue(rec.clear_pinch_ratio)
    assert st_dlg.spin_draw_pinch.value() == 17
    assert st_dlg.spin_clear_pinch.value() == 17

    st_dlg.close()
    sc_dlg.close()
    print("PyQt6 UI tests passed!")


if __name__ == "__main__":
    test_config()
    test_processor()
    test_key_mapper()
    test_gestures()
    test_qt_ui()
    print("\n==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
