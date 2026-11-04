import json
import os
import sys
from dataclasses import dataclass

TEMPLATE_NAMES = {
    "play": "play_btn.png",
    "continue": "continue_btn.png",
    "skip": "skip_btn.png",
    "return_lobby": "return_lobby_btn.png",

    "claim": "claim_btn.png",
    "claim_single": "claim_single_btn.png",
    "popup": "popup_btn.png",

    "hud": "hud_btn.png",
    "menu_btn": "menu_btn.png",
    "menu_return": "menu_return_btn.png",
}

MODES = {"A": "A: Bucle normal (Continuar → Saltar → Lobby)", "B": "B: Esperar en la isla de espera y salir con Esc"}

OPTIONAL_TEMPLATES = {"popup", "claim", "claim_single"}

LANGS = {
    "ja": "Japonés",
    "en": "English",
    "es": "Español (beta)",
    "pt": "Português (beta)",
    "ru": "Русский (beta)",
}
PLATE_LANGS = ("es", "pt", "ru")

LANG_INDEPENDENT = {"continue", "skip", "hud", "menu_btn", "menu_return"}

PLATES = {
    "play": {"roi": (0.0, 0.70, 0.40, 1.0), "threshold": 0.92},
    "return_lobby": {"roi": (0.55, 0.30, 1.0, 0.52), "threshold": 0.80},
    "claim": {"roi": (0.503, 0.80, 1.0, 1.0), "threshold": 0.93},

    "hud": {"roi": (0.0, 0.85, 0.30, 1.0), "threshold": 0.90},
    "menu_btn": {"roi": (0.70, 0.0, 1.0, 0.18), "threshold": 0.85},
    "menu_return": {"roi": (0.55, 0.0, 1.0, 0.36), "threshold": 0.85},
}

PLATE_UNUSED = {"claim_single"}

def plate_filename(key):
    return TEMPLATE_NAMES[key].replace(".png", "_plate.png")

def uses_template(key, lang):
    return not (lang in PLATE_LANGS and key in PLATE_UNUSED)

def template_filename(key, lang="ja"):
    name = TEMPLATE_NAMES[key]
    if key in LANG_INDEPENDENT:
        return name
    if lang in PLATE_LANGS and key in PLATES:
        return plate_filename(key)
    if lang == "ja" or lang in PLATE_LANGS:
        return name
    return name.replace(".png", f"_{lang}.png")

def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def assets_dir():
    return os.path.join(base_dir(), "assets")

def bundled_assets_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", base_dir()), "assets_default")
    return assets_dir()

def external_template_path(key, lang="ja"):
    return os.path.join(assets_dir(), template_filename(key, lang))

def template_path(key, lang="ja"):
    ext = external_template_path(key, lang)
    if os.path.isfile(ext):
        return ext
    bundled = os.path.join(bundled_assets_dir(), template_filename(key, lang))
    return bundled if os.path.isfile(bundled) else ext

@dataclass
class Settings:
    threshold: float = 0.82
    lang: str = "es"
    mode: str = "A"
    wait_b: float = 90.0
    poll_interval: float = 2.0

    scales: tuple = tuple(round(0.6 + 0.1 * i, 2) for i in range(9))
    jitter_px: int = 5
    delay_min: float = 0.15
    delay_max: float = 0.45
    click_cooldown: float = 3.0
    monitor_index: int = 1
    only_foreground: bool = True

    afk_enabled: bool = True
    afk_interval: float = 10.0
    afk_hold: float = 3.0
    afk_keys: tuple = ("w", "a", "s", "d")

SAVED_FIELDS = (
    "threshold", "lang", "mode", "wait_b",
    "afk_enabled", "afk_interval", "afk_hold",
    "monitor_index", "only_foreground",
)

LIMITS = {
    "threshold": (0.5, 0.95),
    "wait_b": (10.0, 600.0),
    "afk_interval": (1.0, 600.0),
    "afk_hold": (0.5, 30.0),
    "monitor_index": (1, 16),
}

def settings_path():
    return os.path.join(base_dir(), "pk-auto-config.json")

def load_settings(path=None):
    s = Settings()
    try:
        with open(path or settings_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return s
    if not isinstance(data, dict):
        return s
    for k in SAVED_FIELDS:
        if k not in data:
            continue
        default, v = getattr(s, k), data[k]
        if isinstance(default, bool):
            if isinstance(v, bool):
                setattr(s, k, v)
        elif isinstance(default, (int, float)):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = LIMITS.get(k, (v, v))
                setattr(s, k, type(default)(min(max(v, lo), hi)))
        elif isinstance(v, str):
            setattr(s, k, v)
    if s.lang not in LANGS:
        s.lang = Settings.lang
    if s.mode not in MODES:
        s.mode = Settings.mode
    return s

def save_settings(s, path=None):
    path = path or settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: getattr(s, k) for k in SAVED_FIELDS}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
