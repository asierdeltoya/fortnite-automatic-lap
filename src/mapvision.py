"""Read the Fortnite map with computer vision.

Two jobs:

* `find_reference_chests()` reads the chest route from a static, annotated map
  image (`assets/chest_map.png`). Chest markers are a dark chest sprite with a
  golden outline and a golden number badge, so the badge (a bright yellow
  circle) is found with Hough circles and cross-checked against a colour pass.
* `PlayerFinder` finds the white arrow that marks the player on the in-game
  map. The cropped template usually carries map background, so matching uses a
  mask (the arrow's white body and dark outline, or the PNG alpha channel).

`MapAligner` matches the in-game map against the reference map with ORB
features and a homography, so the player can be located in reference
coordinates even if the game map is zoomed or framed differently. When that is
not possible, positions fall back to the island's bounding box.
"""

import os

import cv2
import numpy as np

import config
from detect import Match
from geometry import distance, ordered_route

WATER_LOW = (78, 40, 40)
WATER_HIGH = (118, 255, 255)

DARK_MAX_VALUE = 120
GOLD_LOW = (8, 80, 110)
GOLD_HIGH = (42, 255, 255)
BADGE_LOW = (15, 120, 150)
BADGE_HIGH = (42, 255, 255)

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
    """Every chest marker of the annotated map, as fractions of `box`.

    Chest sprites are found by colour (dark sprite with a golden chest inside);
    number badges are found with Hough circles and a golden colour check. Both
    lists are merged: badges are reliable, and the colour pass recovers markers
    whose badge is hidden. The badge sits on the top-right of the sprite, so
    the median offset between both sets moves every badge onto its sprite.
    """
    if image is None or not image.size:
        return []
    height, width = image.shape[:2]
    box = box or (0, 0, width, height)
    sprites = _sprite_seeds(image, box, min_gold)
    badges = _badge_seeds(image)
    points = _merge_marker_points(sprites, badges, image.shape[:2])

    if not points:
        return []
    points = [p for p in points if 0 <= p[0] < width and 0 <= p[1] < height]
    return [normalize(p, box) for p in points]


