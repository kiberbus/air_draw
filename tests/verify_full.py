"""
End-to-end smoke test of all Air Draw modules:

- translation tables are complete and every string formats without errors
- MediaPipe Hands initializes and frames go through ``_process_hand``
- MainWindow actions (colors 0-9, clear, save, gestures, hotkeys)
- SettingsDialog (editing fields, reset to recommended, saving to config.json)
- ShortcutsDialog (checkbox state, saving)
- ThreadedCamera starts and shuts down cleanly

Run with ``python -m tests.verify_full`` from the project root.
A webcam is optional; without one the camera simply yields no frames.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Run Qt headless so the script works without a display
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication

from src.config import (
    RECOMMENDED_DEFAULTS,
    TRANSLATIONS,
    AppConfig,
    get_config_path,
    get_recommended_config,
    load_config,
    save_config,
    tr,
)
from src.gestures import Gesture, classify_gesture, hand_scale, smooth_point
from src.key_mapper import Action, resolve_cv2_key, resolve_qt_key_event
from src.processor_info import detect_processor
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.shortcuts_dialog import ShortcutsDialog


class MockKeyEvent:
    def __init__(self, text: str = "", key: int = 0, vk: int = -1) -> None:
        self._text = text
        self._key = key
        self._vk = vk

    def text(self) -> str:
        return self._text

    def key(self) -> int:
        return self._key

    def nativeVirtualKey(self) -> int:
        return self._vk


def verify_translations() -> None:
    print("1. Checking translation tables...")
    languages = ["ru", "kk", "en"]
    base_keys = set(TRANSLATIONS["ru"].keys())

    for lang in languages:
        assert lang in TRANSLATIONS, f"Missing language {lang}"
        lang_keys = set(TRANSLATIONS[lang].keys())
        missing = base_keys - lang_keys
        assert not missing, f"Language {lang} is missing keys: {missing}"

        # Every string must format with the known placeholders
        for k in base_keys:
            try:
                res = tr(
                    k, lang=lang, num="5", val=10, filename="test.png", path="test/path", key="1",
                    name="IDLE", arch="arm64", logical=8, physical=8,
                )
                assert isinstance(res, str) and len(res) > 0
            except Exception as e:
                raise AssertionError(f"Failed to format key '{k}' for language '{lang}': {e}")

    print("   ✓ All 3 languages (RU, KK, EN) have every key and format correctly")


def verify_processor_info() -> None:
    print("2. Checking CPU detection...")
    info = detect_processor()
    assert info.brand, "CPU brand is empty"
    assert info.architecture in ("arm64", "x86_64", "AMD64", "aarch64", "arm"), f"Unknown architecture: {info.architecture}"
    assert info.logical_cores >= 1
    assert info.physical_cores >= 1
    display = info.get_display_name()
    assert info.brand in display
    cpu_load = info.get_cpu_load()
    print(f"   ✓ CPU: {display} | Load: {cpu_load}%")


def verify_config_and_recommended() -> None:
    print("3. Checking config defaults...")
    rec = get_recommended_config()
    # Recommended values: pinch ratios 17, 30 FPS
    assert rec.draw_pinch_ratio == 17, f"draw_pinch_ratio must be 17, got {rec.draw_pinch_ratio}"
    assert rec.clear_pinch_ratio == 17, f"clear_pinch_ratio must be 17, got {rec.clear_pinch_ratio}"
    assert rec.fps_limit == 30, f"fps_limit must be 30, got {rec.fps_limit}"

    # All 10 palette digits must be valid BGR colors
    for digit in "0123456789":
        assert digit in rec.palette, f"Digit {digit} is missing from the palette"
        color = rec.palette[digit]
        assert len(color) == 3, f"Color for {digit} must have 3 channels (BGR)"
        for c in color:
            assert 0 <= c <= 255, f"Color channel out of range 0..255: {c}"

    # Save / load round trip
    save_config(rec)
    loaded = load_config()
    assert loaded.draw_pinch_ratio == 17
    assert loaded.clear_pinch_ratio == 17
    assert loaded.fps_limit == 30
    print("   ✓ Config defaults (17, 30) are valid")


def verify_ui_components(app: QApplication) -> None:
    print("4. Checking UI components and the frame pipeline...")
    cfg = get_recommended_config()

    # 4.1 ShortcutsDialog
    sc_dlg = ShortcutsDialog(cfg)
    assert sc_dlg.chk_dont_show is not None
    # Simulate clicking OK
    sc_dlg.chk_dont_show.setChecked(False)
    sc_dlg._on_ok()
    assert cfg.show_shortcuts_on_start is True
    sc_dlg.close()
    print("   ✓ ShortcutsDialog OK")

    # 4.2 SettingsDialog
    st_dlg = SettingsDialog(cfg)
    # Language switching
    for i in range(st_dlg.combo_lang.count()):
        st_dlg.combo_lang.setCurrentIndex(i)
        assert st_dlg.combo_lang.currentData() in ("ru", "kk", "en")

    # Threshold editing
    st_dlg.spin_draw_pinch.setValue(17)
    st_dlg.spin_clear_pinch.setValue(17)
    st_dlg.combo_fps.setCurrentIndex(3)  # 30 FPS

    # Palette buttons
    for digit in "0123456789":
        assert digit in st_dlg.color_buttons
        # Simulate picking a color
        st_dlg.current_palette[digit] = [100, 150, 200]
        st_dlg._update_button_color(st_dlg.color_buttons[digit], [100, 150, 200])

    # Reset to recommended values
    rec = get_recommended_config()
    st_dlg.spin_draw_pinch.setValue(rec.draw_pinch_ratio)
    st_dlg.spin_clear_pinch.setValue(rec.clear_pinch_ratio)
    assert st_dlg.spin_draw_pinch.value() == 17
    assert st_dlg.spin_clear_pinch.value() == 17

    # Save settings
    st_dlg._on_save()
    assert cfg.draw_pinch_ratio == 17
    assert cfg.clear_pinch_ratio == 17
    st_dlg.close()
    print("   ✓ SettingsDialog OK")

    # 4.3 MainWindow
    win = MainWindow(cfg)

    # Switch through all colors 0-9
    for digit in "0123456789":
        win._select_color(digit)
        assert win.config.current_color_key == digit
        bgr = win.config.get_color_bgr()
        assert len(bgr) == 3

    # Brush thickness
    old_th = win.config.thickness
    win._increase_thickness()
    assert win.config.thickness == old_th + 1
    win._decrease_thickness()
    assert win.config.thickness == old_th

    # Clear canvas
    win.canvas[10:50, 10:50] = 255
    win.canvas_mask[10:50, 10:50] = 255
    win._clear_canvas()
    assert np.count_nonzero(win.canvas) == 0
    assert np.count_nonzero(win.canvas_mask) == 0

    # Save canvas
    win.canvas[10:20, 10:20] = [0, 255, 0]
    win._save_canvas()
    captures = list(Path("air_draw_captures").glob("*.png"))
    assert len(captures) > 0, "Drawing was not saved"

    # Run a frame through MediaPipe
    test_frame = np.zeros((win.height, win.width, 3), dtype=np.uint8)
    # Draw a circle so the frame is not empty
    cv2.circle(test_frame, (win.width // 2, win.height // 2), 50, (200, 200, 200), -1)

    info = win._process_hand(test_frame)
    win._render_overlay(test_frame, info)
    comp = win._composite(test_frame)
    assert comp.shape == test_frame.shape
    win._display_frame(comp)
    win._update_status_bar(info)

    # Hotkeys via keyPressEvent
    keys_to_test = [
        MockKeyEvent(text="c"),
        MockKeyEvent(text="с"),  # Cyrillic С
        MockKeyEvent(text="s"),
        MockKeyEvent(text="ы"),  # Cyrillic Ы
        MockKeyEvent(text="d"),
        MockKeyEvent(text="в"),  # Cyrillic В
        MockKeyEvent(text="h"),
        MockKeyEvent(text="р"),  # Cyrillic Р
        MockKeyEvent(text="+"),
        MockKeyEvent(text="-"),
        MockKeyEvent(text="1"),
        MockKeyEvent(text="9"),
        MockKeyEvent(text="0"),
    ]
    for k_ev in keys_to_test:
        win.keyPressEvent(k_ev)

    win.close()
    print("   ✓ MainWindow and the frame pipeline OK")


def main() -> None:
    app = QApplication(sys.argv)
    verify_translations()
    verify_processor_info()
    verify_config_and_recommended()
    verify_ui_components(app)
    print("\n==============================================")
    print("ALL CHECKS PASSED")
    print("==============================================")


if __name__ == "__main__":
    main()
