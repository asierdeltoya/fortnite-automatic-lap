"""Read the Fortnite map with computer vision.

Two jobs:

* `find_reference_chests()` reads the chest route from a static, annotated map
  image (`assets/chest_map.png`). It finds the little dark chest icons that the
  map uses and returns their position as fractions of the island.
* `PlayerFinder` finds the white arrow that marks the player on the in-game
  map and returns its position the same way.

Both positions are fractions of the island's bounding box, so a 1080p screen, a
1440p screen and the reference image all speak the same language. Keep the
in-game map fully zoomed out and not panned: the whole island must be visible.
"""

import os

import cv2
import numpy as np

import config
from detect import Match, nms
from geometry import distance, ordered_route

WATER_LOW = (78, 40, 40)
WATER_HIGH = (118, 255, 255)

DARK_MAX_VALUE = 120
GOLD_LOW = (8, 80, 110)
GOLD_HIGH = (42, 255, 255)

CHEST_ICON_MIN_AREA = 0.00006
CHEST_ICON_MAX_AREA = 0.004
CHEST_ICON_MIN_GOLD = 0.03

PLAYER_ROTATIONS = (0, 45, 90, 135, 180, 225, 270, 315)
PLAYER_SCALES = (0.8, 1.0, 1.25)
PLAYER_THRESHOLD = 0.6


def island_box(image):
    """Bounding box of the island in a map image, or None."""
    if image is None or not image.size:
        return None
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    water = cv2.inRange(hsv, WATER_LOW, WATER_HIGH)
    land = cv2.bitwise_not(water)
    # Dark UI panels and map borders are not island: without this the frame
    # around the map can win as the biggest "land" component.
    land[np.where(hsv[:, :, 2] < 55, True, False)] = 0
    land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    land = cv2.morphologyEx(land, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    contours = cv2.findContours(land, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    height, width = image.shape[:2]
    best = None
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 0.25 * width or h < 0.25 * height:
            continue
        if cv2.contourArea(contour) < 0.06 * width * height:
            continue
        if x <= 2 and y <= 2 and x + w >= width - 2 and y + h >= height - 2:
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        return None
    x, y, w, h = best
    return (x, y, x + w, y + h)


def normalize(point, box):
    x0, y0, x1, y1 = box
    return ((point[0] - x0) / max(1, x1 - x0), (point[1] - y0) / max(1, y1 - y0))


def denormalize(point, box):
    x0, y0, x1, y1 = box
    return (x0 + point[0] * (x1 - x0), y0 + point[1] * (y1 - y0))


def find_reference_chests(image, box = None, min_gold = CHEST_ICON_MIN_GOLD):
    """Every chest icon of the annotated map, as island fractions.

    The icons are dark little squares with a golden chest and a number inside,
    all the same size. Dark blobs of the right size that also contain gold are
    kept; the dominant icon size is used to drop stray labels and shadows.
    """
    if image is None or not image.size:
        return []
    box = box or island_box(image)
    if box is None:
        return []
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    dark = np.where(value < DARK_MAX_VALUE, 255, 0).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]

    height, width = image.shape[:2]
    frame_area = float(width * height)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 8 or h < 8:
            continue
        fraction = (w * h) / frame_area
        if not CHEST_ICON_MIN_AREA <= fraction <= CHEST_ICON_MAX_AREA:
            continue
        if not 0.45 <= w / h <= 2.2:
            continue
        if cv2.contourArea(contour) / float(w * h) < 0.4:
            continue
        if not (box[0] <= x + w / 2 <= box[2] and box[1] <= y + h / 2 <= box[3]):
            continue
        patch = hsv[y:y + h, x:x + w]
        gold = (
            (patch[:, :, 0] >= GOLD_LOW[0]) & (patch[:, :, 0] <= GOLD_HIGH[0])
            & (patch[:, :, 1] >= GOLD_LOW[1]) & (patch[:, :, 2] >= GOLD_LOW[2])
        )
        score = float(gold.mean())
        if score < min_gold:
            continue
        found.append(Match(x + w // 2, y + h // 2, w, h, score))

    if not found:
        return []
    sizes = sorted(max(m.w, m.h) for m in found)
    typical = sizes[len(sizes) // 2]
    found = [m for m in found if 0.6 * typical <= max(m.w, m.h) <= 1.6 * typical]
    return [normalize((m.x, m.y), box) for m in nms(found, 0.3)]


def load_reference(path = None):
    """(image, island box, chest fractions) for the annotated map."""
    path = path or config.map_route_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(path)
    box = island_box(image)
    if box is None:
        raise ValueError("island not found in " + path)
    return image, box, find_reference_chests(image, box)


class PlayerFinder:
    """Find the player arrow on the in-game map.

    The arrow rotates with the player's view, so the cropped template is
    rotated in 45 degree steps and matched at a few sizes. Prepared once and
    reused for every map read.
    """

    def __init__(self, template, rotations = PLAYER_ROTATIONS, scales = PLAYER_SCALES, threshold = PLAYER_THRESHOLD):
        self.ready = template is not None and getattr(template, "size", 0) > 0
        self.threshold = threshold
        self.variants = []
        if not self.ready:
            return
        gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template
        for angle in rotations:
            rotated = _rotate(gray, angle)
            for scale in scales:
                t = cv2.resize(rotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
                if min(t.shape[:2]) >= 6:
                    self.variants.append(t)

    def find(self, frame, box = None):
        """Best arrow match in the map, or None."""
        if not self.ready or frame is None or not frame.size:
            return None
        x0, y0, x1, y1 = box or (0, 0, frame.shape[1], frame.shape[0])
        region = frame[y0:y1, x0:x1]
        if region.size == 0:
            return None
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        best = None
        for template in self.variants:
            th, tw = template.shape[:2]
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if best is None or score > best.score:
                best = Match(x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2, tw, th, float(score))
        if best is None or best.score < self.threshold:
            return None
        return best

    def fix(self, frame, box = None):
        """Player position as island fractions, or None."""
        box = box or island_box(frame)
        if box is None:
            return None
        found = self.find(frame, box)
        if found is None:
            return None
        return normalize((found.x, found.y), box)


def render_debug(image, box, player = None, chests = (), route = ()):
    """Copy of `image` with the island box, the player, the chests and a route."""
    out = image.copy()
    if box is not None:
        cv2.rectangle(out, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 3)
        for point in chests:
            x, y = denormalize(point, box)
            cv2.circle(out, (int(x), int(y)), 7, (0, 200, 255), -1)
        if player is not None:
            px, py = denormalize(player, box)
            cv2.circle(out, (int(px), int(py)), 11, (255, 0, 255), 3)
            if route:
                points = [player] + ordered_route(player, list(route))[:12]
                pixels = [(int(x), int(y)) for x, y in (denormalize(p, box) for p in points)]
                for a, b in zip(pixels, pixels[1:]):
                    cv2.line(out, a, b, (255, 0, 0), 2)
    return out


def save_image(path, image):
    ok, encoded = cv2.imencode(os.path.splitext(path)[1] or ".png", image)
    if ok:
        encoded.tofile(path)


def nearest_chests(player, chests, count = 3):
    """The closest chests to a position, for logging."""
    return sorted(chests, key=lambda p: distance(player, p))[:count]


def _rotate(image, angle):
    angle = angle % 360
    if angle % 90 == 0:
        turns = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[int(angle)]
        return image if turns is None else cv2.rotate(image, turns)
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += new_w / 2.0 - center[0]
    matrix[1, 2] += new_h / 2.0 - center[1]
    return cv2.warpAffine(image, matrix, (new_w, new_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
