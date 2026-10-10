"""
Air Draw configuration: default settings, JSON persistence and
UI localization (Russian, Kazakh, English).

Defaults live in one place (``AppConfig``). Loading tolerates hand-edited or
older files: unknown keys are ignored, invalid values fall back to defaults and
numeric values are clamped to ``RANGES``.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sys
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger("air_draw.config")

CONFIG_FILE_NAME = "config.json"
# Overrides the data folder. The test suite uses it so runs never touch real settings.
DATA_DIR_ENV = "AIR_DRAW_DATA_DIR"

LANGUAGES = ("ru", "kk", "en")
# Palette keys in toolbar order: digits 1-9, then 0
PALETTE_KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")

# Digit key -> brush color in BGR order (OpenCV)
DEFAULT_PALETTE_BGR: Dict[str, List[int]] = {
    "1": [0, 255, 0],       # Green
    "2": [0, 0, 255],       # Red
    "3": [255, 0, 0],       # Blue
    "4": [0, 255, 255],     # Yellow
    "5": [255, 255, 0],     # Cyan
    "6": [255, 0, 255],     # Magenta
    "7": [0, 165, 255],     # Orange
    "8": [255, 255, 255],   # White
    "9": [30, 30, 30],      # Near black
    "0": [128, 128, 128],   # Gray
}

# Allowed ranges for numeric settings. Stored and command-line values are clamped
# to these, and the settings dialog uses the same limits, so the UI never changes
# a stored value silently.
RANGES: Dict[str, Tuple[float, float]] = {
    "width": (160, 3840),
    "height": (120, 2160),
    "camera_index": (0, 99),
    "fps_limit": (0, 120),
    "model_complexity": (0, 1),
    "detection_confidence": (0.1, 1.0),
    "tracking_confidence": (0.1, 1.0),
    "detection_scale": (0.25, 1.0),
    "draw_pinch_ratio": (5, 50),
    "clear_pinch_ratio": (5, 50),
    "smoothing_min_cutoff": (0.1, 10.0),
    "smoothing_beta": (0.0, 1.0),
    "thickness": (1, 30),
}


def _default_palette() -> Dict[str, List[int]]:
    return {k: list(v) for k, v in DEFAULT_PALETTE_BGR.items()}


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
    # One Euro filter on the fingertip: lower cutoff = smoother but laggier;
    # higher beta = less lag during fast movement
    smoothing_min_cutoff: float = 1.0
    smoothing_beta: float = 0.03
    thickness: int = 5
    current_color_key: str = "1"
    show_skeleton: bool = True
    show_debug: bool = False
    palette: Dict[str, List[int]] = field(default_factory=_default_palette)
    # Settings overridden by command-line flags for this run only; never written to disk
    session_overrides: FrozenSet[str] = field(
        default_factory=frozenset, compare=False, repr=False, metadata={"persist": False}
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


_DEFAULTS = AppConfig()


def get_recommended_config() -> AppConfig:
    """Return a fresh config with the recommended settings (pinch 17, 30 FPS)."""
    return AppConfig()


def clamp_setting(name: str, value: Any) -> Any:
    """Clamp a numeric setting to ``RANGES``; other values pass through unchanged."""
    if name not in RANGES:
        return value
    low, high = RANGES[name]
    clamped = min(max(value, low), high)
    return int(round(clamped)) if isinstance(getattr(_DEFAULTS, name), int) else float(clamped)


def apply_overrides(cfg: AppConfig, overrides: Dict[str, Any]) -> None:
    """Apply run-only settings (command-line flags). They are not written back to disk."""
    for name, value in overrides.items():
        setattr(cfg, name, clamp_setting(name, value))
    cfg.session_overrides = cfg.session_overrides | frozenset(overrides)


# --------------------------------------------------------------------------- #
# Paths and persistence
# --------------------------------------------------------------------------- #

def get_data_dir() -> Path:
    """
    Folder for ``config.json`` and saved drawings.

    Honors ``AIR_DRAW_DATA_DIR`` if set. When running from source this is the
    project root. In a PyInstaller build the bundle is unpacked to a temporary
    (or read-only) location, so user data goes to ``~/AirDraw`` instead.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        data_dir = Path(override).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    if getattr(sys, "frozen", False):
        data_dir = Path.home() / "AirDraw"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """Path to ``config.json`` inside the data folder."""
    return get_data_dir() / CONFIG_FILE_NAME


