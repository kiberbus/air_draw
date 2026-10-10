"""
Unit tests for the Air Draw components.

Run from the project root with ``pytest tests/test_air_draw.py``.
"""

from __future__ import annotations

import json
import random
import string
import sys
from typing import Optional
from unittest import mock

# tests.support must be imported before any src module: it sets up the temporary data folder
from tests.support import MockKeyEvent, MockLandmark

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.camera import ThreadedCamera
from src.config import (
    PALETTE_KEYS,
    RANGES,
    TRANSLATIONS,
    AppConfig,
    apply_overrides,
    clamp_setting,
    config_from_dict,
    get_config_path,
    get_recommended_config,
    load_config,
    save_config,
    tr,
)
from src.gestures import (
    Gesture,
    OneEuroFilter,
    PointSmoother,
    classify_gesture,
    hand_scale,
)
from src.key_mapper import Action, resolve_qt_key_event
from src.processor_info import detect_processor


def _hand(thumb: tuple, index: tuple, middle: tuple) -> list:
    """21 landmarks on a 1000x1000 frame with a 300 px hand scale."""
    landmarks = [MockLandmark(0.5, 0.5) for _ in range(21)]
    landmarks[0] = MockLandmark(0.5, 0.8)   # wrist
    landmarks[9] = MockLandmark(0.5, 0.5)   # middle finger MCP
    landmarks[4] = MockLandmark(*thumb)
    landmarks[8] = MockLandmark(*index)
    landmarks[12] = MockLandmark(*middle)
    return landmarks


