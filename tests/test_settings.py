import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
import i18n
import vision
from config import Settings


def test_missing_file_gives_defaults(tmp_path):
    assert config.load_settings(str(tmp_path / "nope.json")) == config.default_settings()


def test_first_launch_follows_system_language(monkeypatch):
    for sys_lang, ui, game in (("ja", "ja", "ja"), ("es", "es", "es"), ("pt", "en", "pt"), ("", "en", "en")):
        monkeypatch.setattr(i18n, "system_lang", lambda: sys_lang)
        s = config.default_settings()
        assert (s.ui_lang, s.lang) == (ui, game), sys_lang


def test_roundtrip(tmp_path):
    path = str(tmp_path / "cfg.json")
    s = Settings(threshold=0.9, lang="en", ui_lang="es", mode="B", wait_b=120.0, afk_enabled=False,
                 afk_interval=20.0, afk_hold=2.5, monitor_index=2, only_foreground=False)
    config.save_settings(s, path)
    loaded = config.load_settings(path)
    for k in config.SAVED_FIELDS:
        assert getattr(loaded, k) == getattr(s, k), k


def test_bad_values_are_ignored_or_clamped(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({
        "threshold": 5, "lang": "xx", "ui_lang": "zz", "mode": "Z", "wait_b": "lots",
        "afk_enabled": 1, "afk_hold": 0.0, "unknown": 3,
    }), encoding="utf-8")
    s = config.load_settings(str(path))
    assert s.threshold == 0.95
    d = config.default_settings()
    assert s.lang == d.lang and s.ui_lang == d.ui_lang and s.mode == d.mode
    assert s.wait_b == Settings.wait_b
    assert s.afk_enabled is Settings.afk_enabled
    assert s.afk_hold == 0.5


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("{not json", encoding="utf-8")
    assert config.load_settings(str(path)) == config.default_settings()


def _scene(btn, pos=(300, 200)):
    frame = np.full((600, 900, 3), 30, dtype=np.uint8)
    h, w = btn.shape[:2]
    frame[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = btn
    return frame


def test_found_scale_is_remembered_and_still_matches():
    btn = np.random.default_rng(3).integers(0, 255, size=(40, 120, 3), dtype=np.uint8)
    scales = Settings().scales
    m, _ = vision.find_template(_scene(btn), btn, 0.82, scales)
    assert m is not None
    assert vision._prep_template(btn)["scale"] == 1.0
    for _ in range(vision.FULL_SCAN_EVERY + 2):
        m, _ = vision.find_template(_scene(btn, (100, 400)), btn, 0.82, scales)
        assert m is not None and abs(m[0] - 160) <= 1 and abs(m[1] - 420) <= 1
    m, _ = vision.find_template(np.full((600, 900, 3), 30, np.uint8), btn, 0.82, scales)
    assert m is None


def test_every_text_exists_in_every_ui_language():
    for key, entry in i18n.STRINGS.items():
        assert set(entry) == set(i18n.UI_LANGS), key
        assert all(text.strip() for text in entry.values()), key


def test_placeholders_match_across_languages():
    import string
    for key, entry in i18n.STRINGS.items():
        fields = {code: {f for _, f, _, _ in string.Formatter().parse(text) if f} for code, text in entry.items()}
        assert len({frozenset(v) for v in fields.values()}) == 1, (key, fields)


def test_t_uses_current_language_and_falls_back():
    try:
        i18n.set_lang("ja")
        assert i18n.t("start") == "開始"
        i18n.set_lang("es")
        assert i18n.t("log_mode", name="A") == "modo: A"
        i18n.set_lang("xx")
        assert i18n.get_lang() == i18n.DEFAULT_UI_LANG
        assert i18n.t("no_such_key") == "no_such_key"
    finally:
        i18n.set_lang(i18n.DEFAULT_UI_LANG)


def test_every_state_and_mode_has_a_label():
    from state_machine import State
    for st in State:
        assert f"state_{st.value}" in i18n.STRINGS, st
    for code in config.MODES:
        assert f"mode_{code}" in i18n.STRINGS, code
