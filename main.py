"""
Air Draw — draw in the air with your webcam and MediaPipe Hands.

Application entry point.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict

from PyQt6.QtWidgets import QApplication

from src.config import apply_overrides, load_config
from src.ui.main_window import MainWindow
from src.ui.shortcuts_dialog import ShortcutsDialog
from src.version import __version__

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("air_draw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Air Draw — draw in the air with hand gestures")
    parser.add_argument("--version", action="version", version=f"Air Draw {__version__}")
    parser.add_argument("--camera", type=int, default=None, help="Webcam index")
    parser.add_argument("--width", type=int, default=None, help="Capture width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Capture height in pixels")
    parser.add_argument("--fps", type=int, default=None, help="FPS limit (30 recommended, 0 = unlimited)")
    parser.add_argument("--lang", type=str, choices=["ru", "kk", "en"], default=None, help="Interface language")
    parser.add_argument(
        "--save-options", action="store_true",
        help="Keep the command-line values in config.json (by default they apply to this run only)",
    )
    return parser.parse_args()


def build_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """Collect the command-line flags that were given."""
    flags = {
        "camera_index": args.camera,
        "width": args.width,
        "height": args.height,
        "fps_limit": args.fps,
        "language": args.lang,
    }
    return {name: value for name, value in flags.items() if value is not None}


def main() -> None:
    args = parse_args()

    # Load the saved configuration (or the recommended defaults on first run)
    config = load_config()

    # Command-line values take precedence for this run. Unless --save-options is
    # given, they are not written back to config.json.
    overrides = build_overrides(args)
    apply_overrides(config, overrides)
    if args.save_options:
        # Treat the flags as ordinary settings: they will be written on exit
        config.session_overrides = frozenset()

    app = QApplication(sys.argv)
    app.setApplicationName("Air Draw")

    # Show the shortcuts cheat sheet before the main window, unless disabled
    if config.show_shortcuts_on_start:
        dialog = ShortcutsDialog(config)
        dialog.exec()

    window = MainWindow(config)
    window.show()

    # MainWindow.closeEvent saves the settings
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
