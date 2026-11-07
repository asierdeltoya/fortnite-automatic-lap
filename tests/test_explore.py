import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from detect import Match
from explore import Explorer, Phase

W, H = 1920, 1080


def chest(x = 960, y = 540, w = 120, h = 80, score = 0.9):
    return Match(x, y, w, h, score)


def test_starts_patrolling_forward():
    explorer = Explorer()
    action = explorer.step(100.0, W, H)
    assert action.walk and action.look == 0 and not action.interact
    assert explorer.phase is Phase.SEARCH


def test_patrol_turns_the_camera_after_walking():
    explorer = Explorer()
    explorer.step(100.0, W, H)
    action = explorer.step(102.7, W, H)
    assert not action.walk and action.look > 0


def test_seek_turns_towards_a_chest_on_the_right():
    explorer = Explorer()
    action = explorer.step(100.0, W, H, chest(x = 1400))
    assert explorer.phase is Phase.SEEK
    assert action.look > 0
    assert not action.walk  # still far from the centre


def test_seek_walks_when_the_chest_is_in_front():
    explorer = Explorer()
    action = explorer.step(100.0, W, H, chest(x = 1000))
    assert action.walk
    assert abs(action.look) < W * 0.05


def test_reaching_a_chest_presses_e_only_once():
    explorer = Explorer()
    big_close_chest = chest(w = 500, h = 320)
    action = explorer.step(100.0, W, H, big_close_chest)
    assert action.interact and explorer.looted == 1
    assert explorer.phase is Phase.LOOT

    action = explorer.step(100.5, W, H, big_close_chest)
    assert not action.interact and action.note == "looting"

    action = explorer.step(101.2, W, H, big_close_chest)
    assert not action.interact
    assert explorer.phase is Phase.SEARCH


def test_lost_chest_returns_to_patrol():
    explorer = Explorer()
    explorer.step(100.0, W, H, chest(x = 1400))
    action = explorer.step(100.5, W, H, None, None)
    assert not action.walk and "lost" in action.note
    action = explorer.step(102.5, W, H, None, None)
    assert action.walk and explorer.phase is Phase.SEARCH


def test_walking_into_a_wall_jumps_and_strafes():
    explorer = Explorer()
    explorer.step(100.0, W, H)
    explorer.step(100.6, W, H, None, False)   # starts the "still" timer
    explorer.step(101.1, W, H, None, False)   # 0.5 s still
    action = explorer.step(101.8, W, H, None, False)  # 1.2 s still
    assert action.jump and action.strafe != 0
    assert explorer.phase is Phase.UNSTUCK

    action = explorer.step(102.0, W, H, None, False)
    assert action.strafe != 0 and not action.jump  # keeps strafing for a moment

    action = explorer.step(103.0, W, H, None, True)
    assert explorer.phase is Phase.SEARCH


def test_a_moving_picture_never_counts_as_stuck():
    explorer = Explorer()
    explorer.step(100.0, W, H)
    for t in (100.6, 101.2, 101.8, 102.4):
        action = explorer.step(t, W, H, None, True)
        assert not action.jump


def test_chest_behind_a_wall_is_abandoned_after_the_timeout():
    explorer = Explorer()
    explorer.step(100.0, W, H, chest(x = 400))
    action = explorer.step(101.0, W, H, None, None)
    assert not action.interact
    action = explorer.step(103.0, W, H, None, None)
    assert explorer.phase is Phase.SEARCH


def test_look_is_limited_so_the_camera_does_not_spin():
    explorer = Explorer()
    action = explorer.step(100.0, W, H, chest(x = 1900, y = 400, w = 40, h = 20))
    assert abs(action.look) <= W * 0.13


def test_an_opened_chest_is_ignored_while_walking_away():
    explorer = Explorer()
    big = chest(w=500, h=320)
    explorer.step(100.0, W, H, big)          # opens it
    explorer.step(101.2, W, H, big)          # walks away, cooldown starts
    action = explorer.step(101.4, W, H, big)
    assert not action.interact
    assert explorer.phase is Phase.SEARCH
    action = explorer.step(104.2, W, H, big)  # cooldown over: a real new chest
    assert action.interact
