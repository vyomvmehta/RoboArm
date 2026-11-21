"""Hand shape -> numbers -> a gesture label (V2-2).

Everything is a RATIO to the palm size, so a hand 30 cm or 80 cm from the camera gives the same
answer. The thresholds live in config/gestures.yaml.

Labels:
  "fist"       all four fingers curled, thumb tucked         -> command: go home
  "palm"       all four fingers straight (thumb ignored)     -> command: hold / stop following
  "thumbs_up"  fingers curled, thumb out and pointing up     -> command: replay the last recording
  "none"       anything else (including a pinch: the pinch is continuous, see pinch_fraction)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "gestures.yaml"

WRIST, THUMB_MCP, THUMB_TIP, INDEX_MCP, INDEX_TIP = 0, 2, 4, 5, 8
FINGERS = {"index": (6, 8), "middle": (10, 12), "ring": (14, 16), "little": (18, 20)}  # (PIP, TIP)


@dataclass(frozen=True)
class GestureConfig:
    finger_extended_ratio: float
    thumb_extended_ratio: float
    thumbs_up_rise: float
    pinch_closed_ratio: float
    pinch_open_ratio: float
    hold_to_confirm_s: float
    min_visible_fraction: float


def load_gesture_config(path: Path | str = DEFAULT_PATH) -> GestureConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for k in ("mapping", "modes", "depth"):   # sections read by arm/mapping, arm/modes, arm/vision/depth
        raw.pop(k, None)
    return GestureConfig(**raw)


def _d(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a)[:2] - np.asarray(b)[:2]))   # image plane only: z is noisy


def features(lm: np.ndarray, cfg: GestureConfig) -> dict:
    """(21, 3) landmarks -> the numbers the classifier and the mapping use."""
    palm = _d(lm[WRIST], lm[9])
    if palm < 1e-6:
        raise ValueError("degenerate hand: palm size 0")
    ext = {name: _d(lm[WRIST], lm[tip]) / max(_d(lm[WRIST], lm[pip]), 1e-6) > cfg.finger_extended_ratio
           for name, (pip, tip) in FINGERS.items()}
    thumb_out = _d(lm[THUMB_TIP], lm[INDEX_MCP]) / palm > cfg.thumb_extended_ratio
    thumb_rise = (lm[THUMB_MCP][1] - lm[THUMB_TIP][1]) / palm      # image y points DOWN
    return {
        "palm": palm,
        "pinch_ratio": _d(lm[THUMB_TIP], lm[INDEX_TIP]) / palm,
        "extended": ext,
        "n_extended": sum(ext.values()),
        "thumb_out": thumb_out,
        "thumb_rise": thumb_rise,
    }


def classify(lm: np.ndarray, cfg: GestureConfig) -> str:
    f = features(lm, cfg)
    if f["n_extended"] == 4:
        # Thumb ignored for the palm (Nov 20 clips): on a real open palm the thumb tip sits
        # 0.32-0.63 palm from the index knuckle, overlapping a tucked thumb in a fist
        # (0.23-0.51), so it can't separate them. Four straight fingers already does.
        return "palm"
    if f["n_extended"] == 0:
        if f["thumb_out"] and f["thumb_rise"] > cfg.thumbs_up_rise:
            return "thumbs_up"
        if not f["thumb_out"]:
            return "fist"
    return "none"


def pinch_fraction(lm: np.ndarray, cfg: GestureConfig) -> float:
    """0.0 = thumb and index touching (gripper closed) ... 1.0 = wide apart (gripper open)."""
    r = features(lm, cfg)["pinch_ratio"]
    span = cfg.pinch_open_ratio - cfg.pinch_closed_ratio
    return float(min(1.0, max(0.0, (r - cfg.pinch_closed_ratio) / span)))
