import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mapvision import PlayerFinder, find_reference_chests, island_box, load_reference, normalize, render_debug, save_image

WATER = (200, 170, 40)
LAND = (60, 140, 70)
DARK = (20, 30, 45)
GOLD = (40, 150, 230)


def map_image(size = (800, 600), icons = (), arrows = ()):
    width, height = size
    image = np.full((height, width, 3), WATER, np.uint8)
    cv2.rectangle(image, (100, 100), (700, 500), LAND, -1)
    for x, y in icons:
        cv2.rectangle(image, (x, y), (x + 21, y + 21), DARK, -1)
        cv2.rectangle(image, (x + 4, y + 4), (x + 17, y + 17), GOLD, -1)
        cv2.putText(image, "4", (x + 7, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 220, 250), 1)
    for x, y, direction in arrows:
        _arrow(image, x, y, direction)
    return image


def _arrow(image, x, y, direction = "up"):
    if direction == "up":
        points = np.array([[x, y], [x + 12, y + 20], [x + 6, y + 20], [x + 6, y + 28], [x - 6, y + 28], [x - 6, y + 20], [x - 12, y + 20]])
    else:
        points = np.array([[x, y], [x - 20, y + 12], [x - 20, y + 6], [x - 28, y + 6], [x - 28, y - 6], [x - 20, y - 6], [x - 20, y - 12]])
    cv2.fillPoly(image, [points], (255, 255, 255))
    cv2.polylines(image, [points], True, (0, 0, 0), 1)


def test_island_box_ignores_the_sea():
    box = island_box(map_image())
    assert box is not None
    x0, y0, x1, y1 = box
    assert abs(x0 - 100) <= 3 and abs(y0 - 100) <= 3
    assert abs(x1 - 701) <= 4 and abs(y1 - 501) <= 4


def test_island_fractions_do_not_depend_on_the_image_size():
    small = map_image((800, 600), icons = [(200, 200)])
    big = cv2.resize(small, None, fx = 1.5, fy = 1.5, interpolation = cv2.INTER_NEAREST)
    small_points = find_reference_chests(small)
    big_points = find_reference_chests(big)
    assert len(small_points) == len(big_points) == 1
    for a, b in zip(small_points[0], big_points[0]):
        assert abs(a - b) < 0.01


def test_chest_icons_are_found_and_stray_dark_marks_are_not():
    icons = [(180, 180), (320, 260), (500, 400), (250, 420), (600, 150)]
    image = map_image(icons = icons)
    cv2.rectangle(image, (650, 450), (700, 470), DARK, -1)   # a dark shadow, no gold
    found = find_reference_chests(image)
    assert len(found) == len(icons)
    box = island_box(image)
    expected = sorted(normalize((x + 10, y + 10), box) for x, y in icons)
    for point, want in zip(sorted(found), expected):
        assert abs(point[0] - want[0]) < 0.01 and abs(point[1] - want[1]) < 0.01


def test_no_icons_no_route():
    assert find_reference_chests(map_image()) == []


def test_player_arrow_is_found_whatever_way_it_points():
    image = map_image(arrows = [(350, 300, "up")])
    template = image[290:330, 330:370].copy()
    finder = PlayerFinder(template)
    found = finder.find(image)
    assert found is not None
    assert abs(found.x - 350) < 8 and abs(found.y - 315) < 8

    turned = map_image(arrows = [(520, 380, "left")])
    found = finder.find(turned)
    assert found is not None
    assert abs(found.x - 500) < 12 and abs(found.y - 380) < 12


def test_player_fix_is_an_island_fraction():
    image = map_image(arrows = [(400, 300, "up")])
    template = image[290:330, 380:420].copy()
    fix = PlayerFinder(template).fix(image)
    assert fix is not None
    assert 0.4 < fix[0] < 0.55 and 0.4 < fix[1] < 0.6


def test_a_missing_arrow_template_never_crashes():
    finder = PlayerFinder(None)
    assert finder.ready is False
    assert finder.find(map_image()) is None
    assert finder.fix(map_image()) is None


def test_debug_render_and_saved_reference(tmp_path):
    icons = [(200, 200), (400, 300), (500, 400)]
    image = map_image(icons = icons)
    box = island_box(image)
    points = find_reference_chests(image)
    player = points[0]
    debug = render_debug(image, box, player, points, points)
    assert debug.shape == image.shape

    path = str(tmp_path / "chest_map.png")
    save_image(path, image)
    loaded, loaded_box, loaded_points = load_reference(path)
    assert loaded.shape == image.shape
    assert len(loaded_points) == len(points)
    assert loaded_box == box
