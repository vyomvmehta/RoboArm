"""Block detection (V2-16): find the coloured blocks on the table in a camera frame.

HSV colour threshold -> clean up the mask -> blobs bigger than min_area_px -> each blob's
BOTTOM-centre. Bottom, not middle: the camera sees the block from the front at an angle, so the
blob's middle is partly the block's front face, higher than the table. The bottom edge of the
blob is where the block touches the table, which is what the table calibration maps correctly.
Then convert that point to arm-frame mm and keep only blocks inside the calibrated table area.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml

from arm.pick.table import TableCalibration

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "pick.yaml"


def load_pick_config(path: Path | str = DEFAULT_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@dataclass
class Block:
    px: tuple[float, float]      # image point used (bottom-centre of the blob)
    mm: tuple[float, float]      # arm-frame x, y on the table
    area: float                  # blob area, pixels
    box: tuple[int, int, int, int]   # x, y, w, h in the image (for drawing)


def colour_mask(frame_bgr: np.ndarray, cfg: dict) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in cfg["block"]["hsv_ranges"]:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    k = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)     # drop speckles
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)    # fill small holes


def detect_blocks(frame_bgr: np.ndarray, cal: TableCalibration, cfg: dict) -> list[Block]:
    mask = colour_mask(frame_bgr, cfg)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_poly = cal.area_polygon().astype(np.float32)
    out = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < cfg["block"]["min_area_px"]:
            continue
        x, y, w, h = cv2.boundingRect(c)
        foot = (x + w / 2.0, float(y + h))                # bottom-centre: where it meets the table
        if cv2.pointPolygonTest(area_poly, foot, False) < 0:
            continue                                      # not on the calibrated table area
        mm = cal.to_mm(np.array(foot))
        out.append(Block(foot, (float(mm[0]), float(mm[1])), float(a), (x, y, w, h)))
    return sorted(out, key=lambda b: -b.area)
