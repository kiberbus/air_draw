"""
Air Draw — Рисование в воздухе с помощью веб-камеры и MediaPipe Hands.
Главная точка входа приложения.
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
    parser = argparse.ArgumentParser(description="Air Draw — Рисование в воздухе жестами рук")
    parser.add_argument("--camera", type=int, default=None, help="Индекс веб-камеры")
    parser.add_argument("--width", type=int, default=None, help="Ширина захвата видео")
    parser.add_argument("--height", type=int, default=None, help="Высота захвата видео")
    parser.add_argument("--fps", type=int, default=None, help="Ограничение FPS (рекомендуемое 30)")
    parser.add_argument("--lang", type=str, choices=["ru", "kk", "en"], default=None, help="Язык интерфейса")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Загружаем сохранённую конфигурацию (или рекомендуемые настройки)
    config = load_config()

    # Переопределяем из CLI, если аргументы переданы явно
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

    # Если включен показ подсказки при старте — показываем плашку перед началом
    if config.show_shortcuts_on_start:
        dialog = ShortcutsDialog(config)
        dialog.exec()

    # Запуск главного окна
    window = MainWindow(config)
    window.show()

    exit_code = app.exec()
    save_config(config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()