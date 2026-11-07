import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import chest_mode
from chest_mode import ChestMode, CState
from config import Settings
from detect import Match
from explore import Action

FRAME = np.zeros((1080, 1920, 3), np.uint8)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class FakeController:
    def __init__(self):
        self.clicks = []
        self.presses = []
        self.moves = []
        self.looks = []
        self.released = False

    def click(self, x, y):
        self.clicks.append((x, y))
        return True

    def press(self, key):
        self.presses.append(key)

    def move(self, walk = False, strafe = 0):
        self.moves.append((walk, strafe))

    def look(self, dx, dy = 0):
        self.looks.append(dx)

    def release_all(self):
        self.released = True


class FakeFinder:
    def __init__(self):
        self.result = None

    def detect(self, frame):
        return self.result


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(chest_mode.time, "monotonic", clock)
    keyboard = {"play": False, "menu_return": False, "menu_btn": False}
    templates = {key: object() for key in ("play", "menu_return", "menu_btn", "claim", "claim_single", "popup")}

    def fake_find(frame, template, threshold, scales):
        for key, value in templates.items():
            if template is value and keyboard.get(key):
                return (100, 200, 0.99), 0.99
        return None, 0.0

    monkeypatch.setattr(chest_mode, "find_template", fake_find)
    finder = FakeFinder()
    monkeypatch.setattr(chest_mode.ChestFinder, "from_assets", classmethod(lambda cls, threshold = 0.55: finder))

    ctrl = FakeController()
    mode = ChestMode(Settings(), templates, ctrl)
    mode.start()
    return mode, ctrl, finder, keyboard, clock


def step(mode):
    return mode.step(FRAME)


def test_clicks_play_in_the_lobby_and_starts_the_match(env):
    mode, ctrl, finder, keyboard, clock = env
    keyboard["play"] = True
    result = step(mode)
    assert result.state is CState.PLAY
    assert result.clicked and ctrl.clicks
    assert mode._t_match == clock.t


def test_play_button_after_a_match_returns_to_the_lobby(env):
    mode, ctrl, finder, keyboard, clock = env
    keyboard["play"] = True
    step(mode)                      # lobby -> play
    clock.advance(15)
    assert step(mode).state is CState.PLAY   # grace period still running
    clock.advance(5)
    assert step(mode).state is CState.LOBBY
    assert mode.loops == 1
    assert ctrl.released


def test_opening_a_chest_is_counted_and_pressed(env):
    mode, ctrl, finder, keyboard, clock = env
    keyboard["play"] = True
    step(mode)
    keyboard["play"] = False
    finder.result = Match(960, 540, 500, 320, 0.9)
    mode.explorer.step = lambda now, w, h, detection = None, moved = None: Action(interact = True)
    result = step(mode)
    assert mode.chests == 1
    assert result.chests == 1
    assert "e" in ctrl.presses


def test_it_returns_to_the_lobby_after_enough_chests(env):
    mode, ctrl, finder, keyboard, clock = env
    keyboard["play"] = True
    step(mode)
    keyboard["play"] = False
    mode._match_chests = chest_mode.MAX_CHESTS_PER_MATCH
    result = step(mode)
    assert result.state is CState.EXIT
    assert "esc" in ctrl.presses


def test_cannot_leave_a_normal_match_so_it_keeps_exploring(env):
    mode, ctrl, finder, keyboard, clock = env
    mode.state = CState.EXIT
    mode._esc_tries = chest_mode.ESC_MAX_TRIES
    mode._t_esc = clock.t - chest_mode.EXIT_GIVE_UP_S - 1
    result = step(mode)
    assert result.state is CState.PLAY
    assert mode._match_chests == 0


def test_menu_return_click_leaves_the_match(env):
    mode, ctrl, finder, keyboard, clock = env
    mode.state = CState.EXIT
    keyboard["menu_return"] = True
    result = step(mode)
    assert result.state is CState.LOBBY
    assert mode.loops == 1
    assert ctrl.clicks


def test_stop_releases_the_movement_keys(env):
    mode, ctrl, finder, keyboard, clock = env
    mode.stop()
    assert ctrl.released
    assert mode.state is CState.LOBBY
