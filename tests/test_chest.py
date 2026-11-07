import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chest import ChestFinder, find_gold
from detect import Match, find_all, frame_diff, nms

GOLD = (46, 163, 224)  # BGR for the gold of a chest


def scene(boxes=(), shape=(600, 900), colour=GOLD):
    frame = np.full((shape[0], shape[1], 3), 25, np.uint8)
    for x, y, w, h in boxes:
        cv2.rectangle(frame, (x, y), (x + w, y + h), colour, -1)
    return frame


def chest_patch():
    """A gold chest with structure, so a template can recognise it."""
    patch = np.full((60, 90, 3), GOLD, np.uint8)
    cv2.rectangle(patch, (0, 0), (89, 59), (30, 90, 140), 3)
    cv2.line(patch, (45, 0), (45, 59), (20, 70, 120), 2)
    cv2.circle(patch, (22, 30), 8, (10, 30, 60), -1)
    cv2.circle(patch, (68, 30), 8, (10, 30, 60), -1)
    return patch


def test_gold_rectangle_is_found():
    found = find_gold(scene([(400, 300, 90, 60)]))
    assert len(found) == 1
    match = found[0]
    assert abs(match.x - 445) <= 2 and abs(match.y - 330) <= 2
    assert abs(match.w - 90) <= 2 and abs(match.h - 60) <= 2
    assert match.score >= 0.55


def test_dark_or_grey_scene_has_no_chest():
    assert find_gold(scene()) == []
    assert find_gold(scene([(400, 300, 90, 60)], colour=(120, 120, 120))) == []


def test_huge_gold_area_is_rejected():
    assert find_gold(scene([(0, 0, 900, 600)])) == []


def test_gold_yellow_not_gold_brown():
    # Brown wood is much darker and less saturated than a chest.
    assert find_gold(scene([(400, 300, 90, 60)], colour=(30, 60, 90))) == []


def test_finder_without_templates_uses_colour():
    finder = ChestFinder()
    match = finder.detect(scene([(400, 300, 90, 60)]))
    assert match is not None and match.w >= 80


def test_finder_rejects_gold_blobs_that_are_not_the_cropped_chest():
    finder = ChestFinder([chest_patch()])
    # A plain gold rectangle scores well as colour but does not look like the
    # cropped chest, so it must not be opened.
    assert finder.detect(scene([(400, 300, 90, 60)])) is None


def test_finder_accepts_the_cropped_chest():
    patch = chest_patch()
    frame = scene()
    frame[300:360, 400:490] = patch
    match = ChestFinder([patch]).detect(frame)
    assert match is not None and match.score >= 0.55


def test_find_all_returns_each_copy_once():
    patch = chest_patch()
    frame = scene()
    frame[100:160, 100:190] = patch
    frame[400:460, 600:690] = patch
    found = find_all(frame, patch, 0.9, (1.0,), max_results=4)
    assert len(found) == 2
    assert len(nms(found)) == 2


def test_frame_diff_notices_movement_and_pauses():
    a = scene([(400, 300, 90, 60)])
    assert frame_diff(a, a.copy()) == 0.0
    b = scene([(500, 300, 90, 60)])
    assert frame_diff(a, b) > 0.004


def test_match_scales_and_box():
    match = Match(100, 50, 40, 20, 0.8)
    assert match.box == (80, 40, 120, 60)
    assert match.area == 800
    bigger = match.scaled(2.0)
    assert (bigger.x, bigger.y, bigger.w, bigger.h) == (200, 100, 80, 40)
