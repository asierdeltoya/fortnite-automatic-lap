import random
import time

import pydirectinput

from focus import ensure_game_foreground


class Controller:
    def __init__(self, settings):
        self.s = settings
        self._last_click = -1e9
        self._held = set()

    @staticmethod
    def _click(x, y):
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        pydirectinput.moveTo(x - random.randint(8, 16), y - random.randint(4, 8))
        time.sleep(random.uniform(0.04, 0.08))
        pydirectinput.moveTo(x, y)
        time.sleep(random.uniform(0.10, 0.20))
        pydirectinput.mouseDown(button="left")
        time.sleep(random.uniform(0.06, 0.12))
        pydirectinput.mouseUp(button="left")

    @staticmethod
    def _press(key):
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        pydirectinput.keyDown(key)
        time.sleep(random.uniform(0.06, 0.12))
        pydirectinput.keyUp(key)

    def press(self, key):
        time.sleep(random.uniform(self.s.delay_min, self.s.delay_max))
        ensure_game_foreground()
        self._press(key)

    def _set_held(self, wanted):
        """Hold exactly the movement keys in `wanted` and release the rest."""
        if wanted == self._held:
            return
        ensure_game_foreground()
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        for key in self._held - wanted:
            try:
                pydirectinput.keyUp(key)
            except Exception:
                pass
        for key in wanted - self._held:
            pydirectinput.keyDown(key)
        self._held = wanted

    def move(self, walk = False, strafe = 0):
        """Walk forward with W and strafe with A/D (0 = straight)."""
        wanted = set()
        if walk:
            wanted.add("w")
        if strafe > 0:
            wanted.add("d")
        elif strafe < 0:
            wanted.add("a")
        self._set_held(wanted)

    def release_all(self):
        for key in tuple(self._held):
            try:
                pydirectinput.keyUp(key)
            except Exception:
                pass
        self._held = set()

    def look(self, dx, dy = 0):
        """Turn the camera by a relative number of mouse counts."""
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return
        ensure_game_foreground()
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0.0
        pydirectinput.moveRel(dx, dy)

    def ready(self):
        return time.monotonic() - self._last_click >= self.s.click_cooldown

    def click(self, x, y):
        if not self.ready():
            return False
        j = self.s.jitter_px
        tx, ty = x + random.randint(-j, j), y + random.randint(-j, j)
        time.sleep(random.uniform(self.s.delay_min, self.s.delay_max))
        self._click(tx, ty)
        self._last_click = time.monotonic()
        return True
