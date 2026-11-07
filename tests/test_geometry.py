import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import geometry


def test_cardinal_bearings():
    assert abs(geometry.bearing((0, 0), (0, -1))) < 1e-6
    assert abs(geometry.bearing((0, 0), (1, 0)) - 90) < 1e-6
    assert abs(abs(geometry.bearing((0, 0), (0, 1))) - 180) < 1e-6
    assert abs(abs(geometry.bearing((0, 0), (-1, 0))) - 90) < 1e-6


def test_wrap_deg():
    assert geometry.wrap_deg(370) == 10
    assert geometry.wrap_deg(-190) == 170
    assert geometry.wrap_deg(180) == -180


def test_distance_and_nearest():
    assert abs(geometry.distance((0, 0), (3, 4)) - 5) < 1e-9
    points = [(0.9, 0.9), (0.2, 0.2), (0.5, 0.6)]
    index, distance = geometry.nearest((0.1, 0.1), points)
    assert index == 1 and abs(distance - 0.1414) < 0.001


def test_ordered_route_visits_every_point_once():
    start, points = (0.0, 0.0), [(0.8, 0.8), (0.2, 0.1), (0.4, 0.3), (0.9, 0.1)]
    route = geometry.ordered_route(start, points)
    assert sorted(route) == sorted(points)
    assert route[0] == (0.2, 0.1)


def test_step_follows_the_heading():
    north = geometry.step((0.5, 0.5), 0, 0.1)
    east = geometry.step((0.5, 0.5), 90, 0.1)
    assert abs(north[0] - 0.5) < 1e-9 and abs(north[1] - 0.4) < 1e-9
    assert abs(east[0] - 0.6) < 1e-9 and abs(east[1] - 0.5) < 1e-9