def _read_json_object(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data


def _is_bgr(color: Any) -> bool:
    return (
        isinstance(color, list)
        and len(color) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in color)
    )


def _sanitize_palette(raw: Any) -> Dict[str, List[int]]:
    """Merge a stored palette over the defaults, dropping invalid entries."""
    palette = _default_palette()
    if not isinstance(raw, dict):
        return palette
    for key, color in raw.items():
        if key not in PALETTE_KEYS:
            logger.warning("Ignoring palette entry for unknown key %r", key)
        elif _is_bgr(color):
            palette[key] = list(color)
        else:
            logger.warning("Ignoring invalid palette color for key %s: %r", key, color)
    return palette


def _coerce(name: str, value: Any, default: Any) -> Any:
    """Convert a JSON value to the type of its default. Raises ``ValueError`` if impossible."""
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError("expected true or false")
    if isinstance(default, (int, float)):
        if isinstance(value, bool):
            raise ValueError("expected a number")
        number = float(value)  # Accepts "12" and 12.0, raises for other input
        if not math.isfinite(number):
            raise ValueError("expected a finite number")
        return clamp_setting(name, number)
    if isinstance(default, str):
        if not isinstance(value, str):
            raise ValueError("expected a string")
        return value
    raise ValueError(f"unsupported setting type for {name}")


def config_from_dict(raw: Dict[str, Any]) -> AppConfig:
    """Build a config from parsed JSON, tolerating unknown keys and invalid values."""
    defaults = get_recommended_config()
    values: Dict[str, Any] = {}
    for f in fields(AppConfig):
        if not f.metadata.get("persist", True) or f.name == "palette" or f.name not in raw:
            continue
        try:
            values[f.name] = _coerce(f.name, raw[f.name], getattr(defaults, f.name))
        except (TypeError, ValueError) as e:
            logger.warning("Ignoring invalid value for %s (%r): %s", f.name, raw[f.name], e)

    cfg = replace(defaults, **values)
    cfg.palette = _sanitize_palette(raw.get("palette"))
    if cfg.language not in LANGUAGES:
        cfg.language = "ru"
    if cfg.current_color_key not in PALETTE_KEYS:
        cfg.current_color_key = "1"
    return cfg


def _keep_broken_copy(path: Path) -> Optional[Path]:
    """Copy an unreadable config aside so the user can recover it."""
    backup = path.with_name(f"{path.stem}.broken{path.suffix}")
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError as e:
        logger.error("Could not keep a copy of the broken config: %s", e)
        return None


def _read_stored_values(path: Path) -> Dict[str, Any]:
    try:
        return _read_json_object(path)
    except (OSError, ValueError):
        return {}


def load_config() -> AppConfig:
    """Load settings from disk, creating the file with defaults if missing."""
    config_file = get_config_path()
    if not config_file.exists():
        logger.info("Config file not found, using recommended settings.")
        cfg = get_recommended_config()
        save_config(cfg)
        return cfg

    try:
        raw = _read_json_object(config_file)
    except (OSError, ValueError) as e:
        backup = _keep_broken_copy(config_file)
        logger.error("Failed to read config (%s). Using recommended settings; copy kept at %s", e, backup)
        return get_recommended_config()
    return config_from_dict(raw)


