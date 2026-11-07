"""Mode C, fully automatic: bus -> landing -> map route -> chests -> again.

The mission reads the in-game map with `mapvision`, walks the route that came
from the annotated reference map (`assets/chest_map.png`) with the map-feedback
navigator, and loots with the same chest detector and `Explorer` the roaming
mode uses. Without the reference map or the player-arrow template it falls back
to the plain roaming mode, so mode C always does something useful.

Nothing here reads game memory or the network: the screen, the mouse and the
keyboard are the whole interface.
"""

import time
from dataclasses import dataclass
from enum import Enum

from chest import ChestFinder
from chest_mode import CState, ChestMode
from detect import frame_diff
from explore import Explorer
from geometry import distance
from mapvision import MapAligner, PlayerFinder, island_box, load_reference, normalize
from navigation import Navigator
from state_machine import POPUP_KEYS
from vision import Plate, find_plate, find_template

LOBBY_GRACE = 3.0
MIN_MATCH_S = 15.0

MAP_WAIT_S = 0.9
MAP_TIMEOUT_S = 4.0
LAND_RETRY_S = 2.0
LAND_STABLE = 0.0025
LAND_TIMEOUT_S = 90.0

OVERLAY_EVERY = 4
OVERLAY_KEYS = ("continue", "skip", "return_lobby", "claim", "claim_single", "popup")

MATCH_LIMIT_S = 15 * 60.0
MOVED_THRESHOLD = 0.004
STUCK_AFTER_S = 1.2
ESC_RETRY_S = 8.0
ESC_MAX_TRIES = 3
EXIT_GIVE_UP_S = 6.0


class FState(Enum):
    LOBBY = "C:LOBBY"
    BUS = "C:BUS"
    DIVE = "C:DIVE"
    MAP = "C:MAP"
    WAIT = "C:WAIT"
    RUN = "C:RUN"
    LOOT = "C:LOOT"
    EXIT = "C:EXIT"


@dataclass
class FarmResult:
    state: FState
    chests: int = 0
    loops: int = 0
    score: float = 0.0
    clicked: bool = False
    note: str = ""


