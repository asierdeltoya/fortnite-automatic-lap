import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
import vision
from config import Settings


def test_missing_file_gives_defaults(tmp_path):
    assert config.load_settings(str(tmp_path / "nope.json")) == Settings()


def test_roundtrip(tmp_path):
    path = str(tmp_path / "cfg.json")
    s = Settings(threshold=0.9, lang="es", mode="B", wait_b=120.0, afk_enabled=False,
                 afk_interval=20.0, afk_hold=2.5, monitor_index=2)
    config.save_settings(s, path)
    loaded = config.load_settings(path)
    for k in config.SAVED_FIELDS:
        assert getattr(loaded, k) == getattr(s, k), k


def test_bad_values_are_ignored_or_clamped(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({
        "threshold": 5, "lang": "xx", "mode": "Z", "wait_b": "lots",
        "afk_enabled": 1, "afk_hold": 0.0, "unknown": 3,
    }), encoding="utf-8")
    s = config.load_settings(str(path))
    assert s.threshold == 0.95
    assert s.lang == Settings.lang and s.mode == Settings.mode
    assert s.wait_b == Settings.wait_b
    assert s.afk_enabled is Settings.afk_enabled
    assert s.afk_hold == 0.5


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("{not json", encoding="utf-8")
    assert config.load_settings(str(path)) == Settings()


def _scene(btn, pos=(300, 200)):
    frame = np.full((600, 900, 3), 30, dtype=np.uint8)
    h, w = btn.shape[:2]
    frame[pos[1]:pos[1] + h, pos[0]:pos[0] + w] = btn
    return frame


def test_big_template_is_found_repeatedly_and_absent_frames_stay_empty():
    btn = np.random.default_rng(3).integers(0, 255, size=(80, 200, 3), dtype=np.uint8)
    scales = Settings().scales
    frame = _scene(btn, (100, 400))
    for _ in range(6):
        m, _ = vision.find_template(frame, btn, 0.82, scales)
        assert m is not None and abs(m[0] - 200) <= 1 and abs(m[1] - 440) <= 1
    m, score = vision.find_template(np.full((600, 900, 3), 30, np.uint8), btn, 0.82, scales)
    assert m is None and score < 0.82


def test_cheap_gate_still_finds_a_rescaled_big_template():
    btn = np.random.default_rng(4).integers(0, 255, size=(80, 200, 3), dtype=np.uint8)
    scaled = cv2.resize(btn, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_LINEAR)
    m, _ = vision.find_template(_scene(scaled), btn, 0.82, Settings().scales)
    assert m is not None


def test_small_templates_are_never_gated():
    btn = np.random.default_rng(5).integers(0, 255, size=(30, 30, 3), dtype=np.uint8)
    m, _ = vision.find_template(_scene(btn), btn, 0.9, Settings().scales)
    assert m is not None


def test_nan_values_in_the_config_are_ignored(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text('{"threshold": NaN, "chest_threshold": Infinity}', encoding="utf-8")
    s = config.load_settings(str(path))
    assert s.threshold == Settings.threshold
    assert s.chest_threshold == Settings.chest_threshold