def save_config(cfg: AppConfig) -> None:
    """Write settings to ``config.json`` atomically (temp file, then replace)."""
    config_file = get_config_path()
    data = {f.name: getattr(cfg, f.name) for f in fields(AppConfig) if f.metadata.get("persist", True)}

    # Settings overridden for this run keep whatever is already stored on disk
    if cfg.session_overrides:
        stored = _read_stored_values(config_file)
        for name in cfg.session_overrides:
            if name in stored:
                data[name] = stored[name]
            else:
                data.pop(name, None)

    tmp_file = config_file.with_name(config_file.name + ".tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, config_file)
        logger.info("Config saved to %s", config_file)
    except OSError as e:
        logger.error("Failed to save config: %s", e)


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
        "reset_confirm": "Сбросить все настройки до рекомендуемых (пороги 17, FPS 30)? Язык интерфейса не изменится.",
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
        "smoothing_cutoff_label": "Сглаживание: частота среза (меньше = плавнее):",
        "smoothing_beta_label": "Сглаживание: отклик на быстрые движения (beta):",
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
        "status_save_failed": "Не удалось сохранить рисунок: {filename}",
        "status_cleared": "Холст очищен",
        "thickness_label": "Толщина: {val}",
        "current_color_label": "Цвет: {key}",
        "gesture_label": "ЖЕСТ: {name}",
        "processor_details": "Архитектура: {arch} | Ядер: {logical} ({physical} физ.)",
        "recommended_suffix": "(Рекомендуется)",
        "fps_unlimited": "Без ограничений",
        "pick_color_title": "Выбор цвета для клавиши {key}",
        "res_hd": "HD",
        "res_fhd": "Full HD",
        "bar_proc": "{brand} ({cores} яд.)",
        "bar_load": "Загрузка CPU: {load}%",
        "bar_fps": "FPS: {fps}{target}",
        "camera_error": "Камера {index} не найдена или занята. Выберите другую в настройках (O).",
    },
    "kk": {
        "app_title": "Air Draw — Қол қимылдарымен сурет салу",
        "settings": "Баптаулар",
        "save_and_close": "Сақтау және жабу",
        "cancel": "Болдырмау",
        "reset_recommended": "Ұсынылғанға қайтару",
        "reset_confirm": "Барлық баптауларды ұсынылған мәндерге қайтарғыңыз келе ме (шегі 17, FPS 30)? Интерфейс тілі өзгермейді.",
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
        "smoothing_cutoff_label": "Тегістеу: кесу жиілігі (кіші = жұмсағыр):",
        "smoothing_beta_label": "Тегістеу: жылдам қимылға жауап (beta):",
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
        "status_save_failed": "Суретті сақтау мүмкін болмады: {filename}",
        "status_cleared": "Кенеп тазаланды",
        "thickness_label": "Қалыңдық: {val}",
        "current_color_label": "Түс: {key}",
        "gesture_label": "ҚИМЫЛ: {name}",
        "processor_details": "Архитектура: {arch} | Ядро: {logical} ({physical} физ.)",
        "recommended_suffix": "(Ұсынылады)",
        "fps_unlimited": "Шектеусіз",
        "pick_color_title": "{key} пернесі үшін түс таңдау",
        "res_hd": "HD",
        "res_fhd": "Full HD",
        "bar_proc": "{brand} ({cores} ядро)",
        "bar_load": "CPU жүктемесі: {load}%",
        "bar_fps": "FPS: {fps}{target}",
        "camera_error": "{index}-камера табылмады немесе бос емес. Баптаулардан (O) басқасын таңдаңыз.",
    },
    "en": {
        "app_title": "Air Draw — Hand Gestures Air Canvas",
        "settings": "Settings",
        "save_and_close": "Save & Close",
        "cancel": "Cancel",
        "reset_recommended": "Reset to Recommended",
        "reset_confirm": "Reset all settings to recommended defaults (pinch 17, FPS 30)? The interface language will not change.",
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
        "smoothing_cutoff_label": "Smoothing cutoff (lower = smoother):",
        "smoothing_beta_label": "Smoothing responsiveness (beta):",
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
        "status_save_failed": "Could not save drawing: {filename}",
        "status_cleared": "Canvas cleared",
        "thickness_label": "Thickness: {val}",
        "current_color_label": "Color: {key}",
        "gesture_label": "GESTURE: {name}",
        "processor_details": "Architecture: {arch} | Cores: {logical} ({physical} physical)",
        "recommended_suffix": "(Recommended)",
        "fps_unlimited": "Unlimited",
        "pick_color_title": "Choose color for key {key}",
        "res_hd": "HD",
        "res_fhd": "Full HD",
        "bar_proc": "{brand} ({cores} cores)",
        "bar_load": "CPU load: {load}%",
        "bar_fps": "FPS: {fps}{target}",
        "camera_error": "Camera {index} not found or busy. Pick another one in Settings (O).",
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
