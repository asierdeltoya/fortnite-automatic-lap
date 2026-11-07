"""Mode C: drop in, walk around the map and open chests.

The bot starts a match from the lobby, hands control to `Explorer` while the
match runs, and returns to the lobby when it has opened enough chests or the
match has lasted too long. If the game cannot be left (a normal Battle Royale
match has a different pause menu), it simply keeps exploring and waits for the
match to end.

It only reads the screen: no game memory, no network, no injection.
"""

import time
from dataclasses import dataclass
from enum import Enum

from chest import ChestFinder
from detect import frame_diff
from explore import Explorer
from state_machine import POPUP_KEYS
from vision import Plate, find_plate, find_template

# How long the lobby Play button must stay visible before a running match is
# considered finished (it is still on screen for a moment after clicking it).
LOBBY_GRACE = 3.0
MIN_MATCH_S = 12.0

MAX_CHESTS_PER_MATCH = 10
MATCH_LIMIT_S = 10 * 60.0
ESC_RETRY_S = 8.0
ESC_MAX_TRIES = 3
EXIT_GIVE_UP_S = 6.0

MOVED_THRESHOLD = 0.004


class CState(Enum):
    LOBBY = "C:LOBBY"
    PLAY = "C:PLAY"
    EXIT = "C:EXIT"


@dataclass
class ChestResult:
    state: CState
    chests: int = 0
    score: float = 0.0
    clicked: bool = False
    note: str = ""


class ChestMode:
    def __init__(self, settings, templates, controller):
        self.s = settings
        self.templates = templates
        self.ctrl = controller
        self.finder = ChestFinder.from_assets(getattr(settings, "chest_threshold", 0.55))
        self.explorer = Explorer()
        self.state = CState.LOBBY
        self.loops = 0
        self.chests = 0
        self._match_chests = 0
        self._t_match = 0.0
        self._t_esc = 0.0
        self._esc_tries = 0
        self._play_since = None
        self._prev = None

    def start(self):
        if self.state is CState.LOBBY:
            self.chests = 0
            self._match_chests = 0
            self.explorer.reset()
            self._prev = None

    def stop(self):
        self.ctrl.release_all()
        self.explorer.reset()
        self._prev = None
        self.state = CState.LOBBY

    def step(self, frame, ox = 0, oy = 0):
        now = time.monotonic()
        play, play_score = self._find("play", frame)
        if self.state is CState.LOBBY:
            return self._lobby(now, frame, ox, oy, play, play_score)
        if self.state is CState.EXIT:
            return self._exit(now, frame, ox, oy, play)
        return self._play(now, frame, play, play_score)

    def _enter_match(self, now):
        self.state = CState.PLAY
        self._t_match = now
        self._match_chests = 0
        self._play_since = None
        self._prev = None
        self.explorer.reset()

    def _lobby(self, now, frame, ox, oy, play, play_score):
        if self._click(play, ox, oy):
            self._enter_match(now)
            return ChestResult(CState.PLAY, self.chests, play_score, True, "clicked play")
        for key in POPUP_KEYS:
            found, score = self._find(key, frame)
            if self._click(found, ox, oy):
                return ChestResult(CState.LOBBY, self.chests, score, True, f"clicked {key} (stay)")
        return ChestResult(CState.LOBBY, self.chests, play_score, False, "waiting play")

    def _play(self, now, frame, play, play_score):
        if play is not None:
            if self._play_since is None:
                self._play_since = now
            if now - self._play_since >= LOBBY_GRACE and now - self._t_match >= MIN_MATCH_S:
                self.loops += 1
                self.state = CState.LOBBY
                self.ctrl.release_all()
                return ChestResult(CState.LOBBY, self.chests, play_score, False, "match over")
        else:
            self._play_since = None

        if self._match_chests >= MAX_CHESTS_PER_MATCH or now - self._t_match >= MATCH_LIMIT_S:
            self.state = CState.EXIT
            self.ctrl.release_all()
            self._press_esc(now, first = True)
            return ChestResult(CState.EXIT, self.chests, 0.0, True, "leaving match")

        detection = self.finder.detect(frame)
        moved = None
        if self._prev is not None:
            moved = frame_diff(self._prev, frame) >= MOVED_THRESHOLD
        self._prev = frame

        height, width = frame.shape[:2]
        action = self.explorer.step(now, width, height, detection, moved)
        self._act(action)
        score = detection.score if detection is not None else 0.0
        return ChestResult(CState.PLAY, self.chests, score, False, action.note)

    def _exit(self, now, frame, ox, oy, play):
        found, score = self._find("menu_return", frame)
        if self._click(found, ox, oy):
            self.loops += 1
            self.state = CState.LOBBY
            return ChestResult(CState.LOBBY, self.chests, score, True, "clicked menu_return")
        found, score = self._find("menu_btn", frame)
        if self._click(found, ox, oy):
            self._t_esc = now
            return ChestResult(CState.EXIT, self.chests, score, True, "clicked menu_btn")
        if play is not None:
            self.loops += 1
            self.state = CState.LOBBY
            return ChestResult(CState.LOBBY, self.chests, 0.0, False, "back in lobby")
        if now - self._t_esc >= ESC_RETRY_S and self._esc_tries < ESC_MAX_TRIES:
            self._press_esc(now, first = False)
            return ChestResult(CState.EXIT, self.chests, 0.0, True, f"pressed Esc again ({self._esc_tries})")
        if self._esc_tries >= ESC_MAX_TRIES and now - self._t_esc >= EXIT_GIVE_UP_S:
            # Normal Battle Royale has no "return to lobby" button in this menu:
            # keep playing instead of standing still forever.
            self.state = CState.PLAY
            self._t_match = now
            self._match_chests = 0
            return ChestResult(CState.PLAY, self.chests, 0.0, False, "could not leave: keep exploring")
        return ChestResult(CState.EXIT, self.chests, 0.0, False, "waiting menu")

    def _act(self, action):
        self.ctrl.move(action.walk, action.strafe)
        if action.look:
            self.ctrl.look(action.look)
        if action.jump:
            self.ctrl.press("space")
        if action.interact:
            self.ctrl.press("e")
            self.chests += 1
            self._match_chests += 1

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
