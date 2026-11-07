import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import farm
from chest_mode import CState
from config import Settings
from detect import Match
from farm import FState, FarmMode

FRAME = np.zeros((1080, 1920, 3), np.uint8)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeController:
    def __init__(self):
        self.clicks = []
        self.presses = []
        self.moves = []
        self.looks = []
        self.held = set()
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


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(farm.time, "monotonic", clock)
    ctrl = FakeController()
    mode = FarmMode(Settings(), {}, ctrl)
    keyboard = {"play": False}
    mode._find = lambda key, frame: (((100, 100, 0.99), 0.99) if keyboard.get(key) else (None, 0.0))
    mode.finder.detect = lambda frame: None
    mode.ready = True
    mode.route_ref = [(0.8, 0.5)]
    mode.start()
    return mode, ctrl, keyboard, clock


def test_without_the_map_files_it_falls_back_to_roaming():
    mode = FarmMode(Settings(), {}, FakeController())
    assert mode.ready is False
    assert "chest_map.png" in mode.startup_note
    result = mode.step(FRAME)
    assert result.state is CState.LOBBY


def test_bus_jump_dive_and_landing(env):
    mode, ctrl, keyboard, clock = env
    keyboard["play"] = True
    result = mode.step(FRAME)
    assert result.state is FState.BUS and ctrl.clicks

    clock.advance(Settings().bus_hold + 0.1)
    result = mode.step(FRAME)
    assert result.state is FState.DIVE and "space" in ctrl.presses

    clock.advance(Settings().dive_s + 0.1)
    result = mode.step(FRAME)
    assert result.state is FState.MAP and mode._map_purpose == "land"

    mode._read_map = lambda frame: (0.2, 0.5)
    clock.advance(farm.MAP_WAIT_S + 0.1)
    assert mode.step(FRAME).state is FState.WAIT

    clock.advance(farm.LAND_RETRY_S + 0.1)
    assert mode.step(FRAME).state is FState.MAP

    clock.advance(farm.MAP_WAIT_S + 0.1)
    result = mode.step(FRAME)
    assert result.state is FState.RUN
    assert ctrl.moves and ctrl.moves[-1][0] is True


def test_arriving_at_a_spot_starts_looting(env):
    mode, ctrl, keyboard, clock = env
    mode.state = FState.RUN
    mode._run_until = clock.t - 1
    mode._read_map = lambda frame: (0.8, 0.5)
    assert mode.step(FRAME).state is FState.MAP

    clock.advance(farm.MAP_WAIT_S + 0.1)
    assert mode.step(FRAME).state is FState.RUN      # first leg, no fix yet

    mode._read_map = lambda frame: (0.8, 0.5)
    mode.nav._last = (0.4, 0.5)
    mode.nav._last_time = clock.t - 5
    mode._run_until = clock.t - 1
    assert mode.step(FRAME).state is FState.MAP
    clock.advance(farm.MAP_WAIT_S + 0.1)
    result = mode.step(FRAME)
    assert result.state is FState.LOOT


def test_a_chest_in_sight_is_looted_while_running(env):
    mode, ctrl, keyboard, clock = env
    mode.state = FState.RUN
    mode._run_until = clock.t + 10
    mode.finder.detect = lambda frame: Match(960, 600, 500, 320, 0.9)
    result = mode.step(FRAME)
    assert result.state is FState.LOOT


def test_it_returns_to_the_lobby_when_play_reappears(env):
    mode, ctrl, keyboard, clock = env
    mode.state = FState.RUN
    mode._match_start = clock.t - 60
    mode._run_until = clock.t + 10
    keyboard["play"] = True
    assert mode.step(FRAME).state is FState.RUN      # grace period starts
    clock.advance(farm.LOBBY_GRACE + 0.1)
    result = mode.step(FRAME)
    assert result.state is FState.LOBBY
    assert mode.loops == 1


def test_stop_releases_everything(env):
    mode, ctrl, keyboard, clock = env
    mode.stop()
    assert ctrl.released
