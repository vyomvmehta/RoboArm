"""Pointing + the hand-clear safety gate (V2-16).

PointSelector: a block is SELECTED when your index fingertip (landmark 8) stays within
radius_px of the same block for hold_s. Same idea as the gesture hold-to-confirm: a hand
sweeping over a block on its way somewhere else doesn't select it.

HandGate: the arm may only start (and keep moving) while your hand is OUT of the table area.
"Out" means every landmark is outside the area polygon (calibration marks + a margin) for
clear_s. No hand visible counts as out: with the camera seeing the whole table, a hand you
can't see isn't on the table. (If the camera can't see the whole area, that assumption
breaks: keep the calibration marks inside the camera view.)
"""
from __future__ import annotations

import cv2
import numpy as np

from arm.pick.blocks import Block
from arm.vision.hands import HandFrame

INDEX_TIP = 8


class PointSelector:
    def __init__(self, cfg: dict):
        self.radius = cfg["select"]["radius_px"]
        self.hold_s = cfg["select"]["hold_s"]
        self._key: tuple | None = None      # the block currently being pointed at
        self._since = 0.0
        self._fired: tuple | None = None    # the block that last fired

    def update(self, frame: HandFrame, blocks: list[Block], t: float) -> Block | None:
        """Returns the block once, on the frame the hold completes; None otherwise."""
        target = None
        if frame.visible and blocks:
            tip = frame.landmarks[INDEX_TIP, :2]
            d = [np.hypot(*(tip - np.array(b.px))) for b in blocks]
            i = int(np.argmin(d))
            if d[i] <= self.radius:
                target = blocks[i]
        key = None if target is None else (round(target.mm[0] / 10), round(target.mm[1] / 10))
        if key != self._fired:
            self._fired = None              # moved off the selected block: it can be selected again
        if key != self._key:                # pointing at something new (or nothing): restart
            self._key, self._since = key, t
            return None
        if key is not None and key != self._fired and t - self._since >= self.hold_s:
            self._fired = key               # fire once; must point away and back to re-select
            return target
        return None

    def reset(self) -> None:
        self._key, self._since, self._fired = None, 0.0, None


def hand_in_area(frame: HandFrame, area_poly: np.ndarray) -> bool:
    if not frame.visible or frame.landmarks is None:
        return False
    poly = area_poly.astype(np.float32)
    return any(cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0
               for x, y in frame.landmarks[:, :2])


class HandGate:
    """clear() is True once the hand has been out of the area for clear_s, False the moment it's back."""

    def __init__(self, area_poly: np.ndarray, clear_s: float):
        self.poly, self.clear_s = area_poly, clear_s
        self._out_since: float | None = None
        self.inside = True

    def update(self, frame: HandFrame, t: float) -> bool:
        self.inside = hand_in_area(frame, self.poly)
        if self.inside:
            self._out_since = None
        elif self._out_since is None:
            self._out_since = t
        return self.clear(t)

    def clear(self, t: float) -> bool:
        return not self.inside and self._out_since is not None and t - self._out_since >= self.clear_s
