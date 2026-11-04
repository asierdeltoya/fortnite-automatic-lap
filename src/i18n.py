"""Interface text in every supported UI language.

Each entry maps a key to its text in Japanese (the original), English and
Spanish. Use t("key", name=value) to get the text in the current language.
"""

import ctypes
import locale
import sys

UI_LANGS = {
    "ja": "日本語",
    "en": "English",
    "es": "Español",
}
DEFAULT_UI_LANG = "en"

STRINGS = {
    # --- main controls ---
    "start": {"ja": "開始", "en": "Start", "es": "Iniciar"},
    "stop": {"ja": "停止", "en": "Stop", "es": "Detener"},
    "stopping": {"ja": "停止中…", "en": "Stopping…", "es": "Deteniendo…"},
    "topmost": {"ja": "最前面", "en": "Always on top", "es": "Siempre visible"},
    "hotkey_hint": {"ja": "F8: 開始 / 停止", "en": "F8: start / stop", "es": "F8: iniciar / detener"},
    "ui_lang": {"ja": "表示言語", "en": "Interface language", "es": "Idioma de la interfaz"},
    "game_lang": {"ja": "ゲーム言語", "en": "Game language", "es": "Idioma del juego"},
    "monitor": {"ja": "画面", "en": "Screen", "es": "Pantalla"},
    "only_foreground": {
        "ja": "Fortnite が前面にない時は一時停止",
        "en": "Pause when Fortnite is not in the foreground",
        "es": "Pausar si Fortnite no está en primer plano",
    },
    "mode_A": {
        "ja": "A: 通常ループ (続行→スキップ→ロビーへ)",
        "en": "A: Normal loop (Continue → Skip → Lobby)",
        "es": "A: Bucle normal (Continuar → Saltar → Lobby)",
    },
    "mode_B": {
        "ja": "B: 待機島で待ってEscから退出",
        "en": "B: Wait on the pre-match island, then leave with Esc",
        "es": "B: Esperar en la isla de espera y salir con Esc",
    },
    "wait_b_before": {"ja": "B: 待機島で", "en": "B: on the island, wait", "es": "B: en la isla de espera, esperar"},
    "wait_b_after": {"ja": "秒待ってから Esc", "en": "s, then press Esc", "es": "s y pulsar Esc"},
    "afk": {
        "ja": "マッチ中 WASD ランダム長押し",
        "en": "Hold random WASD keys during the match",
        "es": "Pulsar WASD al azar durante la partida",
    },
    "afk_every": {"ja": "間隔", "en": "Every", "es": "Cada"},
    "afk_hold": {"ja": "秒ごと / 長押し", "en": "s / hold for", "es": "s / mantener"},
    "seconds": {"ja": "秒", "en": "s", "es": "s"},
    "threshold": {
        "ja": "しきい値 (一部のボタンは固定値)",
        "en": "Detection threshold (some buttons use a fixed one)",
        "es": "Umbral de detección (algunos botones usan uno fijo)",
    },
    "crop": {"ja": "画像を切り抜く", "en": "Crop image", "es": "Recortar imagen"},

    # --- status lines ---
    "status": {
        "ja": "{state}   ·   一致度 {score:.2f}",
        "en": "{state}   ·   match {score:.2f}",
        "es": "{state}   ·   coincidencia {score:.2f}",
    },
    "stats_idle": {"ja": "マッチ数: {loops}", "en": "Matches: {loops}", "es": "Partidas: {loops}"},
    "stats": {
        "ja": "マッチ数: {loops}   経過時間: {elapsed}{rate}",
        "en": "Matches: {loops}   Time: {elapsed}{rate}",
        "es": "Partidas: {loops}   Tiempo: {elapsed}{rate}",
    },
    "rate": {"ja": "   ({rate:.1f}/時)", "en": "   ({rate:.1f}/h)", "es": "   ({rate:.1f}/h)"},

    # --- states ---
    "state_IDLE": {"ja": "停止中", "en": "Stopped", "es": "Parado"},
    "state_SEARCHING_PLAY": {"ja": "「プレイ」を探し中", "en": "Looking for «Play»", "es": "Buscando «Jugar»"},
    "state_IN_MATCH": {"ja": "マッチ中", "en": "In match", "es": "En partida"},
    "state_SKIPPING_RESULT": {"ja": "結果をスキップ中", "en": "Skipping results", "es": "Saltando resultados"},
    "state_RETURNING_LOBBY": {"ja": "ロビーへ戻り中", "en": "Returning to lobby", "es": "Volviendo al lobby"},
    "state_B:LOBBY": {"ja": "B: ロビー", "en": "B: in the lobby", "es": "B: en el lobby"},
    "state_B:LOADING": {"ja": "B: 島を読み込み中", "en": "B: loading island", "es": "B: cargando isla"},
    "state_B:WAITING": {"ja": "B: 待機島で待機中", "en": "B: waiting on the island", "es": "B: esperando en la isla"},
    "state_B:MENU": {"ja": "B: メニューから退出中", "en": "B: leaving via the menu", "es": "B: saliendo por el menú"},
    "state_PAUSED": {
        "ja": "一時停止 (Fortnite が前面にない)",
        "en": "Paused (Fortnite is not in front)",
        "es": "En pausa (Fortnite no está delante)",
    },

    # --- log messages ---
    "log_started": {"ja": "開始しました", "en": "started", "es": "iniciado"},
    "log_stopped": {"ja": "停止しました", "en": "stopped", "es": "detenido"},
    "log_paused": {
        "ja": "一時停止: Fortnite が前面にありません",
        "en": "paused: Fortnite is not in the foreground",
        "es": "en pausa: Fortnite no está en primer plano",
    },
    "log_resumed": {"ja": "再開しました", "en": "resumed", "es": "reanudado"},
    "log_ui_lang": {"ja": "表示言語: {name}", "en": "interface language: {name}", "es": "idioma de la interfaz: {name}"},
    "log_game_lang": {"ja": "ゲーム言語: {name}", "en": "game language: {name}", "es": "idioma del juego: {name}"},
    "log_mode": {"ja": "モード: {name}", "en": "mode: {name}", "es": "modo: {name}"},
    "log_monitor": {"ja": "画面: {name}", "en": "screen: {name}", "es": "pantalla: {name}"},
    "log_missing": {"ja": "画像がありません: {name}", "en": "image missing: {name}", "es": "falta la imagen: {name}"},
    "log_error": {"ja": "エラー: {error}", "en": "error: {error}", "es": "error: {error}"},
    "log_save_error": {
        "ja": "設定を保存できません: {error}",
        "en": "could not save settings: {error}",
        "es": "no se pudo guardar la configuración: {error}",
    },
    "log_saved": {"ja": "保存しました: {path}", "en": "saved {path}", "es": "guardado {path}"},
    "log_crop_cancelled": {"ja": "切り抜きをキャンセル", "en": "crop cancelled", "es": "recorte cancelado"},
    "log_crop_error": {"ja": "切り抜きエラー: {error}", "en": "crop error: {error}", "es": "error al recortar: {error}"},
    "log_crop_too_big": {
        "ja": "選択範囲が大きすぎます。ボタンの周りだけを囲んでください",
        "en": "selection too large - drag only around the button",
        "es": "selección demasiado grande: rodea solo el botón",
    },
    "log_hotkey_error": {"ja": "F8 キーのエラー: {error}", "en": "F8 hotkey error: {error}", "es": "error con la tecla F8: {error}"},
}

_current = DEFAULT_UI_LANG


def set_lang(code):
    global _current
    _current = code if code in UI_LANGS else DEFAULT_UI_LANG


def get_lang():
    return _current


def t(key, **kwargs):
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry[DEFAULT_UI_LANG]
    return text.format(**kwargs) if kwargs else text


# Windows primary language ids -> language code.
_PRIMARY_LANG = {0x11: "ja", 0x09: "en", 0x0A: "es", 0x16: "pt", 0x19: "ru"}


def system_lang():
    """Two-letter code of the Windows display language ("" if unknown)."""
    if sys.platform == "win32":
        try:
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = _PRIMARY_LANG.get(langid & 0x3FF)
            if code:
                return code
        except Exception:
            pass
    try:
        name = locale.getlocale()[0] or ""
    except Exception:
        name = ""
    name = name.lower()
    for code, words in {"ja": ("ja", "japanese"), "en": ("en", "english"), "es": ("es", "spanish"),
                        "pt": ("pt", "portuguese"), "ru": ("ru", "russian")}.items():
        if name.startswith(words):
            return code
    return ""
