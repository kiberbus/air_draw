"""
Cheat-sheet dialog listing hand gestures and keyboard shortcuts,
with a "Do not show again on startup" checkbox.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..config import AppConfig, save_config, tr


class ShortcutsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.lang = config.language
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle(tr("shortcuts_title", self.lang))
        self.setMinimumWidth(480)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header
        title = QLabel(f"<h2>{tr('shortcuts_header', self.lang)}</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Gestures section
        gestures_box = QVBoxLayout()
        gestures_lbl = QLabel(f"<b>{tr('gestures_section', self.lang)}</b>")
        gestures_box.addWidget(gestures_lbl)
        gestures_box.addWidget(QLabel(tr("gesture_draw_desc", self.lang)))
        gestures_box.addWidget(QLabel(tr("gesture_clear_desc", self.lang)))
        layout.addLayout(gestures_box)

        # Separator
        line = QLabel("—" * 35)
        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(line)

        # Keyboard section
        keys_box = QVBoxLayout()
        keys_lbl = QLabel(f"<b>{tr('keys_section', self.lang)}</b>")
        keys_box.addWidget(keys_lbl)
        keys_box.addWidget(QLabel(tr("key_colors", self.lang)))
        keys_box.addWidget(QLabel(tr("key_thickness", self.lang)))
        keys_box.addWidget(QLabel(tr("key_clear", self.lang)))
        keys_box.addWidget(QLabel(tr("key_save", self.lang)))
        keys_box.addWidget(QLabel(tr("key_debug", self.lang)))
        keys_box.addWidget(QLabel(tr("key_skeleton", self.lang)))
        keys_box.addWidget(QLabel(tr("key_pinch_adjust", self.lang)))
        keys_box.addWidget(QLabel(tr("key_settings", self.lang)))
        keys_box.addWidget(QLabel(tr("key_exit", self.lang)))
        layout.addLayout(keys_box)

        # "Do not show again" checkbox
        self.chk_dont_show = QCheckBox(tr("dont_show_again", self.lang))
        self.chk_dont_show.setChecked(not self.config.show_shortcuts_on_start)
        layout.addWidget(self.chk_dont_show)

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton(tr("btn_ok", self.lang))
        self.btn_ok.setDefault(True)
        self.btn_ok.setFixedWidth(120)
        self.btn_ok.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

    def _on_ok(self) -> None:
        self.config.show_shortcuts_on_start = not self.chk_dont_show.isChecked()
        save_config(self.config)
        self.accept()