def _sprite_seeds(image, box, min_gold):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    dark = np.where(hsv[:, :, 2] < DARK_MAX_VALUE, 255, 0).astype(np.uint8)
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
        if float(gold.mean()) < min_gold:
            continue
        found.append(Match(x + w // 2, y + h // 2, w, h, float(gold.mean())))
    if not found:
        return []
    sizes = sorted(max(m.w, m.h) for m in found)
    typical = sizes[len(sizes) // 2]
    return [m for m in found if 0.6 * typical <= max(m.w, m.h) <= 1.6 * typical]


def _badge_seeds(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        cv2.medianBlur(gray, 3),
        cv2.HOUGH_GRADIENT,
        dp = 1,
        minDist = 14,
        param1 = 100,
        param2 = 12,
        minRadius = 6,
        maxRadius = 13,
    )
    if circles is None:
        return []
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    height, width = image.shape[:2]
    found = []
    for x, y, radius in np.round(circles[0]).astype(int):
        # Hough often locks on the dark digit inside the badge, so look at a
        # slightly wider square to see the golden ring around it.
        radius += 5
        if not (radius <= x < width - radius and radius <= y < height - radius):
            continue
        patch = hsv[y - radius:y + radius, x - radius:x + radius]
        golden = (
            (patch[:, :, 0] >= BADGE_LOW[0]) & (patch[:, :, 0] <= BADGE_HIGH[0])
            & (patch[:, :, 1] >= BADGE_LOW[1]) & (patch[:, :, 2] >= BADGE_LOW[2])
        ).mean()
        if golden >= 0.35:
            found.append(Match(x, y, radius * 2, radius * 2, float(golden)))
    return found


def _merge_marker_points(sprites, badges, shape):
    height, width = shape
    if not badges:
        badge_points = []
    else:
        badge_points = [(m.x, m.y) for m in badges]

    if badge_points and sprites:
        offsets = []
        for x, y in badge_points:
            nearest = min(sprites, key = lambda m: distance((x, y), (m.x, m.y)))
            if distance((x, y), (nearest.x, nearest.y)) <= 0.6 * max(nearest.w, nearest.h) * 2:
                offsets.append((nearest.x - x, nearest.y - y))
        if len(offsets) >= 3:
            dx = sorted(o[0] for o in offsets)[len(offsets) // 2]
            dy = sorted(o[1] for o in offsets)[len(offsets) // 2]
            badge_points = [(x + dx, y + dy) for x, y in badge_points]

    points = badge_points or [(m.x, m.y) for m in sprites]
    if not points:
        return []

    # Both lists can contain the same marker: collapse points that are close.
    spacing = max(10.0, 0.012 * max(width, height))
    unique = []
    for x, y in sorted(points, key = lambda p: (p[1], p[0])):
        if all(distance((x, y), other) > spacing for other in unique):
            unique.append((x, y))
    if len(unique) < 3 and sprites:
        return [(m.x, m.y) for m in sprites]
    return unique


def load_reference(path = None):
    """(image, island box, chest fractions) for the annotated map."""
    path = path or config.map_route_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(path)
    height, width = image.shape[:2]
    # The annotated map is cropped to the island, so its own frame is the box.
    box = (0, 0, width, height)
    return image, box, find_reference_chests(image, box)


class MapAligner:
    """ORB + homography from the in-game map to the reference image."""

    def __init__(self, reference, max_features = 4000, work_width = 1280):
        self.ready = reference is not None and reference.size > 0
        self.work_width = work_width
        self.reference_size = (reference.shape[1], reference.shape[0]) if self.ready else (0, 0)
        self.orb = cv2.ORB_create(nfeatures = max_features)
        self.kp = self.des = None
        if self.ready:
            gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
            self.kp, self.des = self.orb.detectAndCompute(gray, None)
            self.ready = self.des is not None and len(self.kp) >= 20
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck = True)

    def locate(self, frame, min_inliers = 14):
        """Homography (frame pixels -> reference pixels) or None."""
        if not self.ready or frame is None or not frame.size:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, self.work_width / float(gray.shape[1]))
        small = cv2.resize(gray, None, fx = scale, fy = scale, interpolation = cv2.INTER_AREA) if scale < 1.0 else gray
        kp, des = self.orb.detectAndCompute(small, None)
        if des is None or len(kp) < 12:
            return None
        matches = self.matcher.match(des, self.des)
        if len(matches) < min_inliers:
            return None
        src = np.float32([kp[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2) / scale
        dst = np.float32([self.kp[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if matrix is None or mask is None or int(mask.sum()) < min_inliers:
            return None
        return matrix

    def transform(self, matrix, point):
        p = np.array([point[0], point[1], 1.0])
        q = matrix @ p
        if abs(q[2]) < 1e-9:
            return None
        x, y = q[0] / q[2], q[1] / q[2]
        width, height = self.reference_size
        if not (-0.05 * width <= x <= 1.05 * width and -0.05 * height <= y <= 1.05 * height):
            return None
        return (float(x), float(y))


class PlayerFinder:
    """Find the player arrow on the in-game map.

    The arrow rotates with the player's view, so the cropped template is
    rotated in 45 degree steps and matched at a few sizes. If the PNG has an
    alpha channel it is used as the mask; otherwise the mask is the arrow's
    white body plus its dark outline, which ignores the map background around
    the crop.
    """

    def __init__(self, template, rotations = PLAYER_ROTATIONS, scales = PLAYER_SCALES, threshold = PLAYER_THRESHOLD):
        self.ready = template is not None and getattr(template, "size", 0) > 0
        self.threshold = threshold
        self.variants = []
        if not self.ready:
            return
        gray, mask = _template_and_mask(template)
        for angle in rotations:
            rotated = _rotate(gray, angle)
            rotated_mask = _rotate(mask, angle) if mask is not None else None
            for scale in scales:
                t = cv2.resize(rotated, None, fx = scale, fy = scale, interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
                m = None
                if rotated_mask is not None:
                    m = cv2.resize(rotated_mask, (t.shape[1], t.shape[0]), interpolation = cv2.INTER_NEAREST)
                if min(t.shape[:2]) >= 6:
                    self.variants.append((t, m))

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
        for template, mask in self.variants:
            th, tw = template.shape[:2]
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            if mask is not None:
                res = cv2.matchTemplate(gray, template, cv2.TM_SQDIFF_NORMED, mask = mask)
                res = 1.0 - np.nan_to_num(res, nan = 0.0, posinf = 0.0, neginf = 0.0)
            else:
                res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if best is None or score > best.score:
                best = Match(x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2, tw, th, float(score))
        if best is None or best.score < self.threshold:
            return None
        return best

    def fix(self, frame, box = None):
        """Player position inside `box` as fractions, or None."""
        box = box or (0, 0, frame.shape[1], frame.shape[0])
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
    return sorted(chests, key = lambda p: distance(player, p))[:count]


def _template_and_mask(template):
    if template.ndim == 3 and template.shape[2] == 4:
        alpha = template[:, :, 3]
        if (alpha < 10).sum() > 0:
            return cv2.cvtColor(template[:, :, :3], cv2.COLOR_BGR2GRAY), np.where(alpha > 10, 255, 0).astype(np.uint8)
    bgr = template[:, :, :3] if template.ndim == 3 else cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 2] >= 190) & (hsv[:, :, 1] <= 90)
    dark = hsv[:, :, 2] <= 90
    mask = np.where(white | dark, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    coverage = float((mask > 0).mean())
    if coverage < 0.08 or coverage > 0.9:
        return gray, None
    return gray, mask


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
    return cv2.warpAffine(image, matrix, (new_w, new_h), flags = cv2.INTER_LINEAR, borderMode = cv2.BORDER_REPLICATE)
