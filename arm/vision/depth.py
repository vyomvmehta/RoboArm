"""V2-6: hand distance from apparent palm size (single camera, 2026-11-21).

Physics: a pinhole camera images an object of real size L at distance Z with size
    s = f * L / Z            (f = focal length in pixels; similar triangles through the pinhole)
so  Z = a / s + b            with a = f * L, and b soaking up "where the tape starts" (camera
front vs pinhole, palm surface vs knuckles) plus small lens / MediaPipe bias.
Substituting u = 1 / s makes it a straight line, Z = a*u + b, solved by ordinary least squares.
Linear (Z = a*s + b) is only the tangent to that curve; inverse-square (a/s^2) is for AREAS.
`fit()` supports all three so the calibration tool can show the difference in the residuals.

The fit is tied to ONE camera, ONE capture resolution and ONE person's hand (a = f * L):
  - pixels per degree change with resolution / crop mode,  f changes with the camera,
  - L changes with the hand (two people's palms easily differ by 5-10% -> 5-10% in Z).
`Depth` therefore remembers the resolution it was calibrated at and warns loudly when a live
frame differs. Calibrate with tools/depth_calibrate.py; it writes the `depth:` section of
config/gestures.yaml.

Interface agreed in docs/V2_TASKS.md:  palm_px -> distance_cm   (Depth.__call__).
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import numpy as np
import yaml

from arm.vision.hands import HandFrame

log = logging.getLogger(__name__)
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "gestures.yaml"
SECTION_MARKER = "# ---------------------------------------------------------------- V2-6 depth"


# ------------------------------------------------------------------ palm-size measures
def _d(lm: np.ndarray, a: int, b: int) -> float:
    return float(np.linalg.norm(lm[a, :2] - lm[b, :2]))      # image plane only: MediaPipe z is noisy


def _polygon_area(lm: np.ndarray, idx: list[int]) -> float:
    x, y = lm[idx, 0], lm[idx, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


# All in pixels. "palm_triangle" is the default: three rigid palm bones pointing different ways
# (wrist->index knuckle, wrist->little knuckle, knuckle span), so tilting the hand shortens some
# and not others, and no finger joint is involved (pinch / fist don't change it). On Vyom's
# Nov 20 clips it had the lowest spread at a roughly fixed distance (8-13% vs 11-24% for
# wrist->middle knuckle). The others stay for comparison in the calibration tool.
MEASURES = {
    "palm_triangle": lambda lm: (_d(lm, 0, 5) + _d(lm, 0, 17) + _d(lm, 5, 17)) / 3,
    "wrist_mcp9": lambda lm: _d(lm, 0, 9),
    "mcp_span": lambda lm: _d(lm, 5, 17),
    "sqrt_palm_area": lambda lm: float(np.sqrt(_polygon_area(lm, [0, 5, 9, 13, 17]))),
    "bbox_diag": lambda lm: float(np.linalg.norm(lm[:, :2].max(axis=0) - lm[:, :2].min(axis=0))),
}


def palm_px(landmarks: np.ndarray, measure: str = "palm_triangle") -> float:
    if measure not in MEASURES:
        raise ValueError(f"unknown palm measure {measure!r}; pick one of {sorted(MEASURES)}")
    return MEASURES[measure](np.asarray(landmarks, dtype=float))


# ------------------------------------------------------------------ models + fitting
MODELS = {
    "linear": lambda s: s,                 # Z = a * s + b
    "inverse": lambda s: 1.0 / s,          # Z = a / s + b      (the physical one)
    "inverse_square": lambda s: 1.0 / s ** 2,
}


def predict(model: str, a: float, b: float, s) -> np.ndarray:
    return a * MODELS[model](np.asarray(s, dtype=float)) + b


def fit(sizes_px, dist_cm, model: str = "inverse") -> tuple[float, float, np.ndarray]:
    """Least squares Z = a * g(s) + b. Returns (a, b, residuals_cm) with residual = measured - fit."""
    s, z = np.asarray(sizes_px, dtype=float), np.asarray(dist_cm, dtype=float)
    if len(s) < 3:
        raise ValueError("need at least 3 distances (2 unknowns + 1 to check the fit)")
    if np.any(s <= 0):
        raise ValueError("palm sizes must be positive")
    g = MODELS[model](s)
    A = np.column_stack([g, np.ones_like(g)])
    (a, b), *_ = np.linalg.lstsq(A, z, rcond=None)
    return float(a), float(b), z - (a * g + b)


# ------------------------------------------------------------------ config
def load_depth_config(path: Path | str = DEFAULT_PATH) -> dict | None:
    """The `depth:` section, or None if not calibrated yet (mapping then uses fixed_reach_mm)."""
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")).get("depth")
    if not d:
        return None
    missing = {"model", "a", "b", "measure", "width", "height"} - set(d)
    if missing:
        raise ValueError(f"gestures.yaml depth: missing {sorted(missing)} (rerun tools/depth_calibrate.py)")
    if d["model"] not in MODELS:
        raise ValueError(f"gestures.yaml depth.model {d['model']!r} not one of {sorted(MODELS)}")
    return d


_UNCALIBRATED_LOGGED = False


def load_depth(path: Path | str = DEFAULT_PATH) -> "Depth | None":
    """Start-up helper: a ready Depth, or None while gestures.yaml has `depth: null`.

    None means "no depth": pass distance_cm=None to HandMapper.map and it keeps the reach at
    mapping.fixed_reach_mm. Logs that depth is uncalibrated ONCE per process (not per frame), and
    with no Depth object there is no resolution guard to fire: nothing is calibrated to guard."""
    global _UNCALIBRATED_LOGGED
    cfg = load_depth_config(path)
    if cfg is None:
        if not _UNCALIBRATED_LOGGED:
            _UNCALIBRATED_LOGGED = True
            log.warning("depth is uncalibrated (gestures.yaml depth: null): reach stays at "
                        "mapping.fixed_reach_mm. Run tools/depth_calibrate.py on the demo camera.")
        return None
    return Depth(cfg)


# A section header line in gestures.yaml: "# ---...--- <name>". The depth block runs from its own
# header to the next one (or the end of the file), so it can sit anywhere: other branches (V2-4
# filter) also append their section at the end, and a merge may put them after this one.
_SECTION_LINE = re.compile(r"^# -{20,} ", re.M)


def write_depth_section(cfg: dict, path: Path | str = DEFAULT_PATH, notes: str = "") -> None:
    """Replace ONLY the depth block of gestures.yaml (SECTION_MARKER up to the next section
    header or the end of the file); everything before and after it is kept byte for byte.
    Appends the block at the end if the marker is missing."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    i = text.find(SECTION_MARKER)
    if i < 0:
        head, tail = text, ""
    else:
        nxt = _SECTION_LINE.search(text, i + len(SECTION_MARKER))
        head, tail = text[:i], (text[nxt.start():] if nxt else "")
    head = head.rstrip("\n") + "\n\n"
    body = yaml.safe_dump({"depth": cfg}, sort_keys=False, default_flow_style=None, width=100)
    comment = "".join(f"# {ln}\n" if ln else "#\n" for ln in notes.strip("\n").splitlines())
    block = _section_header() + comment + body
    path.write_text(head + block + ("\n" + tail if tail else ""), encoding="utf-8")


