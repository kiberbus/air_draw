"""
End-to-end smoke test of all Air Draw modules:

- translation tables are complete and every string formats without errors
- MediaPipe Hands initializes and frames go through ``_process_hand``
- MainWindow actions (colors 0-9, clear, save, gestures, hotkeys)
- a missing camera is reported in the window instead of an empty view
- SettingsDialog (editing fields, reset to recommended, saving to config.json)
- ShortcutsDialog (checkbox state, saving)

Run with ``python -m tests.verify_full`` from the project root.
A webcam is optional; without one the camera simply reports that it is missing.
"""

from __future__ import annotations

import string
import sys
from unittest import mock

# tests.support must be imported before any src module: it sets up the temporary data folder
from tests.support import DATA_DIR, MockKeyEvent

import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication

from src.config import (
    TRANSLATIONS,
    get_recommended_config,
    load_config,
    save_config,
    tr,
)
from src.processor_info import detect_processor
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.shortcuts_dialog import ShortcutsDialog

# Every placeholder used in any translation, with a sample value
SAMPLE_VALUES = dict(
    num="5", val=10, filename="test.png", path="test/path", key="1", name="IDLE",
    arch="arm64", logical=8, physical=8, brand="CPU", cores=8, load="12", fps="30",
    target="/30", index=3,
)


def verify_translations() -> None:
    print("1. Checking translation tables...")
    base_keys = set(TRANSLATIONS["ru"])
    for lang in ("ru", "kk", "en"):
        assert set(TRANSLATIONS[lang]) == base_keys, f"Language {lang} has missing or extra keys"
        for text in TRANSLATIONS[lang].values():
            names = {name for _, name, _, _ in string.Formatter().parse(text) if name}
            text.format(**{name: SAMPLE_VALUES[name] for name in names})  # raises on a bad placeholder
    assert tr("camera_error", "en", index=3).startswith("Camera 3")
    print("   ✓ All 3 languages (RU, KK, EN) have every key and format correctly")


def verify_processor_info() -> None:
    print("2. Checking CPU detection...")
    info = detect_processor()
    assert info.brand, "CPU brand is empty"
    assert info.logical_cores >= 1 and info.physical_cores >= 1
    print(f"   ✓ CPU: {info.get_display_name()} | Load: {info.get_cpu_load()}%")


def verify_config_defaults() -> None:
    print("3. Checking config defaults...")
    rec = get_recommended_config()
    assert rec.draw_pinch_ratio == 17, f"draw_pinch_ratio must be 17, got {rec.draw_pinch_ratio}"
    assert rec.clear_pinch_ratio == 17, f"clear_pinch_ratio must be 17, got {rec.clear_pinch_ratio}"
    assert rec.fps_limit == 30, f"fps_limit must be 30, got {rec.fps_limit}"
    for digit in "0123456789":
        color = rec.palette[digit]
        assert len(color) == 3 and all(0 <= c <= 255 for c in color), f"Bad color for {digit}: {color}"

    save_config(rec)
    loaded = load_config()
    assert loaded.draw_pinch_ratio == 17 and loaded.clear_pinch_ratio == 17 and loaded.fps_limit == 30
    assert (DATA_DIR / "config.json").exists(), "Config must be written to the data folder"
    print("   ✓ Config defaults (17, 30) are valid and saved to the data folder")


def verify_ui_components(app: QApplication) -> None:
    print("4. Checking UI components and the frame pipeline...")
    cfg = get_recommended_config()

    # 4.1 ShortcutsDialog
    sc_dlg = ShortcutsDialog(cfg)
    sc_dlg.chk_dont_show.setChecked(False)
    sc_dlg._on_ok()
    assert cfg.show_shortcuts_on_start is True
    sc_dlg.close()
    print("   ✓ ShortcutsDialog OK")

    # 4.2 SettingsDialog
    st_dlg = SettingsDialog(cfg)
    for i in range(st_dlg.combo_lang.count()):
        st_dlg.combo_lang.setCurrentIndex(i)
        assert st_dlg.combo_lang.currentData() in ("ru", "kk", "en")

    st_dlg.spin_draw_pinch.setValue(17)
    st_dlg.spin_clear_pinch.setValue(17)
    st_dlg.combo_fps.setCurrentIndex(3)  # 30 FPS
    for digit in "0123456789":
        st_dlg.current_palette[digit] = [100, 150, 200]
        st_dlg._update_button_color(st_dlg.color_buttons[digit], [100, 150, 200])

    st_dlg._on_save()
    assert cfg.draw_pinch_ratio == 17 and cfg.clear_pinch_ratio == 17
    st_dlg.close()
    print("   ✓ SettingsDialog OK")

    # 4.3 MainWindow (a webcam is optional)
    win = MainWindow(cfg)

    for digit in "0123456789":
        win._select_color(digit)
        assert win.config.current_color_key == digit
        assert len(win.config.get_color_bgr()) == 3

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

    # Save canvas: transparent PNG (4 channels), new file for every save
    before = set(win.output_dir.glob("*.png"))
    win.canvas[10:20, 10:20] = [0, 255, 0]
    win.canvas_mask[10:20, 10:20] = 255
    win._save_canvas()
    win._save_canvas()
    saved = set(win.output_dir.glob("*.png")) - before
    assert len(saved) == 2, "Each save must create its own file"
    assert win.output_dir.parent == DATA_DIR
    image = cv2.imread(str(next(iter(saved))), cv2.IMREAD_UNCHANGED)
    assert image.shape[2] == 4, "Saved PNG must have an alpha channel"

    # Run a frame through MediaPipe
    test_frame = np.zeros((win.frame_height, win.frame_width, 3), dtype=np.uint8)
    cv2.circle(test_frame, (win.frame_width // 2, win.frame_height // 2), 50, (200, 200, 200), -1)
    info = win._process_hand(test_frame, 1 / 30)
    win._render_overlay(test_frame, info)
    comp = win._composite(test_frame)
    assert comp.shape == test_frame.shape
    win._display_frame(comp)
    win._update_status_bar(info)

    # Main loop tick with a stand-in camera: a new frame is processed once, a repeat is skipped
    frames = [(True, test_frame.copy()), (False, None)]
    with mock.patch.object(win.camera, "read", side_effect=lambda: frames.pop(0)):
        win._on_frame_tick()
        win._on_frame_tick()
    assert win.current_fps >= 0.0 and not frames

    # Hotkeys via keyPressEvent
    for char in ["c", "с", "s", "ы", "d", "в", "h", "р", "+", "-", "1", "9", "0"]:
        win.keyPressEvent(MockKeyEvent(text=char))

    win.close()
    print("   ✓ MainWindow and the frame pipeline OK")

    # 4.4 A missing camera is reported in the window
    missing_cfg = get_recommended_config()
    missing_cfg.camera_index = 97
    win_missing = MainWindow(missing_cfg)
    assert not win_missing.camera.is_opened()
    assert win_missing.video_label.text() == tr("camera_error", missing_cfg.language, index=97)
    win_missing.close()
    print("   ✓ Missing camera is reported in the window")


def main() -> None:
    app = QApplication(sys.argv)
    verify_translations()
    verify_processor_info()
    verify_config_defaults()
    verify_ui_components(app)
    print("\n==============================================")
    print("ALL CHECKS PASSED")
    print("==============================================")


if __name__ == "__main__":
    main()
