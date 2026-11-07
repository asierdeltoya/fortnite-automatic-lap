"""Computer-vision helpers used by the chest mode.

Everything here works on plain BGR frames (``numpy.uint8``, height x width x 3)
so it can be tested without a screen. Coordinates are pixels of the frame that
was passed in.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Match:
    """A detection: centre, size and a confidence between 0 and 1."""

    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def box(self):
        half_w, half_h = self.w // 2, self.h // 2
        return (self.x - half_w, self.y - half_h, self.x + half_w, self.y + half_h)

    @property
    def area(self):
        return self.w * self.h

    def scaled(self, factor):
        return Match(
            round(self.x * factor),
            round(self.y * factor),
            max(1, round(self.w * factor)),
            max(1, round(self.h * factor)),
            self.score,
        )


def iou(a, b):
    """Intersection over union of two (x0, y0, x1, y1) boxes."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms(matches, overlap = 0.4):
    """Drop boxes that overlap a better one, keeping the highest scores."""
    kept = []
    for match in sorted(matches, key=lambda m: m.score, reverse=True):
        if all(iou(match.box, other.box) <= overlap for other in kept):
            kept.append(match)
    return kept


def shrink(frame, factor):
    """Resize a frame by `factor`, keeping the interpolation sensible."""
    if factor == 1:
        return frame
    return cv2.resize(
        frame,
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_LINEAR,
    )


def find_all(frame, template, threshold = 0.7, scales = (0.6, 0.8, 1.0, 1.2), max_results = 4):
    """Find every copy of `template` in `frame` at several sizes.

    The top matches of each scale are kept, overlapping boxes are removed, and
    the best `max_results` are returned. The scale range is deliberately small
    because chests are verified inside a region proposed by the colour filter.
    """
    if frame is None or template is None or not frame.size or not template.size:
        return []
    fg = _gray(frame)
    tg = _gray(template)
    found = []
    for scale in scales:
        t = shrink(tg, scale)
        th, tw = t.shape[:2]
        if tw < 6 or th < 6 or th > fg.shape[0] or tw > fg.shape[1]:
            continue
        res = cv2.matchTemplate(fg, t, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
        keep = min(8, res.size)
        flat = np.argpartition(res.ravel(), -keep)[-keep:]
        for index in flat:
            y, x = divmod(int(index), res.shape[1])
            score = float(res[y, x])
            if score >= threshold:
                found.append(Match(x + tw // 2, y + th // 2, tw, th, score))
    return nms(found)[:max_results]


def frame_diff(previous, current, size = (64, 36)):
    """How much two frames differ, from 0 (identical) to 1 (totally different).

    Used to notice that the character is walking into a wall: while moving,
    the picture keeps changing, so a still picture means "stuck".
    """
    if previous is None or current is None:
        return 1.0
    if previous.shape != current.shape:
        return 1.0
    a = cv2.resize(previous, size, interpolation=cv2.INTER_AREA)
    b = cv2.resize(current, size, interpolation=cv2.INTER_AREA)
    a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) if a.ndim == 3 else a
    b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) if b.ndim == 3 else b
    return float(cv2.absdiff(a, b).mean()) / 255.0


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
