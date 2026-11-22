"""V2-1: webcam -> MediaPipe hand landmarks, plus a CSV recorder (2026-11-20).

  Camera       OpenCV capture (DirectShow on Windows: opens fast, no 5 s MSMF delay).
  HandTracker  MediaPipe Tasks HandLandmarker in VIDEO mode (it tracks between frames instead of
               re-detecting every frame: steadier and cheaper). One hand only.
  HandFrame    what every later stage consumes: time, visible?, 21 landmarks in PIXELS.
  save_csv / load_csv
               record a landmark stream once, then test the gestures, filter and mapping on it
               forever without a camera. This is what makes V2 testable.

Landmarks are stored in pixels (x, y from the top-left, z on the same scale as x) rather than
MediaPipe's 0..1 image units, because 0..1 is stretched differently in x and y on a 16:9
camera: a distance like the palm size would change just by turning the hand.

MediaPipe landmark numbers used later: 0 wrist; thumb 1-4; index 5-8; middle 9-12; ring 13-16;
little 17-20 (each finger: MCP knuckle, PIP, DIP, TIP).

Needs the .venv (Python 3.12) and models/hand_landmarker.task (docs/V2_TASKS.md V2-0).
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "hand_landmarker.task"
N = 21


@dataclass
class HandFrame:
    t: float                       # seconds since the start of the stream
    visible: bool
    landmarks: np.ndarray | None   # (21, 3) pixels; None when no hand is seen
    width: int = 0                 # image size, so later stages can normalise
    height: int = 0
    handedness: str = ""           # "Left" / "Right" as MediaPipe reports it
    score: float = 0.0             # MediaPipe's confidence in the handedness

    def palm_size(self) -> float:
        """Wrist -> middle-finger knuckle (0 -> 9) in pixels: the hand's own ruler.

        Gestures divide by it so they don't depend on how far the hand is from the camera, and
        the depth estimate (V2-6) uses it the other way round: smaller palm = further away.
        """
        if self.landmarks is None:
            return 0.0
        return float(np.linalg.norm(self.landmarks[9, :2] - self.landmarks[0, :2]))


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        import cv2
        api = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, api)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"camera {index} did not open (in use by another app? wrong index?)")

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("camera stopped giving frames")
        return frame                    # BGR, as OpenCV gives it

    def close(self):
        self.cap.release()


class HandTracker:
    def __init__(self, model: Path | str = MODEL, min_confidence: float = 0.5):
        from mediapipe.tasks.python import BaseOptions, vision
        if not Path(model).exists():
            raise FileNotFoundError(f"{model} missing: see docs/V2_TASKS.md V2-0")
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self._lm = vision.HandLandmarker.create_from_options(opts)
        self._last_ms = -1

    def process(self, frame_bgr, t: float) -> HandFrame:
        import cv2
        import mediapipe as mp
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        ms = max(int(t * 1000), self._last_ms + 1)     # VIDEO mode needs strictly rising timestamps
        self._last_ms = ms
        res = self._lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
        if not res.hand_landmarks:
            return HandFrame(t, False, None, w, h)
        pts = np.array([[p.x * w, p.y * h, p.z * w] for p in res.hand_landmarks[0]])
        cat = res.handedness[0][0] if res.handedness else None
        return HandFrame(t, True, pts, w, h,
                         cat.category_name if cat else "", float(cat.score) if cat else 0.0)

    def close(self):
        self._lm.close()


# ------------------------------------------------------------------ recording
def _header() -> list[str]:
    cols = ["t", "visible", "width", "height", "handedness", "score"]
    return cols + [f"{a}{i}" for i in range(N) for a in "xyz"]


def save_csv(frames: list[HandFrame], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_header())
        for fr in frames:
            pts = (fr.landmarks.reshape(-1).round(2).tolist() if fr.landmarks is not None
                   else [""] * (N * 3))
            w.writerow([f"{fr.t:.4f}", int(fr.visible), fr.width, fr.height,
                        fr.handedness, f"{fr.score:.3f}"] + pts)


def load_csv(path: Path | str) -> list[HandFrame]:
    out = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vis = row["visible"] == "1"
            pts = (np.array([[float(row[f"{a}{i}"]) for a in "xyz"] for i in range(N)])
                   if vis else None)
            out.append(HandFrame(float(row["t"]), vis, pts, int(row["width"]), int(row["height"]),
                                 row["handedness"], float(row["score"] or 0)))
    return out
