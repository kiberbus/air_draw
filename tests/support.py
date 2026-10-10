"""
Shared test setup and helpers.

Import this module before any ``src`` module: it points Air Draw at a temporary
data folder, so test runs never read or overwrite the real ``config.json``, and
it runs Qt headless.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

DATA_DIR = Path(tempfile.mkdtemp(prefix="air_draw_test_"))
os.environ["AIR_DRAW_DATA_DIR"] = str(DATA_DIR)
atexit.register(shutil.rmtree, DATA_DIR, ignore_errors=True)


class MockLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


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
