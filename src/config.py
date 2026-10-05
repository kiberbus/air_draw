"""
Air Draw configuration: default settings, JSON persistence and
UI localization (Russian, Kazakh, English).
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("air_draw.config")

CONFIG_FILE_NAME = "config.json"

# Recommended defaults. Pinch ratios are stored as integer percentages of the
# hand size (17 -> 0.17); 17 and 30 FPS are the tuned recommended values.
RECOMMENDED_DEFAULTS = {
    "language": "ru",
    "show_shortcuts_on_start": True,
    "camera_index": 0,
    "width": 960,
    "height": 540,
    "fps_limit": 30,
    "model_complexity": 0,
    "detection_confidence": 0.6,
    "tracking_confidence": 0.6,
    "detection_scale": 1.0,
    "draw_pinch_ratio": 17,
    "clear_pinch_ratio": 17,
    "smoothing_window": 4,
    "thickness": 5,
    "current_color_key": "1",
    "show_skeleton": True,
    "show_debug": False,
    "palette": {  # Digit key -> brush color in BGR order (OpenCV)
        "1": [0, 255, 0],     # Green
        "2": [0, 0, 255],     # Red
        "3": [255, 0, 0],     # Blue
        "4": [0, 255, 255],   # Yellow
        "5": [255, 255, 0],   # Cyan
        "6": [255, 0, 255],   # Magenta
        "7": [0, 165, 255],   # Orange
        "8": [255, 255, 255], # White
        "9": [30, 30, 30],    # Near black
        "0": [128, 128, 128], # Gray
    },
}


@dataclass
class AppConfig:
    """All user-tunable settings; persisted to ``config.json``."""

    language: str = "ru"  # "ru", "kk", "en"
    show_shortcuts_on_start: bool = True
    camera_index: int = 0
    width: int = 960
    height: int = 540
    fps_limit: int = 30  # 0 = unlimited
    model_complexity: int = 0  # 0 = fast, 1 = accurate
    detection_confidence: float = 0.6
    tracking_confidence: float = 0.6
    detection_scale: float = 1.0  # Downscale factor for the frame fed to MediaPipe
    draw_pinch_ratio: int = 17   # Percent of hand size
    clear_pinch_ratio: int = 17  # Percent of hand size
    smoothing_window: int = 4  # Moving-average window, in frames
    thickness: int = 5
    current_color_key: str = "1"
    show_skeleton: bool = True
    show_debug: bool = False
    palette: Dict[str, List[int]] = field(
        default_factory=lambda: dict(RECOMMENDED_DEFAULTS["palette"])
    )

    @property
    def draw_pinch_float(self) -> float:
        return self.draw_pinch_ratio / 100.0

    @property
    def clear_pinch_float(self) -> float:
        return self.clear_pinch_ratio / 100.0

    def get_color_bgr(self, key: Optional[str] = None) -> Tuple[int, int, int]:
        """Return the BGR color for a palette key (defaults to the active color)."""
        k = key or self.current_color_key
        c = self.palette.get(str(k), [0, 255, 0])
        return int(c[0]), int(c[1]), int(c[2])

    def set_color_bgr(self, key: str, bgr: Tuple[int, int, int]) -> None:
        self.palette[str(key)] = [int(bgr[0]), int(bgr[1]), int(bgr[2])]


def get_data_dir() -> Path:
    """
    Folder for ``config.json`` and saved drawings.

    When running from source this is the project root. In a PyInstaller build
    the bundle is unpacked to a temporary (or read-only) location, so user data
    goes to ``~/AirDraw`` instead.
    """
    if getattr(sys, "frozen", False):
        data_dir = Path.home() / "AirDraw"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """Path to ``config.json`` inside the data folder."""
    return get_data_dir() / CONFIG_FILE_NAME


def load_config() -> AppConfig:
    """Load settings from disk, creating the file with defaults if missing."""
    config_file = get_config_path()
    if not config_file.exists():
        logger.info("Config file not found, using recommended settings.")
        cfg = get_recommended_config()
        save_config(cfg)
        return cfg

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge over the defaults so configs from older versions still load
        merged = dict(RECOMMENDED_DEFAULTS)
        merged.update(data)
        if "palette" in data and isinstance(data["palette"], dict):
            p = dict(RECOMMENDED_DEFAULTS["palette"])
            p.update(data["palette"])
            merged["palette"] = p

        # Coerce types in case the file was edited by hand
        return AppConfig(
            language=str(merged.get("language", "ru")),
            show_shortcuts_on_start=bool(merged.get("show_shortcuts_on_start", True)),
            camera_index=int(merged.get("camera_index", 0)),
            width=int(merged.get("width", 960)),
            height=int(merged.get("height", 540)),
            fps_limit=int(merged.get("fps_limit", 30)),
            model_complexity=int(merged.get("model_complexity", 0)),
            detection_confidence=float(merged.get("detection_confidence", 0.6)),
            tracking_confidence=float(merged.get("tracking_confidence", 0.6)),
            detection_scale=float(merged.get("detection_scale", 1.0)),
            draw_pinch_ratio=int(merged.get("draw_pinch_ratio", 17)),
            clear_pinch_ratio=int(merged.get("clear_pinch_ratio", 17)),
            smoothing_window=int(merged.get("smoothing_window", 4)),
            thickness=int(merged.get("thickness", 5)),
            current_color_key=str(merged.get("current_color_key", "1")),
            show_skeleton=bool(merged.get("show_skeleton", True)),
            show_debug=bool(merged.get("show_debug", False)),
            palette=dict(merged.get("palette", RECOMMENDED_DEFAULTS["palette"])),
        )
    except Exception as e:
        logger.error(f"Failed to load config: {e}. Falling back to recommended settings.")
        return get_recommended_config()


def save_config(cfg: AppConfig) -> None:
    """Write settings to ``config.json``."""
    config_file = get_config_path()
    try:
        data = asdict(cfg)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Config saved to %s", config_file)
    except Exception as e:
        logger.error("Failed to save config: %s", e)


def get_recommended_config() -> AppConfig:
    """Return a fresh config with the recommended settings (pinch 17, 30 FPS)."""
    return AppConfig(
        language=RECOMMENDED_DEFAULTS["language"],
        show_shortcuts_on_start=RECOMMENDED_DEFAULTS["show_shortcuts_on_start"],
        camera_index=RECOMMENDED_DEFAULTS["camera_index"],
        width=RECOMMENDED_DEFAULTS["width"],
        height=RECOMMENDED_DEFAULTS["height"],
        fps_limit=RECOMMENDED_DEFAULTS["fps_limit"],
        model_complexity=RECOMMENDED_DEFAULTS["model_complexity"],
        detection_confidence=RECOMMENDED_DEFAULTS["detection_confidence"],
        tracking_confidence=RECOMMENDED_DEFAULTS["tracking_confidence"],
        detection_scale=RECOMMENDED_DEFAULTS["detection_scale"],
        draw_pinch_ratio=RECOMMENDED_DEFAULTS["draw_pinch_ratio"],
        clear_pinch_ratio=RECOMMENDED_DEFAULTS["clear_pinch_ratio"],
        smoothing_window=RECOMMENDED_DEFAULTS["smoothing_window"],
        thickness=RECOMMENDED_DEFAULTS["thickness"],
        current_color_key=RECOMMENDED_DEFAULTS["current_color_key"],
        show_skeleton=RECOMMENDED_DEFAULTS["show_skeleton"],
        show_debug=RECOMMENDED_DEFAULTS["show_debug"],
        palette={k: list(v) for k, v in RECOMMENDED_DEFAULTS["palette"].items()},
    )


# --------------------------------------------------------------------------- #
# Localization (Russian / Kazakh / English)
# --------------------------------------------------------------------------- #

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "app_title": "Air Draw — Рисование жестами рук",
        "settings": "Настройки",
        "save_and_close": "Сохранить и закрыть",
        "cancel": "Отмена",
        "reset_recommended": "Сбросить до рекомендуемых",
        "reset_confirm": "Вы уверены, что хотите сбросить все настройки до рекомендуемых (пороги 17, FPS 30)?",
        "tab_general": "Основные",
        "tab_camera": "Камера и FPS",
        "tab_gestures": "Жесты и пороги",
        "tab_palette": "Палитра (0-9)",
        "language_select": "Язык интерфейса:",
        "processor_header": "Аппаратный процессор системы:",
        "processor_load": "Загрузка CPU:",
        "startup_shortcuts_toggle": "Показывать окно горячих клавиш при запуске",
        "camera_index_label": "Индекс камеры:",
        "camera_resolution_label": "Разрешение камеры:",
        "fps_limit_label": "Ограничение FPS (рекомендуется 30):",
        "model_complexity_label": "Сложность модели MediaPipe:",
        "model_fast": "0 — Быстрая (рекомендуется)",
        "model_accurate": "1 — Точная",
        "detection_scale_label": "Масштаб кадра детекции:",
        "detection_conf_label": "Порог детекции (confidence):",
        "tracking_conf_label": "Порог отслеживания (tracking):",
        "draw_pinch_label": "Порог пинча DRAW_PINCH_RATIO (рекомендуется 17):",
        "clear_pinch_label": "Порог пинча CLEAR_PINCH_RATIO (рекомендуется 17):",
        "smoothing_label": "Окно сглаживания координат (кадры):",
        "show_skeleton_label": "Отображать скелет руки и точки",
        "show_debug_label": "Отображать отладочные значения на экране",
        "palette_description": "Настройте цвет для каждой цифры (0-9). Нажатие цифры переключает цвет кисти:",
        "key_num_label": "Клавиша {num}:",
        "pick_color_btn": "Выбрать цвет...",
        "shortcuts_title": "Горячие клавиши и управление",
        "shortcuts_header": "Управление приложением Air Draw",
        "gestures_section": "Управление жестами:",
        "gesture_draw_desc": "- Пинч большим и указательным пальцем — Рисование",
        "gesture_clear_desc": "- Пинч большим и средним пальцем — Очистить холст",
        "keys_section": "Клавиатура (работает на ЛЮБОЙ раскладке):",
        "key_exit": "- Q / Й — Выход из приложения",
        "key_clear": "- C / С — Очистить холст",
        "key_save": "- S / Ы — Сохранить рисунок в PNG",
        "key_colors": "- 0-9 — Выбрать цвет из палитры",
        "key_thickness": "- + / - — Толщина кисти (+/-)",
        "key_debug": "- D / В — Вкл/выкл отладку (пороги и дистанции)",
        "key_skeleton": "- H / Р — Вкл/выкл скелет руки",
        "key_pinch_adjust": "- [ / ] (Х / Ъ) — Уменьшить/увеличить порог очистки",
        "key_settings": "- O / Щ — Открыть настройки",
        "dont_show_again": "Больше не показывать при запуске",
        "btn_ok": "Понятно",
        "btn_clear_canvas": "Очистить холст",
        "btn_save_canvas": "Сохранить PNG",
        "btn_open_settings": "Настройки",
        "btn_open_shortcuts": "Горячие клавиши",
        "status_draw": "РИСОВАНИЕ",
        "status_clear": "ОЧИСТКА",
        "status_idle": "ОЖИДАНИЕ",
        "status_saved": "Рисунок сохранён: {filename}",
        "status_cleared": "Холст очищен",
        "thickness_label": "Толщина: {val}",
        "current_color_label": "Цвет: {key}",
        "gesture_label": "ЖЕСТ: {name}",
        "processor_details": "Архитектура: {arch} | Ядер: {logical} ({physical} физ.)",
        "recommended_suffix": "(Рекомендуется)",
        "fps_unlimited": "Без ограничений",
        "pick_color_title": "Выбор цвета для клавиши {key}",
    },
    "kk": {
        "app_title": "Air Draw — Қол қимылдарымен сурет салу",
        "settings": "Баптаулар",
        "save_and_close": "Сақтау және жабу",
        "cancel": "Болдырмау",
        "reset_recommended": "Ұсынылғанға қайтару",
        "reset_confirm": "Барлық баптауларды ұсынылған мәндерге қайтарғыңыз келе ме (шегі 17, FPS 30)?",
        "tab_general": "Жалпы",
        "tab_camera": "Камера және FPS",
        "tab_gestures": "Қимылдар мен шектер",
        "tab_palette": "Палитра (0-9)",
        "language_select": "Интерфейс тілі:",
        "processor_header": "Жүйенің аппараттық процессоры:",
        "processor_load": "CPU жүктемесі:",
        "startup_shortcuts_toggle": "Іске қосқанда пернелер тіркесімін көрсету",
        "camera_index_label": "Камера индексі:",
        "camera_resolution_label": "Камера ажыратымдылығы:",
        "fps_limit_label": "FPS шектеуі (ұсынылатыны 30):",
        "model_complexity_label": "MediaPipe моделінің күрделілігі:",
        "model_fast": "0 — Жылдам (ұсынылады)",
        "model_accurate": "1 — Дәл",
        "detection_scale_label": "Анықтау кадрының масштабы:",
        "detection_conf_label": "Анықтау сенімділігі (confidence):",
        "tracking_conf_label": "Қадағалау сенімділігі (tracking):",
        "draw_pinch_label": "Сурет салу пинч шегі DRAW_PINCH_RATIO (ұсынылғаны 17):",
        "clear_pinch_label": "Тазалау пинч шегі CLEAR_PINCH_RATIO (ұсынылғаны 17):",
        "smoothing_label": "Координаттарды тегістеу терезесі (кадр):",
        "show_skeleton_label": "Қол қаңқасы мен нүктелерін көрсету",
        "show_debug_label": "Экранда реттеу мәндерін көрсету",
        "palette_description": "Әрбір санға (0-9) түс орнатыңыз. Санды басу қылқалам түсін ауыстырады:",
        "key_num_label": "{num} пернесі:",
        "pick_color_btn": "Түсті таңдау...",
        "shortcuts_title": "Пернелер тіркесімдері және басқару",
        "shortcuts_header": "Air Draw қолданбасын басқару",
        "gestures_section": "Қимылмен басқару:",
        "gesture_draw_desc": "- Бас бармақ пен сұқ саусақты түйістіру — Сурет салу",
        "gesture_clear_desc": "- Бас бармақ пен ортаңғы саусақты түйістіру — Кенепті тазалау",
        "keys_section": "Пернетақта (КЕЗ КЕЛГЕН тілде жұмыс істейді):",
        "key_exit": "- Q / Й — Қолданбадан шығу",
        "key_clear": "- C / С — Кенепті тазалау",
        "key_save": "- S / Ы — PNG форматында суретті сақтау",
        "key_colors": "- 0-9 — Палитрадан түс таңдау",
        "key_thickness": "- + / - — Қылқалам қалыңдығы (+/-)",
        "key_debug": "- D / В — Реттеу мәліметтерін көрсету/жасыру",
        "key_skeleton": "- H / Р — Қол қаңқасын қосу/өшіру",
        "key_pinch_adjust": "- [ / ] (Х / Ъ) — Тазалау шегін азайту/көбейту",
        "key_settings": "- O / Щ — Баптауларды ашу",
        "dont_show_again": "Іске қосқанда қайта көрсетпеу",
        "btn_ok": "Түсінікті",
        "btn_clear_canvas": "Кенепті тазалау",
        "btn_save_canvas": "PNG сақтау",
        "btn_open_settings": "Баптаулар",
        "btn_open_shortcuts": "Пернелер",
        "status_draw": "СУРЕТ САЛУ",
        "status_clear": "ТАЗАЛАУ",
        "status_idle": "КҮТУ",
        "status_saved": "Сурет сақталды: {filename}",
        "status_cleared": "Кенеп тазаланды",
        "thickness_label": "Қалыңдық: {val}",
        "current_color_label": "Түс: {key}",
        "gesture_label": "ҚИМЫЛ: {name}",
        "processor_details": "Архитектура: {arch} | Ядро: {logical} ({physical} физ.)",
        "recommended_suffix": "(Ұсынылады)",
        "fps_unlimited": "Шектеусіз",
        "pick_color_title": "{key} пернесі үшін түс таңдау",
    },
    "en": {
        "app_title": "Air Draw — Hand Gestures Air Canvas",
        "settings": "Settings",
        "save_and_close": "Save & Close",
        "cancel": "Cancel",
        "reset_recommended": "Reset to Recommended",
        "reset_confirm": "Are you sure you want to reset all settings to recommended defaults (pinch 17, FPS 30)?",
        "tab_general": "General",
        "tab_camera": "Camera & FPS",
        "tab_gestures": "Gestures & Thresholds",
        "tab_palette": "Palette (0-9)",
        "language_select": "Interface Language:",
        "processor_header": "System Hardware Processor:",
        "processor_load": "CPU Usage:",
        "startup_shortcuts_toggle": "Show shortcuts window on application startup",
        "camera_index_label": "Camera Index:",
        "camera_resolution_label": "Camera Resolution:",
        "fps_limit_label": "FPS Limit (recommended: 30):",
        "model_complexity_label": "MediaPipe Model Complexity:",
        "model_fast": "0 — Fast (recommended)",
        "model_accurate": "1 — Accurate",
        "detection_scale_label": "Detection Frame Scale:",
        "detection_conf_label": "Detection Confidence:",
        "tracking_conf_label": "Tracking Confidence:",
        "draw_pinch_label": "Draw Pinch Ratio (DRAW_PINCH_RATIO, rec. 17):",
        "clear_pinch_label": "Clear Pinch Ratio (CLEAR_PINCH_RATIO, rec. 17):",
        "smoothing_label": "Coordinate Smoothing Window (frames):",
        "show_skeleton_label": "Render hand skeleton and landmarks",
        "show_debug_label": "Show debug distances and thresholds overlay",
        "palette_description": "Set a custom color for each digit key (0-9). Pressing the digit selects the brush color:",
        "key_num_label": "Key {num}:",
        "pick_color_btn": "Choose Color...",
        "shortcuts_title": "Keyboard Shortcuts & Controls",
        "shortcuts_header": "Air Draw Controls Guide",
        "gestures_section": "Hand Gestures Controls:",
        "gesture_draw_desc": "- Thumb + Index finger pinch — Draw",
        "gesture_clear_desc": "- Thumb + Middle finger pinch — Clear canvas",
        "keys_section": "Keyboard (Works on ANY layout):",
        "key_exit": "- Q / Й — Quit application",
        "key_clear": "- C / С — Clear canvas",
        "key_save": "- S / Ы — Save drawing to PNG",
        "key_colors": "- 0-9 — Select color from palette",
        "key_thickness": "- + / - — Adjust brush thickness",
        "key_debug": "- D / В — Toggle debug info overlay",
        "key_skeleton": "- H / Р — Toggle hand skeleton",
        "key_pinch_adjust": "- [ / ] (Х / Ъ) — Decrease/increase clear threshold",
        "key_settings": "- O / Щ — Open settings",
        "dont_show_again": "Do not show again on startup",
        "btn_ok": "Got it",
        "btn_clear_canvas": "Clear Canvas",
        "btn_save_canvas": "Save PNG",
        "btn_open_settings": "Settings",
        "btn_open_shortcuts": "Shortcuts",
        "status_draw": "DRAWING",
        "status_clear": "CLEARING",
        "status_idle": "IDLE",
        "status_saved": "Drawing saved: {filename}",
        "status_cleared": "Canvas cleared",
        "thickness_label": "Thickness: {val}",
        "current_color_label": "Color: {key}",
        "gesture_label": "GESTURE: {name}",
        "processor_details": "Architecture: {arch} | Cores: {logical} ({physical} physical)",
        "recommended_suffix": "(Recommended)",
        "fps_unlimited": "Unlimited",
        "pick_color_title": "Choose color for key {key}",
    },
}


def tr(msg_key: str, lang: str = "ru", **kwargs: Any) -> str:
    """Return the translated string for ``msg_key``, falling back to Russian."""
    pack = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    msg = pack.get(msg_key, TRANSLATIONS["ru"].get(msg_key, msg_key))
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg
