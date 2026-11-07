import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from geometry import step
from navigation import Navigator


class World:
    """A stand-in for the game with an unknown mouse sensitivity and speed."""

    def __init__(self, position, counts_per_deg = 25.0, speed = 0.01, heading = 0.0):
        self.position = position
        self.counts_per_deg = counts_per_deg
        self.speed = speed
        self.heading = heading

    def turn(self, counts):
        self.heading = (self.heading + counts / self.counts_per_deg) % 360.0

    def run(self, seconds):
        self.position = step(self.position, self.heading, self.speed * seconds)


def run_to(nav, world, target, max_legs = 80):
    nav.set_route([target])
    decision = nav.on_fix(world.position, 0.0)
    now = 0.0
    for _ in range(max_legs):
        world.turn(decision.turn)
        world.run(decision.run_s)
        now += decision.run_s + 0.5
        decision = nav.on_fix(world.position, now)
        if decision.arrived:
            return True
        assert not decision.stuck
    return False


@pytest.mark.parametrize("target", [(0.8, 0.2), (0.2, 0.8), (0.9, 0.9), (0.1, 0.1), (0.5, 0.9)])
def test_it_reaches_a_target_in_any_direction(target):
    world = World((0.5, 0.5))
    assert run_to(Navigator(), world, target)


@pytest.mark.parametrize("counts_per_deg", [3.0, 6.0, 25.0, 90.0, 300.0])
def test_it_learns_the_mouse_sensitivity_while_walking(counts_per_deg):
    world = World((0.5, 0.5), counts_per_deg = counts_per_deg)
    nav = Navigator()
    assert run_to(nav, world, (0.8, 0.2))
    assert abs(nav.counts_per_deg - counts_per_deg) / counts_per_deg < 0.2
    assert nav.legs <= 10


def test_it_works_at_different_walking_speeds():
    for speed in (0.003, 0.02, 0.06):
        world = World((0.5, 0.5), speed = speed)
        assert run_to(Navigator(), world, (0.15, 0.85))


def test_it_notices_that_it_cannot_move():
    nav = Navigator()
    nav.set_route([(0.9, 0.5), (0.1, 0.5)])
    nav.on_fix((0.5, 0.5), 0.0)
    assert nav.on_fix((0.5, 0.5), 5.0).stuck
    nav.on_fix((0.5, 0.5), 10.0)
    nav.on_fix((0.5, 0.5), 15.0)
    assert nav.stuck_fixes >= 3
    assert nav.skip()
    assert nav.target is None


def test_advance_takes_the_next_waypoint():
    nav = Navigator()
    nav.set_route([(0.2, 0.2), (0.8, 0.8)])
    nav.on_fix((0.2, 0.2), 0.0)
    assert nav.target == (0.2, 0.2)
    assert nav.advance()
    nav.on_fix((0.2, 0.2), 1.0)
    assert nav.target == (0.8, 0.8)
    assert not nav.advance()


def test_an_empty_route_is_harmless():
    nav = Navigator()
    nav.set_route([])
    decision = nav.on_fix((0.5, 0.5), 0.0)
    assert decision.note == "no route" and not decision.arrived
