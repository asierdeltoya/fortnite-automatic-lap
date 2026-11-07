import os
import threading
from dataclasses import dataclass

import cv2
import mss
import numpy as np

_MSS = getattr(mss, "MSS", None) or mss.mss

def load_template(path):
    if not os.path.isfile(path):
        return None
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img

@dataclass
class Plate:

    image: np.ndarray
    mask: np.ndarray
    roi: tuple
    threshold: float

def load_template_auto(path, plate=None):
    if not os.path.isfile(path):
        return None
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:
        if plate is not None:
            return Plate(np.ascontiguousarray(img[:, :, :3]), np.ascontiguousarray(img[:, :, 3]), tuple(plate["roi"]), plate["threshold"])
        return np.ascontiguousarray(img[:, :, :3])
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img

_tls = threading.local()

# Every scale is scanned at half size (four times cheaper than full size);
# only the winning scale is then checked again at full size. Templates confirm
# chests and buttons in the middle of the screen, so this keeps a 1080p frame
# under ~150 ms instead of ~400 ms.

# A half-size score this far below the threshold cannot realistically reach it
# at full size, so the full-resolution refinement is skipped. Real matches
# score around 0.9 at half size, so this keeps a wide safety margin. Only big
# templates are tested this way: in a small one (the 27x29 ``continue`` button)
# half resolution loses too much detail for the score to be trusted.
EARLY_OUT = 0.15
EARLY_OUT_MIN = 0.55
GATE_MIN_TEMPLATE = 48

def _sct():
    sct = getattr(_tls, "sct", None)
    if sct is None:
        sct = _tls.sct = _MSS()
    return sct

def close_thread_capture():
    """Release the screen-capture session held by the current thread.

    mss keeps a display context open, and it has no finaliser, so a thread
    that ends without this call leaks it. Call it when a worker finishes.
    """
    sct = getattr(_tls, "sct", None)
    _tls.sct = None
    _tls.frame = None
    if sct is not None:
        try:
            sct.close()
        except Exception:
            pass

def list_monitors():
    with _MSS() as sct:
        return [(m["width"], m["height"]) for m in sct.monitors[1:]]

def capture_screen(monitor_index=1, region=None):
    sct = _sct()
    try:
        mon = region or sct.monitors[min(monitor_index, len(sct.monitors) - 1)]
        shot = np.array(sct.grab(mon))
    except Exception:
        close_thread_capture()
        raise
    return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR), mon["left"], mon["top"]

def _half(img):
    return cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)

def _prep_frame(frame):
    cache = getattr(_tls, "frame", None)
    if cache is None or cache[0] is not frame:
        g = _gray(frame)
        cache = _tls.frame = (frame, g, _half(g))
    return cache[1], cache[2]

_tpl_cache = {}

def _prep_template(template):
    e = _tpl_cache.get(id(template))
    if e is None or e["ref"] is not template:
        if len(_tpl_cache) > 64:
            _tpl_cache.clear()
        g = _gray(template)
        e = {"ref": template, "gray": g, "half": _half(g)}
        _tpl_cache[id(template)] = e
    return e

