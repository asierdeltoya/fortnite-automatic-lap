"""Find chests in a Fortnite frame.

The first signal is colour: chests are gold and strongly saturated, which is
cheap to detect and survives distance, angle and lighting changes better than a
single image. That alone cannot tell a chest from a golden weapon lying on the
floor, so a chest cropped by the player (assets/chest_btn.png or any
assets/chest*.png) is used to confirm the candidates.

Detection runs on a half-size copy of the frame and only the confirmed
candidates are checked again at full size, which keeps a 1080p frame around
10-20 ms instead of the ~400 ms a full multi-scale sweep costs.
"""

import cv2
import numpy as np

import config
from detect import Match, find_all, iou, nms, shrink
from vision import load_template_auto

# Gold in HSV (OpenCV hue is 0-180). Chests are bright yellow-orange.
GOLD_LOW = (8, 110, 120)
GOLD_HIGH = (40, 255, 255)

GOLD_THRESHOLD = 0.55
MIN_AREA = 0.0008      # of the frame; smaller is noise
MAX_AREA = 0.06        # of the frame; bigger is scenery or a menu
MIN_FILL = 0.3         # contour area / bounding box
MIN_SIDE = 8           # pixels, before scaling back up

DETECT_SCALE = 0.5
VERIFY_SCALES = (0.85, 1.0, 1.15)
VERIFY_THRESHOLD = 0.55

# The current chest has purple gems and red eyes; golden weapons do not. A few
# pixels of either colour are a strong hint that a golden blob is a chest.
GEM_MIN_PIXELS = 6
GEM_BONUS = 0.15


def count_gem_pixels(frame, match):
    """Purple or red pixels inside a candidate box (chest gems and eyes)."""
    x0, y0, x1, y1 = match.box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return 0
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    purple = (hue >= 130) & (hue <= 170) & (sat >= 70) & (val >= 60)
    red = ((hue <= 6) | (hue >= 172)) & (sat >= 110) & (val >= 80)
    return int((purple | red).sum())


def find_gold(frame, threshold = GOLD_THRESHOLD, min_area = MIN_AREA, max_area = MAX_AREA):
    """Gold-coloured blobs that could be a chest, best first."""
    if frame is None or not frame.size:
        return []
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, GOLD_LOW, GOLD_HIGH)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]

    height, width = frame.shape[:2]
    frame_area = float(width * height)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < MIN_SIDE or h < MIN_SIDE:
            continue
        fraction = (w * h) / frame_area
        if not min_area <= fraction <= max_area:
            continue
        if not 0.35 <= w / h <= 3.5:
            continue
        fill = cv2.contourArea(contour) / float(w * h)
        if fill < MIN_FILL:
            continue
        size = min(1.0, fraction / 0.02)
        score = 0.5 * fill + 0.5 * size
        if score >= threshold:
            found.append(Match(x + w // 2, y + h // 2, w, h, round(score, 3)))
    return sorted(found, key=lambda m: m.score, reverse=True)


class ChestFinder:
    """Chest detector with an optional template confirmation step."""

    def __init__(
        self,
        templates = (),
        threshold = GOLD_THRESHOLD,
        scales = VERIFY_SCALES,
        detect_scale = DETECT_SCALE,
    ):
        self.templates = [t for t in templates if t is not None and getattr(t, "size", 0)]
        self.threshold = threshold
        self.scales = scales
        self.detect_scale = detect_scale

    @classmethod
    def from_assets(cls, threshold = GOLD_THRESHOLD):
        """Load every chest image saved next to the program, if any."""
        images = [load_template_auto(path) for path in config.chest_template_paths()]
        return cls(images, threshold = threshold)

    def detect(self, frame):
        """Best chest in the frame, or None. Coordinates are full-frame pixels."""
        if frame is None or not frame.size:
            return None
        small = shrink(frame, self.detect_scale)
        candidates = [m.scaled(1 / self.detect_scale) for m in find_gold(small, self.threshold)]

        matches = [self._verify(frame, candidate) for candidate in candidates]
        matches = [m for m in matches if m is not None and m.score >= self.threshold]
        if not matches:
            return None
        return max(nms(matches), key=lambda m: (m.score, m.area))

    def _verify(self, frame, candidate):
        """Check a colour candidate against the cropped templates.

        With a cropped chest the templates decide: a plain gold blob (a weapon
        on the floor, a golden UI badge) is not a chest and is rejected.
        """
        if not self.templates:
            return candidate
        box = candidate.box
        pad_x, pad_y = max(12, candidate.w // 2), max(12, candidate.h // 2)
        x0 = max(0, box[0] - pad_x)
        y0 = max(0, box[1] - pad_y)
        x1 = min(frame.shape[1], box[2] + pad_x)
        y1 = min(frame.shape[0], box[3] + pad_y)
        region = frame[y0:y1, x0:x1]
        best = 0.0
        for template in self.templates:
            for found in find_all(region, template, VERIFY_THRESHOLD, self.scales, max_results = 2):
                moved = Match(found.x + x0, found.y + y0, found.w, found.h, found.score)
                if iou(moved.box, candidate.box) > 0.1:
                    best = max(best, moved.score)
        if best < self.threshold:
            return None
        return Match(candidate.x, candidate.y, candidate.w, candidate.h, round(best, 3))
