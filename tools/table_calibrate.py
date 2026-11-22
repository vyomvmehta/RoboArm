r"""V2-16 table calibration + live block check.

    .venv\Scripts\python tools\table_calibrate.py            click the 4 marks, saves config/table_calibration.yaml
    .venv\Scripts\python tools\table_calibrate.py --check    live: detected blocks with their arm-frame mm

Calibrate: tape 4 crosses on the table at the arm-frame spots in config/pick.yaml `marks_mm`
(measured from the base axis), then click them in that order: far-left, far-right, near-right,
near-left. r = redo, s = save, q = quit. Redo whenever the camera moves.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm.pick.blocks import detect_blocks, load_pick_config  # noqa: E402
from arm.pick.table import TableCalibration  # noqa: E402
from arm.vision.hands import Camera  # noqa: E402

ORDER = ["far-left", "far-right", "near-right", "near-left"]


def calibrate(cam, cfg):
    clicks = []
    win = "Click the 4 marks (r redo, s save, q quit)"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, lambda e, x, y, *_: clicks.append((x, y)) if e == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4 else None)
    while True:
        view = cam.read().copy()                 # NOT mirrored: clicks must be in real image pixels
        for i, p in enumerate(clicks):
            cv2.circle(view, p, 6, (0, 255, 255), -1)
            cv2.putText(view, ORDER[i], (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        msg = f"click {ORDER[len(clicks)]}" if len(clicks) < 4 else "s = save, r = redo"
        cv2.putText(view, msg, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        if len(clicks) == 4:
            cv2.polylines(view, [np.array(clicks, np.int32)], True, (0, 255, 255), 2)
        cv2.imshow(win, view)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("r"):
            clicks.clear()
        elif k == ord("s") and len(clicks) == 4:
            cal = TableCalibration(clicks, cfg["marks_mm"])
            cal.save()
            print("saved config/table_calibration.yaml")
            return
        elif k in (ord("q"), 27):
            return


def check(cam, cfg):
    cal = TableCalibration.load()
    poly = cal.area_polygon(cfg["safety"]["margin_px"]).astype(np.int32)
    while True:
        frame = cam.read()
        view = frame.copy()
        cv2.polylines(view, [poly], True, (0, 200, 255), 1)
        for b in detect_blocks(frame, cal, cfg):
            x, y, w, h = b.box
            cv2.rectangle(view, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(view, f"x{b.mm[0]:.0f} y{b.mm[1]:+.0f}", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("Blocks (q quits)", view)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            return


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    cfg, cam = load_pick_config(), Camera(a.camera)
    try:
        (check if a.check else calibrate)(cam, cfg)
    finally:
        cam.close()
        cv2.destroyAllWindows()
