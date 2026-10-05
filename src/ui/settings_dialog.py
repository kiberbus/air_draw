"""
Окно настроек со всеми параметрами, сбросом до рекомендуемых (пороги 17, FPS 30),
выбором языка, определением процессора и настройкой палитры 0-9.
"""

from __future__ import annotations

from typing import Dict, List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, get_recommended_config, save_config, tr
from ..processor_info import detect_processor


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.lang = config.language
        self.proc_info = detect_processor()

        # Локальная копия палитры для редактирования
        self.current_palette: Dict[str, List[int]] = {
            k: list(v) for k, v in config.palette.items()
        }
        self.color_buttons: Dict[str, QPushButton] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle(tr("settings", self.lang))
        self.setMinimumSize(540, 520)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 1. Вкладка "Основные"
        self.tab_general = QWidget()
        self._setup_general_tab(self.tab_general)
        self.tab_widget.addTab(self.tab_general, tr("tab_general", self.lang))

        # 2. Вкладка "Камера и FPS"
        self.tab_camera = QWidget()
        self._setup_camera_tab(self.tab_camera)
        self.tab_widget.addTab(self.tab_camera, tr("tab_camera", self.lang))

        # 3. Вкладка "Жесты и пороги"
        self.tab_gestures = QWidget()
        self._setup_gestures_tab(self.tab_gestures)
        self.tab_widget.addTab(self.tab_gestures, tr("tab_gestures", self.lang))

        # 4. Вкладка "Палитра (0-9)"
        self.tab_palette = QWidget()
        self._setup_palette_tab(self.tab_palette)
        self.tab_widget.addTab(self.tab_palette, tr("tab_palette", self.lang))

        # Нижняя панель кнопок
        bottom_layout = QHBoxLayout()

        self.btn_reset = QPushButton(tr("reset_recommended", self.lang))
        self.btn_reset.clicked.connect(self._on_reset_recommended)
        bottom_layout.addWidget(self.btn_reset)

        bottom_layout.addStretch()

        self.btn_cancel = QPushButton(tr("cancel", self.lang))
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(tr("save_and_close", self.lang))
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)
        bottom_layout.addWidget(self.btn_save)

        main_layout.addLayout(bottom_layout)

    # ----------------- 1. General Tab ----------------- #
    def _setup_general_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)

        form = QFormLayout()

        # Выбор языка
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("Русский", "ru")
        self.combo_lang.addItem("Қазақша", "kk")
        self.combo_lang.addItem("English", "en")

        idx = self.combo_lang.findData(self.config.language)
        if idx >= 0:
            self.combo_lang.setCurrentIndex(idx)
        form.addRow(tr("language_select", self.lang), self.combo_lang)

        # Чекбокс подсказки при старте
        self.chk_startup = QCheckBox(tr("startup_shortcuts_toggle", self.lang))
        self.chk_startup.setChecked(self.config.show_shortcuts_on_start)
        form.addRow("", self.chk_startup)

        layout.addLayout(form)

        # Определение процессора
        group_proc = QGroupBox(tr("processor_header", self.lang))
        proc_layout = QVBoxLayout(group_proc)

        lbl_cpu = QLabel(f"<b>{self.proc_info.brand}</b>")
        lbl_arch = QLabel(f"Архитектура: {self.proc_info.architecture} | Ядер: {self.proc_info.logical_cores} ({self.proc_info.physical_cores} физ.)")
        proc_layout.addWidget(lbl_cpu)
        proc_layout.addWidget(lbl_arch)

        cpu_load = self.proc_info.get_cpu_load()
        load_text = f"{cpu_load:.1f}%" if cpu_load is not None else "N/A"
        lbl_load = QLabel(f"{tr('processor_load', self.lang)} {load_text}")
        proc_layout.addWidget(lbl_load)

        layout.addWidget(group_proc)
        layout.addStretch()

    # ----------------- 2. Camera & FPS Tab ----------------- #
    def _setup_camera_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        # Индекс камеры
        self.spin_cam_idx = QSpinBox()
        self.spin_cam_idx.setRange(0, 10)
        self.spin_cam_idx.setValue(self.config.camera_index)
        form.addRow(tr("camera_index_label", self.lang), self.spin_cam_idx)

        # Разрешение камеры
        self.combo_res = QComboBox()
        self.combo_res.addItem("640 x 480", (640, 480))
        self.combo_res.addItem("960 x 540 (Рекомендуется)", (960, 540))
        self.combo_res.addItem("1280 x 720 (HD)", (1280, 720))
        self.combo_res.addItem("1920 x 1080 (Full HD)", (1920, 1080))

        current_res = (self.config.width, self.config.height)
        found_res = False
        for i in range(self.combo_res.count()):
            if self.combo_res.itemData(i) == current_res:
                self.combo_res.setCurrentIndex(i)
                found_res = True
                break
        if not found_res:
            self.combo_res.addItem(f"{current_res[0]} x {current_res[1]}", current_res)
            self.combo_res.setCurrentIndex(self.combo_res.count() - 1)

        form.addRow(tr("camera_resolution_label", self.lang), self.combo_res)

        # Ограничение FPS (рекомендуемое 30)
        self.combo_fps = QComboBox()
        self.combo_fps.addItem("15 FPS", 15)
        self.combo_fps.addItem("20 FPS", 20)
        self.combo_fps.addItem("24 FPS", 24)
        self.combo_fps.addItem("30 FPS (Рекомендуется)", 30)
        self.combo_fps.addItem("60 FPS", 60)
        self.combo_fps.addItem("Без ограничений", 0)

        found_fps = False
        for i in range(self.combo_fps.count()):
            if self.combo_fps.itemData(i) == self.config.fps_limit:
                self.combo_fps.setCurrentIndex(i)
                found_fps = True
                break
        if not found_fps:
            self.combo_fps.addItem(f"{self.config.fps_limit} FPS", self.config.fps_limit)
            self.combo_fps.setCurrentIndex(self.combo_fps.count() - 1)

        form.addRow(tr("fps_limit_label", self.lang), self.combo_fps)

        # Модель MediaPipe (0 - быстрая, 1 - точная)
        self.combo_model = QComboBox()
        self.combo_model.addItem(tr("model_fast", self.lang), 0)
        self.combo_model.addItem(tr("model_accurate", self.lang), 1)
        idx_m = self.combo_model.findData(self.config.model_complexity)
        if idx_m >= 0:
            self.combo_model.setCurrentIndex(idx_m)
        form.addRow(tr("model_complexity_label", self.lang), self.combo_model)

        # Масштаб детекции
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.25, 1.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(self.config.detection_scale)
        form.addRow(tr("detection_scale_label", self.lang), self.spin_scale)

        # Пороги confidence
        self.spin_det_conf = QDoubleSpinBox()
        self.spin_det_conf.setRange(0.1, 1.0)
        self.spin_det_conf.setSingleStep(0.05)
        self.spin_det_conf.setValue(self.config.detection_confidence)
        form.addRow(tr("detection_conf_label", self.lang), self.spin_det_conf)

        self.spin_track_conf = QDoubleSpinBox()
        self.spin_track_conf.setRange(0.1, 1.0)
        self.spin_track_conf.setSingleStep(0.05)
        self.spin_track_conf.setValue(self.config.tracking_confidence)
        form.addRow(tr("tracking_conf_label", self.lang), self.spin_track_conf)

        layout.addLayout(form)
        layout.addStretch()

    # ----------------- 3. Gestures Tab ----------------- #
    def _setup_gestures_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        # DRAW_PINCH_RATIO (рекомендуется строго 17)
        self.spin_draw_pinch = QSpinBox()
        self.spin_draw_pinch.setRange(5, 50)
        self.spin_draw_pinch.setValue(self.config.draw_pinch_ratio)
        form.addRow(tr("draw_pinch_label", self.lang), self.spin_draw_pinch)

        # CLEAR_PINCH_RATIO (рекомендуется строго 17)
        self.spin_clear_pinch = QSpinBox()
        self.spin_clear_pinch.setRange(5, 50)
        self.spin_clear_pinch.setValue(self.config.clear_pinch_ratio)
        form.addRow(tr("clear_pinch_label", self.lang), self.spin_clear_pinch)

        # Окно сглаживания
        self.spin_smoothing = QSpinBox()
        self.spin_smoothing.setRange(1, 15)
        self.spin_smoothing.setValue(self.config.smoothing_window)
        form.addRow(tr("smoothing_label", self.lang), self.spin_smoothing)

        # Скелет руки
        self.chk_skeleton = QCheckBox(tr("show_skeleton_label", self.lang))
        self.chk_skeleton.setChecked(self.config.show_skeleton)
        form.addRow("", self.chk_skeleton)

        # Отладочный оверлей
        self.chk_debug = QCheckBox(tr("show_debug_label", self.lang))
        self.chk_debug.setChecked(self.config.show_debug)
        form.addRow("", self.chk_debug)

        layout.addLayout(form)
        layout.addStretch()

    # ----------------- 4. Palette Tab ----------------- #
    def _setup_palette_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)

        desc = QLabel(tr("palette_description", self.lang))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        for d in digits:
            row_layout = QHBoxLayout()

            lbl = QLabel(tr("key_num_label", self.lang, num=d))
            lbl.setFixedWidth(100)
            row_layout.addWidget(lbl)

            # Кнопка с образцом цвета
            bgr = self.current_palette.get(d, [0, 255, 0])
            btn_color = QPushButton()
            btn_color.setFixedSize(50, 26)
            self._update_button_color(btn_color, bgr)
            row_layout.addWidget(btn_color)
            self.color_buttons[d] = btn_color

            # Кнопка выбора цвета
            btn_pick = QPushButton(tr("pick_color_btn", self.lang))
            btn_pick.clicked.connect(lambda _, key=d: self._on_pick_color(key))
            row_layout.addWidget(btn_pick)

            row_layout.addStretch()
            scroll_layout.addLayout(row_layout)

        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def _update_button_color(self, btn: QPushButton, bgr: List[int]) -> None:
        # BGR -> RGB для CSS
        r, g, b = bgr[2], bgr[1], bgr[0]
        btn.setStyleSheet(
            f"background-color: rgb({r}, {g}, {b}); border: 1px solid #777; border-radius: 3px;"
        )

    def _on_pick_color(self, key: str) -> None:
        current_bgr = self.current_palette.get(key, [0, 255, 0])
        initial = QColor(current_bgr[2], current_bgr[1], current_bgr[0])
        chosen = QColorDialog.getColor(initial, self, f"Выбор цвета для клавиши {key}")
        if chosen.isValid():
            new_bgr = [chosen.blue(), chosen.green(), chosen.red()]
            self.current_palette[key] = new_bgr
            if key in self.color_buttons:
                self._update_button_color(self.color_buttons[key], new_bgr)

    # ----------------- Сброс до рекомендуемых ----------------- #
    def _on_reset_recommended(self) -> None:
        reply = QMessageBox.question(
            self,
            tr("settings", self.lang),
            tr("reset_confirm", self.lang),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            rec = get_recommended_config()
            # Обновляем поля UI
            self.spin_cam_idx.setValue(rec.camera_index)

            # Разрешение
            for i in range(self.combo_res.count()):
                if self.combo_res.itemData(i) == (rec.width, rec.height):
                    self.combo_res.setCurrentIndex(i)
                    break

            # FPS: 30
            for i in range(self.combo_fps.count()):
                if self.combo_fps.itemData(i) == 30:
                    self.combo_fps.setCurrentIndex(i)
                    break

            # Модель и scale
            self.combo_model.setCurrentIndex(0)
            self.spin_scale.setValue(rec.detection_scale)
            self.spin_det_conf.setValue(rec.detection_confidence)
            self.spin_track_conf.setValue(rec.tracking_confidence)

            # Пороги: строго 17!
            self.spin_draw_pinch.setValue(17)
            self.spin_clear_pinch.setValue(17)
            self.spin_smoothing.setValue(rec.smoothing_window)

            self.chk_skeleton.setChecked(rec.show_skeleton)
            self.chk_debug.setChecked(rec.show_debug)
            self.chk_startup.setChecked(rec.show_shortcuts_on_start)

            # Палитра
            self.current_palette = {k: list(v) for k, v in rec.palette.items()}
            for k, btn in self.color_buttons.items():
                if k in self.current_palette:
                    self._update_button_color(btn, self.current_palette[k])

    # ----------------- Сохранение ----------------- #
    def _on_save(self) -> None:
        # Применяем значения в config
        new_lang = self.combo_lang.currentData()
        self.config.language = new_lang
        self.config.show_shortcuts_on_start = self.chk_startup.isChecked()
        self.config.camera_index = self.spin_cam_idx.value()

        res = self.combo_res.currentData()
        if res:
            self.config.width, self.config.height = res

        fps = self.combo_fps.currentData()
        self.config.fps_limit = fps if fps is not None else 30

        self.config.model_complexity = self.combo_model.currentData() or 0
        self.config.detection_scale = self.spin_scale.value()
        self.config.detection_confidence = self.spin_det_conf.value()
        self.config.tracking_confidence = self.spin_track_conf.value()

        # Пороги пинча
        self.config.draw_pinch_ratio = self.spin_draw_pinch.value()
        self.config.clear_pinch_ratio = self.spin_clear_pinch.value()
        self.config.smoothing_window = self.spin_smoothing.value()

        self.config.show_skeleton = self.chk_skeleton.isChecked()
        self.config.show_debug = self.chk_debug.isChecked()

        # Палитра
        self.config.palette = {k: list(v) for k, v in self.current_palette.items()}

        # Сохраняем на диск в config.json
        save_config(self.config)
        self.accept()
