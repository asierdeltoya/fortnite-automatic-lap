"""Run towards a point on the map without knowing the mouse sensitivity.

The game only tells us where we are when the map is read. Between two reads the
character runs forward for a while; the direction it actually moved tells us how
the last turn went. From that feedback the navigator learns two numbers while it
works:

* `counts_per_deg` - how many mouse counts turn the view by one degree.
* `speed` - island fractions walked per second.

With those it can aim at the next waypoint, choose a run time and correct on the
next map read. It never needs a compass, a fixed sensitivity or a radar.

All positions are island fractions (see `geometry`). `on_fix()` is called once
per map read and returns what to do until the next one.
"""

from dataclasses import dataclass

from geometry import bearing, clamp, distance, nearest, wrap_deg


@dataclass(frozen = True)
class Decision:
    turn: int = 0          # mouse counts, + turns right
    run_s: float = 0.0     # seconds to hold W
    arrived: bool = False
    stuck: bool = False
    note: str = ""


class Navigator:
    def __init__(
        self,
        arrive = 0.012,
        min_leg = 0.5,
        max_leg = 20.0,
        counts_per_deg = 30.0,
        speed = 0.01,
    ):
        self.arrive = arrive
        self.min_leg = min_leg
        self.max_leg = max_leg
        self.counts_per_deg = counts_per_deg
        self.speed = speed
        self.route = []
        self.target = None
        self.legs = 0
        self.stuck_fixes = 0
        self._last = None
        self._last_time = None
        self._prev_bearing = None
        self._dx = 0
        self._probe = 40
        self._need_probe = True

    def set_route(self, route):
        """Start a new list of waypoints (nearest first)."""
        self.route = [tuple(p) for p in route]
        self.target = None
        self._last = None
        self._last_time = None
        self._prev_bearing = None
        self._dx = 0
        self._probe = 40
        self._need_probe = True
        self.stuck_fixes = 0

    def advance(self):
        """The current waypoint is done; is there another one?"""
        if self.target in self.route:
            self.route.remove(self.target)
        self.target = None
        self._last = None
        self._last_time = None
        self._prev_bearing = None
        self._dx = 0
        self.stuck_fixes = 0
        return bool(self.route)

    def skip(self):
        """Give up on the current waypoint (unreachable) and take the next."""
        if self.target in self.route:
            self.route.remove(self.target)
        self.target = None
        self._last = None
        self._last_time = None
        self._prev_bearing = None
        self._dx = 0
        self.stuck_fixes = 0
        return bool(self.route)

    def on_fix(self, position, now):
        if not self.route:
            return Decision(note = "no route")
        if self.target is None:
            self.target = self.route[nearest(position, self.route)[0]]

        if self._last is None:
            self._last, self._last_time = position, now
            return self._aim(position, note = "first leg")

        elapsed = max(0.05, now - self._last_time)
        moved = distance(self._last, position)
        if moved < 0.0015:
            self.stuck_fixes += 1
            self._last_time = now
            return Decision(stuck = True, note = "no movement between map reads")

        observed = bearing(self._last, position)
        self._learn_turn(observed)
        self._prev_bearing = observed
        self.speed = clamp(0.65 * self.speed + 0.35 * (moved / elapsed), 0.002, 0.4)
        self._last, self._last_time = position, now
        self.stuck_fixes = 0

        if distance(position, self.target) <= self.arrive:
            return Decision(arrived = True, note = "arrived")
        return self._aim(position, note = "leg")

    def _learn_turn(self, observed):
        if not self._dx or self._prev_bearing is None:
            return
        changed = wrap_deg(observed - self._prev_bearing)
        if self._need_probe:
            # First turn is a probe: keep changing its size until the picture
            # moves by an amount that can be measured without wrapping.
            if 0.5 <= abs(changed) <= 45.0:
                measured = abs(self._dx) / abs(changed)
                if 0.4 <= measured <= 500.0:
                    self.counts_per_deg = measured
                    self._need_probe = False
            elif abs(changed) > 45.0:
                self._probe = max(10, int(self._probe / 2))
            else:
                self._probe = min(4000, int(self._probe * 4))
            return
        if abs(changed) < 0.5 or abs(self._dx) < 20:
            return
        measured = abs(self._dx) / abs(changed)
        if 0.4 <= measured <= 500.0:
            self.counts_per_deg = clamp(0.9 * self.counts_per_deg + 0.1 * measured, 0.4, 500.0)

    def _aim(self, position, note):
        desired = bearing(position, self.target)
        current = self._prev_bearing if self._prev_bearing is not None else desired
        error = wrap_deg(desired - current)
        if self._need_probe:
            self._dx = int(self._probe)
        else:
            self._dx = int(clamp(error, -90.0, 90.0) * self.counts_per_deg)
        remaining = distance(position, self.target)
        run = clamp(remaining / max(self.speed, 0.0015) * 0.7, self.min_leg, self.max_leg)
        self.legs += 1
        return Decision(turn = self._dx, run_s = run, note = note)

    def target_distance(self, position):
        return None if self.target is None else distance(position, self.target)