def find_template(
    frame,
    template,
    threshold = 0.82,
    scales = (0.9, 0.95, 1.0, 1.05, 1.1),
):
    fg, half_f = _prep_frame(frame)
    e = _prep_template(template)
    tg, half_t = e["gray"], e["half"]

    # The half-size pass picks both the scale and an approximate position, so
    # the full-size check only has to look around that point. Matching the
    # whole 1080p frame three times per template is what used to cost ~400 ms.
    coarse = [_match(half_f, half_t, s) + (s,) for s in scales]
    coarse = [c for c in coarse if c[0] > -1]
    if not coarse:
        return None, 0.0
    best_score, half_x, half_y, best_scale = max(coarse, key = lambda c: (c[0], c[3]))
    if min(tg.shape[:2]) >= GATE_MIN_TEMPLATE and best_score < max(EARLY_OUT_MIN, threshold - EARLY_OUT):
        return None, max(best_score, 0.0)

    best = (-1.0, 0, 0)
    for s in (best_scale - 0.05, best_scale, best_scale + 0.05):
        score, x, y = _match_near(fg, tg, s, half_x * 2, half_y * 2)
        if score > best[0]:
            best = (score, x, y)
    score, x, y = best
    if score >= threshold:
        return (x, y, score), score
    if score >= threshold - 0.1:
        # Borderline: the coarse guess may have picked the wrong spot between
        # two similar scales, so pay for one full-frame check before giving up.
        full = (-1.0, 0, 0)
        for s in (best_scale - 0.05, best_scale, best_scale + 0.05):
            s2, x2, y2 = _match(fg, tg, s)
            if s2 > full[0]:
                full = (s2, x2, y2)
        score, x, y = full
        if score >= threshold:
            return (x, y, score), score
    return None, max(score, 0.0)

def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

def _match(frame, template, scale):
    t = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    th, tw = t.shape[:2]
    if th > frame.shape[0] or tw > frame.shape[1] or th < 4 or tw < 4:
        return -2.0, 0, 0
    _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(frame, t, cv2.TM_CCOEFF_NORMED))
    return float(max_val), max_loc[0] + tw // 2, max_loc[1] + th // 2

def _match_near(frame, template, scale, cx, cy):
    """Like _match, but only around (cx, cy), where the coarse pass saw it."""
    t = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    th, tw = t.shape[:2]
    if th < 4 or tw < 4 or th > frame.shape[0] or tw > frame.shape[1]:
        return -2.0, 0, 0
    pad = 24 + int(0.06 * max(tw, th))
    x0 = max(0, int(cx) - tw // 2 - pad)
    y0 = max(0, int(cy) - th // 2 - pad)
    x1 = min(frame.shape[1], int(cx) + tw // 2 + pad)
    y1 = min(frame.shape[0], int(cy) + th // 2 + pad)
    region = frame[y0:y1, x0:x1]
    if region.shape[0] < th or region.shape[1] < tw:
        return -2.0, 0, 0
    _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED))
    return float(max_val), x0 + max_loc[0] + tw // 2, y0 + max_loc[1] + th // 2

def find_plate(
    frame,
    plate,
    scales = (0.9, 0.95, 1.0, 1.05, 1.1),
):
    fh, fw = frame.shape[:2]
    x0, y0 = int(plate.roi[0] * fw), int(plate.roi[1] * fh)
    x1, y1 = int(plate.roi[2] * fw), int(plate.roi[3] * fh)
    region = frame[y0:y1, x0:x1]
    if region.size == 0:
        return None, 0.0

    def match(img, base, scale):
        f = base * scale
        t = cv2.resize(plate.image, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
        m = cv2.resize(plate.mask, (t.shape[1], t.shape[0]), interpolation=cv2.INTER_NEAREST)
        if t.shape[0] >= img.shape[0] or t.shape[1] >= img.shape[1] or min(t.shape[:2]) < 6 or not m.any():
            return -2.0, 0, 0
        res = np.nan_to_num(cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED, mask=m), nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, val, _, loc = cv2.minMaxLoc(res)
        return float(val), x0 + loc[0] + t.shape[1] // 2, y0 + loc[1] + t.shape[0] // 2

    half = cv2.resize(region, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    coarse = [(match(half, 0.5, s)[0], s) for s in scales]
    coarse = [c for c in coarse if c[0] > -2]
    if not coarse:
        return None, 0.0
    best_scale = max(coarse)[1]
    best = (-1.0, 0, 0)
    for s in (best_scale - 0.05, best_scale, best_scale + 0.05):
        cand = match(region, 1.0, s)
        if cand[0] > best[0]:
            best = cand
    score, x, y = best
    score = min(score, 1.0)
    if score >= plate.threshold:
        return (x, y, score), score
    return None, max(score, 0.0)
