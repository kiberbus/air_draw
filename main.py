"""
Air Draw — draw in the air with your webcam and MediaPipe Hands.

Application entry point.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.config import load_config, save_config
from src.ui.main_window import MainWindow
from src.ui.shortcuts_dialog import ShortcutsDialog

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("air_draw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Air Draw — draw in the air with hand gestures")
    parser.add_argument("--camera", type=int, default=None, help="Webcam index")
    parser.add_argument("--width", type=int, default=None, help="Capture width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Capture height in pixels")
    parser.add_argument("--fps", type=int, default=None, help="FPS limit (30 recommended, 0 = unlimited)")
    parser.add_argument("--lang", type=str, choices=["ru", "kk", "en"], default=None, help="Interface language")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load the saved configuration (or the recommended defaults on first run)
    config = load_config()

    # Command-line arguments take precedence over the saved configuration
    if args.camera is not None:
        config.camera_index = args.camera
    if args.width is not None:
        config.width = args.width
    if args.height is not None:
        config.height = args.height
    if args.fps is not None:
        config.fps_limit = args.fps
    if args.lang is not None:
        config.language = args.lang

    app = QApplication(sys.argv)
    app.setApplicationName("Air Draw")

    # Show the shortcuts cheat sheet before the main window, unless disabled
    if config.show_shortcuts_on_start:
        dialog = ShortcutsDialog(config)
        dialog.exec()

    window = MainWindow(config)
    window.show()

    exit_code = app.exec()
    save_config(config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