def _section_header() -> str:
    return (SECTION_MARKER + " (arm/vision/depth.py)\n"
            "# WRITTEN BY tools/depth_calibrate.py: from the line above to the next '# ----' section\n"
            "# header (or the end of the file) is replaced on every calibration. Don't hand-edit it.\n"
            "# Z_cm = a * g(palm_px) + b, with g = 1/s (inverse), s (linear) or 1/s^2. Valid only for the\n"
            "# camera, resolution and hand below: Depth warns at runtime if the resolution differs.\n")


# ------------------------------------------------------------------ runtime
class Depth:
    """depth = Depth(load_depth_config());  distance_cm = depth(palm_px)
    or      distance_cm = depth.from_frame(hand_frame)   (also checks the resolution)."""

    def __init__(self, cfg: dict, warn_margin: float = 0.15):
        self.cfg = cfg
        self.model, self.a, self.b = cfg["model"], float(cfg["a"]), float(cfg["b"])
        self.measure = cfg["measure"]
        self.res = (int(cfg["width"]), int(cfg["height"]))
        lo, hi = cfg.get("fit_range_cm", [0, float("inf")])
        span = hi - lo
        self.valid_cm = (lo - warn_margin * span, hi + warn_margin * span)
        self.mismatch = False          # True once a frame at another resolution was seen: the page
        self._warned: set = set()      # should show it; distances are then NOT trustworthy

    def __call__(self, palm_px_value: float) -> float:
        if palm_px_value <= 0:
            raise ValueError("palm size must be positive")
        return float(predict(self.model, self.a, self.b, palm_px_value))

    def check_resolution(self, width: int, height: int) -> bool:
        """True if (width, height) matches the calibration. Warns LOUDLY once per new resolution."""
        if (width, height) == self.res:
            return True
        self.mismatch = True
        if (width, height) not in self._warned:
            self._warned.add((width, height))
            cam = self.cfg.get("camera_name", "?")
            msg = (f"DEPTH CALIBRATION MISMATCH: live frames are {width}x{height} but the depth fit in "
                   f"gestures.yaml was made at {self.res[0]}x{self.res[1]} on '{cam}'. Palm size is in "
                   f"pixels, so every distance from now on is WRONG. Capture at "
                   f"{self.res[0]}x{self.res[1]} or rerun tools/depth_calibrate.py.")
            bar = "!" * 100
            print(f"\n{bar}\n{msg}\n{bar}\n", file=sys.stderr, flush=True)
            log.warning(msg)
        return False

    def from_frame(self, frame: HandFrame) -> float | None:
        if not frame.visible or frame.landmarks is None:
            return None
        self.check_resolution(frame.width, frame.height)
        return self(palm_px(frame.landmarks, self.measure))

    def in_range(self, distance_cm: float) -> bool:
        """Inside the calibrated distances (plus a small margin): outside it is extrapolation."""
        return self.valid_cm[0] <= distance_cm <= self.valid_cm[1]