def _placeholders(text: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def _write_config_file(data) -> None:
    get_config_path().write_text(json.dumps(data), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def test_recommended_defaults() -> None:
    rec = get_recommended_config()
    assert rec.draw_pinch_ratio == 17
    assert rec.clear_pinch_ratio == 17
    assert rec.fps_limit == 30
    assert list(rec.palette) == list(PALETTE_KEYS)


def test_save_and_load_round_trip() -> None:
    cfg = get_recommended_config()
    cfg.thickness = 9
    cfg.palette["3"] = [1, 2, 3]
    save_config(cfg)

    loaded = load_config()
    assert loaded.thickness == 9
    assert loaded.palette["3"] == [1, 2, 3]
    assert loaded.session_overrides == frozenset()


def test_unknown_and_invalid_values_fall_back_to_defaults() -> None:
    cfg = config_from_dict({
        "camera_index": "abc",       # not a number -> default
        "fps_limit": "45",           # numeric string -> accepted
        "show_debug": "true",        # string boolean -> accepted
        "language": "xx",            # unknown language -> Russian
        "current_color_key": "Z",    # not a palette key -> "1"
        "removed_setting": 42,       # unknown key -> ignored
    })
    assert cfg.camera_index == 0
    assert cfg.fps_limit == 45
    assert cfg.show_debug is True
    assert cfg.language == "ru"
    assert cfg.current_color_key == "1"


def test_numeric_values_are_clamped_to_ranges() -> None:
    cfg = config_from_dict({"draw_pinch_ratio": 3, "camera_index": 500, "detection_scale": 9})
    assert cfg.draw_pinch_ratio == RANGES["draw_pinch_ratio"][0]
    assert cfg.camera_index == RANGES["camera_index"][1]
    assert cfg.detection_scale == RANGES["detection_scale"][1]
    assert clamp_setting("thickness", 100) == RANGES["thickness"][1]


def test_palette_entries_are_validated() -> None:
    cfg = config_from_dict({"palette": {"1": [0, 0, 300], "2": [1, 2, 3], "x": [1, 2, 3]}})
    assert cfg.palette["1"] == get_recommended_config().palette["1"]  # 300 is not a channel value
    assert cfg.palette["2"] == [1, 2, 3]
    assert "x" not in cfg.palette
    assert len(cfg.palette) == len(PALETTE_KEYS)


def test_broken_config_is_kept_and_not_overwritten_on_load() -> None:
    broken = "{ this is not json"
    get_config_path().write_text(broken, encoding="utf-8")

    cfg = load_config()
    assert cfg.draw_pinch_ratio == 17

    backup = get_config_path().with_name("config.broken.json")
    assert backup.read_text(encoding="utf-8") == broken
    assert get_config_path().read_text(encoding="utf-8") == broken


def test_command_line_overrides_are_not_saved() -> None:
    _write_config_file({"camera_index": 0, "show_debug": False})

    cfg = load_config()
    apply_overrides(cfg, {"camera_index": 7})
    assert cfg.camera_index == 7

    # Another setting changed during the run is saved, the flag is not
    cfg.show_debug = True
    save_config(cfg)

    stored = json.loads(get_config_path().read_text(encoding="utf-8"))
    assert stored["camera_index"] == 0
    assert stored["show_debug"] is True


def test_override_removed_from_disk_when_not_stored() -> None:
    _write_config_file({"show_debug": False})  # camera_index is not stored at all

    cfg = load_config()
    apply_overrides(cfg, {"camera_index": 4})
    save_config(cfg)

    assert "camera_index" not in json.loads(get_config_path().read_text(encoding="utf-8"))


def test_overrides_are_clamped() -> None:
    cfg = AppConfig()
    apply_overrides(cfg, {"fps_limit": 1000})
    assert cfg.fps_limit == RANGES["fps_limit"][1]
    assert cfg.session_overrides == frozenset({"fps_limit"})


def test_translations_are_complete_and_consistent() -> None:
    base_keys = set(TRANSLATIONS["ru"])
    for lang in ("ru", "kk", "en"):
        assert set(TRANSLATIONS[lang]) == base_keys, f"keys differ for {lang}"

    # Every language uses the same placeholders for each message
    placeholders = {k: _placeholders(v) for k, v in TRANSLATIONS["ru"].items()}
    for lang in ("kk", "en"):
        for k, v in TRANSLATIONS[lang].items():
            assert _placeholders(v) == placeholders[k], f"placeholders differ for {k} in {lang}"


def test_translations_format_with_all_placeholders() -> None:
    values = dict(num="5", val=10, filename="a.png", key="1", name="IDLE", arch="arm64",
                  logical=8, physical=8, brand="CPU", cores=8, load="12", fps="30",
                  target="/30", index=3)
    for pack in TRANSLATIONS.values():
        for text in pack.values():
            text.format(**{name: values[name] for name in _placeholders(text)})


def test_tr_falls_back_to_key_and_russian() -> None:
    assert tr("no_such_key", "en") == "no_such_key"
    assert tr("btn_ok", "xx") == TRANSLATIONS["ru"]["btn_ok"]


# --------------------------------------------------------------------------- #
# Processor detection
# --------------------------------------------------------------------------- #

def test_processor() -> None:
    proc = detect_processor()
    assert proc.brand, "Brand should not be empty"
    assert proc.logical_cores >= 1, "Should detect at least 1 core"
    assert detect_processor() is proc, "Detection result is cached"


# --------------------------------------------------------------------------- #
# Keyboard mapping
# --------------------------------------------------------------------------- #

def test_key_mapper_letters_and_digits() -> None:
    cases = [
        ("q", Action.QUIT, None), ("й", Action.QUIT, None),
        ("c", Action.CLEAR_CANVAS, None), ("с", Action.CLEAR_CANVAS, None),
        ("s", Action.SAVE_CANVAS, None), ("ы", Action.SAVE_CANVAS, None),
        ("d", Action.TOGGLE_DEBUG, None), ("в", Action.TOGGLE_DEBUG, None),
        ("h", Action.TOGGLE_SKELETON, None), ("р", Action.TOGGLE_SKELETON, None),
        ("o", Action.OPEN_SETTINGS, None), ("щ", Action.OPEN_SETTINGS, None),
        ("?", Action.OPEN_SHORTCUTS, None),
        ("[", Action.CLEAR_PINCH_DEC, None), ("х", Action.CLEAR_PINCH_DEC, None),
        ("]", Action.CLEAR_PINCH_INC, None), ("ъ", Action.CLEAR_PINCH_INC, None),
        ("1", Action.SELECT_COLOR, "1"), ("7", Action.SELECT_COLOR, "7"), ("0", Action.SELECT_COLOR, "0"),
        ("+", Action.THICKNESS_INC, None), ("-", Action.THICKNESS_DEC, None),
    ]
    for char, expected_action, expected_param in cases:
        action, param = resolve_qt_key_event(MockKeyEvent(text=char))
        assert action == expected_action, f"For {char!r}: expected {expected_action}, got {action}"
        if expected_param is not None:
            assert param == expected_param


def test_key_mapper_qt_key_codes_and_macos_keycodes() -> None:
    assert resolve_qt_key_event(MockKeyEvent(key=int(Qt.Key.Key_5))) == (Action.SELECT_COLOR, "5")
    assert resolve_qt_key_event(MockKeyEvent(key=int(Qt.Key.Key_F1))) == (Action.OPEN_SHORTCUTS, None)
    assert resolve_qt_key_event(MockKeyEvent(text="", vk=12)) == (Action.QUIT, None)
    assert resolve_qt_key_event(MockKeyEvent(text="", vk=8)) == (Action.CLEAR_CANVAS, None)
    assert resolve_qt_key_event(MockKeyEvent(text="", vk=29)) == (Action.SELECT_COLOR, "0")
    assert resolve_qt_key_event(MockKeyEvent(text="z")) == (None, None)


# --------------------------------------------------------------------------- #
# Gestures and smoothing
# --------------------------------------------------------------------------- #

def test_hand_scale() -> None:
    landmarks = _hand((0.5, 0.5), (0.5, 0.5), (0.5, 0.5))
    assert abs(hand_scale(landmarks, 1000, 1000) - 300.0) < 1.0


def test_classify_draw_clear_idle() -> None:
    # Threshold with ratio 0.17 is 300 * 0.17 = 51 px
    draw = classify_gesture(_hand((0.5, 0.5), (0.5, 0.52), (0.5, 0.7)), 1000, 1000)
    assert draw.gesture == Gesture.DRAW

    clear = classify_gesture(_hand((0.5, 0.5), (0.5, 0.7), (0.5, 0.52)), 1000, 1000)
    assert clear.gesture == Gesture.CLEAR

    idle = classify_gesture(_hand((0.5, 0.5), (0.5, 0.7), (0.5, 0.7)), 1000, 1000)
    assert idle.gesture == Gesture.IDLE


def test_pinch_hysteresis_keeps_a_held_pinch() -> None:
    # 60 px is above the 51 px threshold but below the released threshold (51 * 1.25)
    borderline = _hand((0.5, 0.5), (0.5, 0.56), (0.5, 0.7))

    assert classify_gesture(borderline, 1000, 1000, previous=Gesture.IDLE).gesture == Gesture.IDLE
    assert classify_gesture(borderline, 1000, 1000, previous=Gesture.DRAW).gesture == Gesture.DRAW


def test_one_euro_filter_reduces_jitter_on_still_signal() -> None:
    rng = random.Random(0)
    raw = [100.0 + rng.uniform(-3.0, 3.0) for _ in range(300)]
    smooth_filter = OneEuroFilter(min_cutoff=1.0, beta=0.03)
    filtered = [smooth_filter(x, 1 / 30) for x in raw]

    def spread(values):
        mean = sum(values[60:]) / len(values[60:])
        return sum((v - mean) ** 2 for v in values[60:]) ** 0.5

    assert spread(filtered) < spread(raw) * 0.5
    assert abs(filtered[-1] - 100.0) < 1.0


def test_one_euro_filter_follows_fast_motion() -> None:
    smooth_filter = OneEuroFilter(min_cutoff=1.0, beta=0.03)
    smooth_filter(0.0, 1 / 30)
    # A jump of 500 px in one frame is followed almost immediately (little lag)
    assert smooth_filter(500.0, 1 / 30) > 400.0


def test_point_smoother_reset_returns_raw_point() -> None:
    smoother = PointSmoother(min_cutoff=1.0, beta=0.03)
    smoother.update((100, 100), 1 / 30)
    smoother.update((120, 120), 1 / 30)
    smoother.reset()
    assert smoother.update((400, 300), 1 / 30) == (400, 300)


# --------------------------------------------------------------------------- #
# Camera
# --------------------------------------------------------------------------- #

def test_missing_camera_is_reported_not_opened() -> None:
    camera = ThreadedCamera(camera_index=97)
    try:
        assert not camera.is_opened()
        assert camera.read() == (False, None)
    finally:
        camera.release()


# --------------------------------------------------------------------------- #
# Qt widgets
# --------------------------------------------------------------------------- #

_qt_app: Optional[QApplication] = None


def _app() -> QApplication:
    # Keep a reference: Qt aborts if the application object is garbage-collected while widgets exist
    global _qt_app
    if _qt_app is None:
        _qt_app = QApplication.instance() or QApplication(sys.argv)
    return _qt_app


def test_shortcuts_dialog_saves_checkbox_state() -> None:
    from src.ui.shortcuts_dialog import ShortcutsDialog

    _app()
    cfg = get_recommended_config()
    dlg = ShortcutsDialog(cfg)
    assert dlg.windowTitle() == tr("shortcuts_title", cfg.language)
    dlg.chk_dont_show.setChecked(True)
    dlg._on_ok()
    assert cfg.show_shortcuts_on_start is False
    dlg.close()


def test_settings_dialog_does_not_change_stored_values() -> None:
    from src.ui.settings_dialog import SettingsDialog

    _app()
    cfg = get_recommended_config()
    cfg.camera_index = 12                 # set by a flag or config.json, above the old 0..10 spinbox range
    cfg.width, cfg.height = 1000, 700     # custom resolution that is not in the list
    dlg = SettingsDialog(cfg)
    assert dlg.spin_cam_idx.value() == 12
    dlg._on_save()

    stored = load_config()
    assert stored.camera_index == 12
    assert (stored.width, stored.height) == (1000, 700)
    dlg.close()


def test_settings_reset_keeps_language_and_restores_defaults() -> None:
    from src.ui.settings_dialog import SettingsDialog

    _app()
    cfg = get_recommended_config()
    cfg.language = "kk"
    dlg = SettingsDialog(cfg)
    dlg.spin_smooth_cutoff.setValue(5.0)
    dlg.spin_draw_pinch.setValue(30)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dlg._on_reset_recommended()

    assert dlg.spin_draw_pinch.value() == 17
    assert dlg.spin_smooth_cutoff.value() == get_recommended_config().smoothing_min_cutoff
    assert dlg.combo_lang.currentData() == "kk"
    dlg.close()


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
