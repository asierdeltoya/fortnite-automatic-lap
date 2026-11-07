"""Geometry for map navigation.

Positions are fractions of the island (0..1 on both axes) so they do not
depend on the resolution or on where the map is drawn on screen. Bearings use
degrees, 0 = north (up on the map), 90 = east (right), growing clockwise.
"""

import math


def wrap_deg(angle):
    """Normalise an angle to -180..180."""
    return (angle + 180.0) % 360.0 - 180.0


def bearing(a, b):
    """Compass bearing from point `a` to point `b` (screen axes, y down)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.degrees(math.atan2(dx, -dy))


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def direction(heading, length = 1.0):
    r = math.radians(heading)
    return (math.sin(r) * length, -math.cos(r) * length)


def step(point, heading, length):
    dx, dy = direction(heading, length)
    return (point[0] + dx, point[1] + dy)


def nearest(point, points):
    """Index and distance of the closest point (None if the list is empty)."""
    best_index, best_distance = None, None
    for index, candidate in enumerate(points):
        d = distance(point, candidate)
        if best_distance is None or d < best_distance:
            best_index, best_distance = index, d
    return best_index, best_distance


def ordered_route(start, points):
    """Visit every point once, always going to the nearest one left."""
    remaining = list(points)
    route = []
    position = start
    while remaining:
        index, _ = nearest(position, remaining)
        position = remaining.pop(index)
        route.append(position)
    return route


def clamp(value, low, high):
    return max(low, min(high, value))
