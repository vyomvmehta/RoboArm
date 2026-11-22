"""Table calibration (V2-16): camera pixels on the TABLE <-> arm-frame millimetres.

The front camera sees the table at an angle, so a square on the table looks like a trapezoid.
A homography (a 3x3 perspective map) undoes that, exactly, for points ON the table plane.
It is fitted once from 4 marks taped on the table at known arm-frame positions: click them in
the image (tools/table_calibrate.py) and the map is saved to config/table_calibration.yaml.

Only valid for points on the table surface: a fingertip held 5 cm above the table maps a bit
off. That's fine for SELECTING the nearest block, not for measuring the finger's position.
Redo it whenever the camera moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "table_calibration.yaml"


@dataclass
class TableCalibration:
    image_px: np.ndarray        # (4, 2) the marks as clicked in the image
    table_mm: np.ndarray        # (4, 2) the same marks in the arm frame (x, y mm)

    def __post_init__(self):
        self.image_px = np.asarray(self.image_px, dtype=np.float64).reshape(-1, 2)
        self.table_mm = np.asarray(self.table_mm, dtype=np.float64).reshape(-1, 2)
        if len(self.image_px) != 4 or len(self.table_mm) != 4:
            raise ValueError("table calibration needs exactly 4 marks")
        if abs(cv2.contourArea(self.image_px.astype(np.float32))) < 100:
            raise ValueError("the 4 marks are (nearly) on a line in the image: spread them out")
        self.H = cv2.getPerspectiveTransform(self.image_px.astype(np.float32),
                                             self.table_mm.astype(np.float32))
        self.H_inv = np.linalg.inv(self.H)

    def to_mm(self, px) -> np.ndarray:
        """(N, 2) or (2,) image pixels -> arm-frame mm on the table."""
        p = np.asarray(px, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(p, self.H).reshape(-1, 2)
        return out[0] if np.ndim(px) == 1 else out

    def to_px(self, mm) -> np.ndarray:
        p = np.asarray(mm, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(p, self.H_inv).reshape(-1, 2)
        return out[0] if np.ndim(mm) == 1 else out

    def area_polygon(self, margin_px: float = 0.0) -> np.ndarray:
        """The 4 marks' outline in the image, grown by margin_px: the 'table area' for safety."""
        poly = self.image_px[cv2.convexHull(self.image_px.astype(np.float32), returnPoints=False).ravel()]
        if margin_px:
            c = poly.mean(axis=0)
            d = poly - c
            poly = c + d * (1 + margin_px / np.linalg.norm(d, axis=1, keepdims=True))
        return poly

    def save(self, path: Path | str = DEFAULT_PATH) -> None:
        Path(path).write_text(
            "# Table calibration (arm/pick/table.py). Redo it whenever the camera moves.\n"
            + yaml.safe_dump({"image_px": self.image_px.round(1).tolist(),
                              "table_mm": self.table_mm.round(1).tolist()}, sort_keys=False),
            encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "TableCalibration":
        if not Path(path).exists():
            raise FileNotFoundError(f"{path} missing: run tools/table_calibrate.py first")
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(raw["image_px"], raw["table_mm"])
