"""Where to look and where to walk when hunting chests.

`Explorer` is pure decision logic: it receives what the camera saw and returns
what the character should do next. It never touches the mouse, the keyboard or
the clock, so the whole patrol / approach / loot cycle is unit tested.

One call per camera frame (roughly every 150-250 ms). Actions are relative and
resolution independent: distances are fractions of the frame width.
"""

from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    SEARCH = "SEARCH"
    SEEK = "SEEK"
    LOOT = "LOOT"
    UNSTUCK = "UNSTUCK"


@dataclass(frozen = True)
class Action:
    look: int = 0          # horizontal mouse counts, + turns right
    walk: bool = False     # hold W
    strafe: int = 0        # -1 hold A, +1 hold D
    jump: bool = False
    interact: bool = False  # press E
    note: str = ""


class Explorer:
    """Patrol the map, walk to a chest and open it."""

    # patrol schedule: (kind, seconds, turn as a fraction of the frame width)
    PATROL = (
        ("walk", 2.6, 0.0),
        ("look", 0.35, 0.09),
        ("walk", 2.0, 0.0),
        ("look", 0.35, 0.09),
        ("walk", 2.6, 0.0),
        ("look", 0.35, -0.18),
    )

    def __init__(
        self,
        seek_gain = 0.55,
        seek_walk_dx = 0.18,
        reach_height = 0.20,
        reach_dx = 0.13,
        seek_timeout = 1.6,
        loot_time = 1.0,
        loot_cooldown = 2.5,
        stuck_after = 1.0,
        unstuck_time = 0.9,
    ):
        self.seek_gain = seek_gain
        self.seek_walk_dx = seek_walk_dx
        self.reach_height = reach_height
        self.reach_dx = reach_dx
        self.seek_timeout = seek_timeout
        self.loot_time = loot_time
        self.loot_cooldown = loot_cooldown
        self.stuck_after = stuck_after
        self.unstuck_time = unstuck_time
        self.reset()

    def reset(self):
        self.phase = Phase.SEARCH
        self.looted = 0
        self.target = None
        self._patrol_step = 0
        self._t_phase = None
        self._t_seen = None
        self._t_still = None
        self._unstuck_side = 1
        self._unstick_turn = 1
        self._ignore_until = 0.0

    def step(self, now, width, height, detection = None, moved = None):
        """Decide the next action.

        `detection` is the chest found in this frame (or None) and `moved` says
        whether the picture changed since the previous frame (None when the
        character was not walking, so "stuck" is not judged).
        """
        if self._t_phase is None:
            self._t_phase = now

        if detection is not None and now < self._ignore_until:
            detection = None

        if self.phase is Phase.LOOT:
            if now - self._t_phase < self.loot_time:
                return Action(note = "looting")
            # An opened chest stays visible for a moment; ignore it while the
            # character walks away so it is not opened (and counted) twice.
            self._ignore_until = now + self.loot_cooldown
            self._search(now)
            return self._patrol(now, width, moved)

        if detection is not None:
            self.target = detection
            self._t_seen = now
            if self._reached(detection, width, height):
                self.phase = Phase.LOOT
                self._t_phase = now
                self.looted += 1
                return Action(interact = True, note = "chest reached: press E")
            self.phase = Phase.SEEK
            if self._stuck(now, moved, True):
                return self._unstick(now, width)
            dx = detection.x - width / 2
            look = int(max(-0.12 * width, min(0.12 * width, dx * self.seek_gain)))
            walk = abs(dx) <= self.seek_walk_dx * width
            return Action(look = look, walk = walk, note = "walking to chest")

        if self.phase is Phase.SEEK:
            if self._t_seen is not None and now - self._t_seen < self.seek_timeout:
                return Action(look = 0, walk = False, note = "chest lost: looking")
            self._search(now)
            return self._patrol(now, width, moved)

        if self.phase is Phase.UNSTUCK:
            if now - self._t_phase < self.unstuck_time:
                return Action(walk = True, strafe = self._unstuck_side, note = "unstuck")
            self._search(now)
            return self._patrol(now, width, moved)

        return self._patrol(now, width, moved)

    def _search(self, now):
        self.phase = Phase.SEARCH
        self.target = None
        self._t_phase = now
        self._patrol_step = 0
        self._t_still = None

    def _patrol(self, now, width, moved):
        schedule = self.PATROL
        while now - self._t_phase >= schedule[self._patrol_step][1]:
            self._t_phase += schedule[self._patrol_step][1]
            self._patrol_step = (self._patrol_step + 1) % len(schedule)

        kind, _, turn = schedule[self._patrol_step]
        if kind == "look":
            return Action(look = round(turn * width), note = "looking around")
        if self._stuck(now, moved, True):
            return self._unstick(now, width)
        return Action(walk = True, note = "patrolling")

    def _reached(self, detection, width, height):
        dx = abs(detection.x - width / 2)
        return detection.h >= self.reach_height * height and dx <= self.reach_dx * width

    def _stuck(self, now, moved, walking):
        if not walking or moved is None:
            self._t_still = None
            return False
        if moved:
            self._t_still = None
            return False
        if self._t_still is None:
            self._t_still = now
            return False
        return now - self._t_still >= self.stuck_after

    def _unstick(self, now, width):
        self.phase = Phase.UNSTUCK
        self._t_phase = now
        self._t_still = None
        self._unstuck_side = -self._unstuck_side
        self._unstick_turn = -self._unstick_turn
        return Action(
            look = round(0.08 * width * self._unstick_turn),
            walk = True,
            strafe = self._unstuck_side,
            jump = True,
            note = "blocked: jump and strafe",
        )