class FarmMode:
    def __init__(self, settings, templates, controller):
        self.s = settings
        self.templates = templates
        self.ctrl = controller
        self.roam = ChestMode(settings, templates, controller)
        self.finder = ChestFinder.from_assets(getattr(settings, "chest_threshold", 0.55))
        self.explorer = Explorer()
        self.nav = Navigator()
        self.player = PlayerFinder(templates.get("map_player"))
        self.route_ref = []
        self._load_assets()

        self.state = FState.LOBBY
        self.chests = 0
        self.loops = 0
        self._t = 0.0
        self._match_start = 0.0
        self._map_t = 0.0
        self._map_purpose = ""
        self._map_fix = None
        self._land_start = 0.0
        self._wait_until = 0.0
        self._wait_next = ""
        self._run_until = 0.0
        self._loot_until = 0.0
        self._prev = None
        self._stuck_since = None
        self._play_since = None
        self._calls = 0
        self._esc_tries = 0
        self._t_esc = 0.0

    def _load_assets(self):
        try:
            image, box, chests = load_reference()
        except Exception:
            image, box, chests = None, None, []
        self.reference = image
        self.ref_box = box
        self.ref_size = (image.shape[1], image.shape[0]) if image is not None else (0, 0)
        self.aligner = MapAligner(image) if image is not None else None
        self.route_ref = list(chests) if chests and len(chests) >= 3 else []
        self.ready = bool(self.route_ref and self.player.ready)
        if self.ready:
            self.startup_note = f"farm ready: {len(self.route_ref)} chests on the reference map"
        elif not self.route_ref:
            self.startup_note = "farm needs assets/chest_map.png with chest icons: roaming mode"
        else:
            self.startup_note = "farm needs assets/map_player.png (crop your map arrow): roaming mode"

    # --- lifecycle -----------------------------------------------------
    def start(self):
        self.state = FState.LOBBY
        self.chests = 0
        self.loops = 0
        self._prev = None
        self._calls = 0
        self._play_since = None
        self._esc_tries = 0
        self.explorer.reset()
        self.nav.set_route(self.route_ref)
        self.roam.start()

    def stop(self):
        self.ctrl.release_all()
        self.explorer.reset()
        self._prev = None
        self.state = FState.LOBBY
        self.roam.stop()

    # --- main step -----------------------------------------------------
    def step(self, frame, ox = 0, oy = 0):
        if not self.ready:
            result = self.roam.step(frame, ox, oy)
            self.chests, self.loops = self.roam.chests, self.roam.loops
            return result

        now = time.monotonic()
        play, play_score = self._find("play", frame)
        self._calls += 1
        state = self.state

        if state is FState.LOBBY:
            return self._lobby(now, frame, ox, oy, play, play_score)
        if state is FState.BUS:
            return self._bus(now)
        if state is FState.DIVE:
            return self._dive(now)
        if state is FState.MAP:
            return self._map(now, frame)
        if state is FState.WAIT:
            return self._wait_step(now)
        if state is FState.RUN:
            return self._run(now, frame, ox, oy, play)
        if state is FState.LOOT:
            return self._loot(now, frame, ox, oy, play)
        return self._exit(now, frame, ox, oy, play)

    def _lobby(self, now, frame, ox, oy, play, play_score):
        if self._click(play, ox, oy):
            self.state, self._t = FState.BUS, now
            self._match_start = now
            self._play_since = None
            self._esc_tries = 0
            return FarmResult(FState.BUS, self.chests, self.loops, play_score, True, "clicked play: on the bus")
        for key in POPUP_KEYS:
            found, score = self._find(key, frame)
            if self._click(found, ox, oy):
                return FarmResult(FState.LOBBY, self.chests, self.loops, score, True, f"clicked {key} (stay)")
        return FarmResult(FState.LOBBY, self.chests, self.loops, play_score, False, "waiting play")

    def _bus(self, now):
        left = self.s.bus_hold - (now - self._t)
        if left > 0:
            return FarmResult(FState.BUS, self.chests, self.loops, 0.0, False, f"on the bus: jumping in {left:.0f}s")
        self.ctrl.release_all()
        self.ctrl.press("space")
        self.state, self._t = FState.DIVE, now
        return FarmResult(FState.DIVE, self.chests, self.loops, 0.0, True, "jumped from the bus")

    def _dive(self, now):
        self.ctrl.move(walk = True)
        if now - self._t < self.s.dive_s:
            return FarmResult(FState.DIVE, self.chests, self.loops, 0.0, False, "diving")
        self.ctrl.release_all()
        self._land_start = now
        self._map_fix = None
        self._open_map(now, "land")
        return FarmResult(FState.MAP, self.chests, self.loops, 0.0, True, "opening the map to find where we landed")

    def _open_map(self, now, purpose):
        self.ctrl.release_all()
        self.ctrl.press(self.s.map_key)
        self.state = FState.MAP
        self._map_t = now
        self._map_purpose = purpose

    def _map(self, now, frame):
        if now - self._map_t < MAP_WAIT_S:
            return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "reading the map")
        fix = self._read_map(frame)
        if fix is None:
            if now - self._map_t < MAP_TIMEOUT_S:
                return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "looking for the player arrow")
            self.ctrl.press(self.s.map_key)
            if self._map_purpose == "land":
                return self._fall_back_to_roam(now, frame)
            if not self.nav.skip():
                return self._finish_route(now)
            self._open_map(now, "nav")
            return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "player not found: retrying")

        self.ctrl.press(self.s.map_key)   # close the map
        if self._map_purpose == "land":
            return self._landed(now, fix)
        return self._navigate(now, fix)

    def _fall_back_to_roam(self, now, frame):
        self.ready = False
        self.startup_note = "could not read the map: roaming mode"
        self.roam.state = CState.PLAY
        self.roam._t_match = now
        self.roam._match_chests = 0
        self.roam._prev = None
        self.roam.explorer.reset()
        return self.roam.step(frame)

    def _landed(self, now, fix):
        if self._map_fix is None:
            self._map_fix = fix
            self._wait(now, LAND_RETRY_S, "map_land")
            return FarmResult(FState.WAIT, self.chests, self.loops, 0.0, False, "checking if we are on the ground")
        moved = distance(fix, self._map_fix)
        if moved <= LAND_STABLE or now - self._land_start >= LAND_TIMEOUT_S:
            self._map_fix = None
            self.nav.set_route(self.route_ref)
            decision = self.nav.on_fix(fix, now)
            self._enter_run(now, decision)
            return FarmResult(FState.RUN, self.chests, self.loops, 0.0, False, "landed: running the chest route")
        self._map_fix = fix
        self._wait(now, LAND_RETRY_S, "map_land")
        return FarmResult(FState.WAIT, self.chests, self.loops, 0.0, False, "still in the air")

    def _navigate(self, now, fix):
        decision = self.nav.on_fix(fix, now)
        if decision.arrived:
            self.ctrl.release_all()
            self.explorer.reset()
            self._loot_until = now + self.s.loot_search_s
            self.state = FState.LOOT
            return FarmResult(FState.LOOT, self.chests, self.loops, 0.0, False, "at a chest spot: searching")
        if decision.stuck:
            if self.nav.stuck_fixes >= 3 and not self.nav.skip():
                return self._finish_route(now)
            self._enter_run(now, decision, unstick = True)
            return FarmResult(FState.RUN, self.chests, self.loops, 0.0, True, "blocked: jumping around it")
        self._enter_run(now, decision)
        return FarmResult(FState.RUN, self.chests, self.loops, 0.0, False, f"{decision.note}: running {decision.run_s:.0f}s")

    def _enter_run(self, now, decision, unstick = False):
        self.state = FState.RUN
        self.ctrl.release_all()
        if decision.turn:
            self.ctrl.look(decision.turn)
        if unstick:
            side = 1 if self.nav.legs % 2 else -1
            self.ctrl.move(walk = True, strafe = side)
            self.ctrl.press("space")
            self._run_until = now + 1.0
        else:
            self.ctrl.move(walk = True)
            self._run_until = now + max(0.5, decision.run_s)
        self._stuck_since = None

    def _wait(self, now, seconds, next_state):
        self.state = FState.WAIT
        self._wait_until = now + seconds
        self._wait_next = next_state

    def _wait_step(self, now):
        if now < self._wait_until:
            return FarmResult(FState.WAIT, self.chests, self.loops, 0.0, False, "waiting")
        self._open_map(now, "land" if self._wait_next == "map_land" else "nav")
        return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "map check")

    def _run(self, now, frame, ox, oy, play):
        finished = self._check_match_over(now, play)
        if finished is not None:
            return finished
        overlay = self._overlay(now, frame, ox, oy)
        if overlay is not None:
            return overlay

        detection = self.finder.detect(frame)
        height, width = frame.shape[:2]
        if detection is not None:
            close = detection.h >= 0.2 * height and abs(detection.x - width / 2) <= 0.1 * width
            if close:
                self.ctrl.release_all()
                self.explorer.reset()
                self._loot_until = now + self.s.loot_search_s
                self.state = FState.LOOT
                return FarmResult(FState.LOOT, self.chests, self.loops, detection.score, False, "chest in sight: looting")

        if self._blocked(now, frame):
            return FarmResult(FState.RUN, self.chests, self.loops, 0.0, True, "blocked: jumping around it")

        if now >= self._run_until:
            self._open_map(now, "nav")
            return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "map check")
        return FarmResult(FState.RUN, self.chests, self.loops, 0.0, False, "running to the chest")

    def _loot(self, now, frame, ox, oy, play):
        finished = self._check_match_over(now, play)
        if finished is not None:
            return finished
        overlay = self._overlay(now, frame, ox, oy)
        if overlay is not None:
            return overlay

        detection = self.finder.detect(frame)
        height, width = frame.shape[:2]
        action = self.explorer.step(now, width, height, detection, self._moved(frame))
        self._act(action)
        score = detection.score if detection is not None else 0.0

        if now >= self._loot_until:
            self.ctrl.release_all()
            if self.nav.advance():
                self._open_map(now, "nav")
                return FarmResult(FState.MAP, self.chests, self.loops, score, False, "spot done: next chest")
            return self._finish_route(now)
        return FarmResult(FState.LOOT, self.chests, self.loops, score, False, action.note)

    def _exit(self, now, frame, ox, oy, play):
        found, score = self._find("menu_return", frame)
        if self._click(found, ox, oy):
            return self._to_lobby(score)
        found, score = self._find("menu_btn", frame)
        if self._click(found, ox, oy):
            self._t_esc = now
            return FarmResult(FState.EXIT, self.chests, self.loops, score, True, "clicked menu_btn")
        if play is not None:
            return self._to_lobby(0.0)
        if now - self._t_esc >= ESC_RETRY_S and self._esc_tries < ESC_MAX_TRIES:
            self._press_esc(now, first = False)
            return FarmResult(FState.EXIT, self.chests, self.loops, 0.0, True, f"pressed Esc again ({self._esc_tries})")
        if self._esc_tries >= ESC_MAX_TRIES and now - self._t_esc >= EXIT_GIVE_UP_S:
            self.ctrl.release_all()
            self.nav.set_route(self.route_ref)
            self._match_start = now
            self._open_map(now, "nav")
            return FarmResult(FState.MAP, self.chests, self.loops, 0.0, False, "cannot leave: keep farming")
        return FarmResult(FState.EXIT, self.chests, self.loops, 0.0, False, "waiting for the menu")

    # --- helpers ---------------------------------------------------------
    def _finish_route(self, now):
        self.state = FState.EXIT
        self.ctrl.release_all()
        self._press_esc(now, first = True)
        return FarmResult(FState.EXIT, self.chests, self.loops, 0.0, True, "route done: leaving the match")

    def _to_lobby(self, score):
        self.state = FState.LOBBY
        self.loops += 1
        self.ctrl.release_all()
        self._play_since = None
        return FarmResult(FState.LOBBY, self.chests, self.loops, score, False, "back in the lobby")

    def _check_match_over(self, now, play):
        if play is None:
            self._play_since = None
            return None
        if now - self._match_start < MIN_MATCH_S:
            return None
        if self._play_since is None:
            self._play_since = now
            return None
        if now - self._play_since >= LOBBY_GRACE:
            return self._to_lobby(0.0)
        return None

    def _overlay(self, now, frame, ox, oy):
        if self._calls % OVERLAY_EVERY:
            return None
        for key in OVERLAY_KEYS:
            found, score = self._find(key, frame)
            if self._click(found, ox, oy):
                self.ctrl.release_all()
                return FarmResult(self.state, self.chests, self.loops, score, True, f"clicked {key} (match over)")
        return None

    def _blocked(self, now, frame):
        moved = self._moved(frame)
        if moved is not False:
            self._stuck_since = None
            return False
        if self._stuck_since is None:
            self._stuck_since = now
            return False
        if now - self._stuck_since < STUCK_AFTER_S:
            return False
        self.ctrl.release_all()
        side = 1 if self.nav.legs % 2 else -1
        self.ctrl.move(walk = True, strafe = side)
        self.ctrl.press("space")
        self._stuck_since = now
        return True

    def _moved(self, frame):
        moved = None
        if self._prev is not None:
            moved = frame_diff(self._prev, frame) >= MOVED_THRESHOLD
        self._prev = frame
        return moved

    def _read_map(self, frame):
        box = island_box(frame)
        arrow = self.player.find(frame, box) if box is not None else self.player.find(frame)
        if arrow is None:
            return None
        if self.aligner is not None and self.aligner.ready:
            matrix = self.aligner.locate(frame)
            if matrix is not None:
                point = self.aligner.transform(matrix, (arrow.x, arrow.y))
                if point is not None and self.ref_size[0] and self.ref_size[1]:
                    return (point[0] / self.ref_size[0], point[1] / self.ref_size[1])
        # Fallback: both maps show the whole island, so match their land boxes.
        if box is None:
            return None
        return normalize((arrow.x, arrow.y), box)

    def _act(self, action):
        self.ctrl.move(action.walk, action.strafe)
        if action.look:
            self.ctrl.look(action.look)
        if action.jump:
            self.ctrl.press("space")
        if action.interact:
            self.ctrl.press("e")
            self.chests += 1

    def _press_esc(self, now, first):
        self.ctrl.press("esc")
        self._t_esc = now
        self._esc_tries = 1 if first else self._esc_tries + 1

    def _find(self, key, frame):
        template = self.templates.get(key)
        if template is None:
            return None, 0.0
        if isinstance(template, Plate):
            return find_plate(frame, template, self.s.scales)
        return find_template(frame, template, self.s.threshold, self.s.scales)

    def _click(self, match, ox, oy):
        return bool(match) and self.ctrl.click(match[0] + ox, match[1] + oy)
