"""V2-5: hand position -> gripper target (2026-11-20).

    HandFrame (pixels) + pinch (0..1) [+ distance_cm from V2-6]
        -> Target: x, y, z (mm), pitch (deg), gripper (mm), joints (or why it was refused)

This module only decides WHERE. Whether the arm may go there is decided by
arm.targets.point_to_joints (workspace, IK, joint limits, base clearance), and how fast by the
Controller's ramp. A refused target is reported, never swapped for a "nearby" one: the modes
layer (V2-7) holds the last good pose instead.

Steps, in order:
  1. Hand point = palm centre (mean of the wrist and the four finger knuckles): steadier than any
     single landmark, and it doesn't move when the fingers pinch.
  2. Image position -> 0..1 inside the HAND BOX (the middle of the image; tracking is shaky at
     the edges), mirrored so moving your hand right moves the arm right.
  3. 0..1 -> the WORK BOX (a small box around the pick area, config/gestures.yaml `mapping`).
  4. Clamp to the work box, then to the arm's workspace ring (r_min..r_max, z_min..z_max).
     `clamped` says it happened, so the page can show "hand outside the box".
  5. IK through point_to_joints. If it refuses: `joints` is None and `refused` says why.

Filter (V2-4) and depth (V2-6) plug in without changes here: pass `smooth=` a callable
f(t, (x, y, z)) -> (x, y, z), and `distance_cm=` to map(). Until they exist, positions go
straight through and reach is fixed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import yaml

from arm.config import ArmConfig
from arm.targets import point_to_joints
from arm.vision.hands import HandFrame

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "gestures.yaml"
PALM_POINTS = [0, 5, 9, 13, 17]          # wrist + the four finger knuckles


def load_mapping_config(path: Path | str = DEFAULT_PATH) -> dict:
    m = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["mapping"]
    if m["axes"] not in ("A", "B"):
        raise ValueError(f"mapping.axes must be A or B, got {m['axes']!r}")
    for k in ("x", "y", "z"):
        lo, hi = m["work_box"][k]
        if lo >= hi:
            raise ValueError(f"mapping.work_box.{k}: {lo} must be below {hi}")
    return m


@dataclass
class Target:
    x: float
    y: float
    z: float
    pitch: float
    gripper_mm: float
    clamped: bool = False                 # the hand was outside the hand box / workspace
    joints: list[float] | None = None     # [j0..j3] degrees; None when refused
    refused: str | None = None            # why point_to_joints said no
    hand_uv: tuple[float, float] = field(default=(0.0, 0.0))   # 0..1 position inside the hand box

    def pose(self) -> list[float] | None:
        """The 5 values Controller.set_target() takes, or None if refused."""
        return None if self.joints is None else self.joints + [self.gripper_mm]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class HandMapper:
    def __init__(self, arm: ArmConfig, cfg: dict | None = None,
                 smooth: Callable[[float, tuple], tuple] | None = None):
        self.arm = arm
        self.cfg = cfg or load_mapping_config()
        self.smooth = smooth              # V2-4 filter; None = pass straight through

    def hand_uv(self, frame: HandFrame) -> tuple[float, float, bool]:
        """Palm centre -> (u, v) in 0..1 across the hand box, mirrored; plus 'was outside'."""
        c = frame.landmarks[PALM_POINTS, :2].mean(axis=0)
        u, v = c[0] / frame.width, c[1] / frame.height
        u0, u1, v0, v1 = self.cfg["hand_box"]
        su, sv = (u - u0) / (u1 - u0), (v - v0) / (v1 - v0)
        outside = not (0.0 <= su <= 1.0 and 0.0 <= sv <= 1.0)
        su, sv = min(1.0, max(0.0, su)), min(1.0, max(0.0, sv))
        if self.cfg["mirror"]:
            su = 1.0 - su                 # camera faces you: your right is the image's left
        return su, sv, outside

    def map(self, frame: HandFrame, pinch: float, distance_cm: float | None = None) -> Target | None:
        """One frame -> a Target, or None when no hand is visible (the dead-man case)."""
        if not frame.visible or frame.landmarks is None:
            return None
        m, wb = self.cfg, self.cfg["work_box"]
        su, sv, clamped = self.hand_uv(frame)

        # su: 0 = arm's right ... 1 = arm's left   (+y is the arm's LEFT)
        # sv: 0 = top of the image ... 1 = bottom
        y = _lerp(wb["y"][0], wb["y"][1], su)
        if m["axes"] == "A":
            z = _lerp(wb["z"][1], wb["z"][0], sv)           # hand up -> arm up
            if distance_cm is None:
                x = float(m["fixed_reach_mm"])
            else:                                           # nearer the camera -> further out
                near, far = m["depth_cm"]
                t = min(1.0, max(0.0, (distance_cm - near) / (far - near)))
                x = _lerp(wb["x"][1], wb["x"][0], t)
        else:                                               # B: image up/down -> reach
            x = _lerp(wb["x"][1], wb["x"][0], sv)           # hand up -> further out
            z = float(m["fixed_z_mm"])

        if self.smooth is not None:
            x, y, z = self.smooth(frame.t, (x, y, z))

        x, y, z, c2 = self._clamp(x, y, z)
        g = self.arm.raw["gripper"]
        grip = round(_lerp(g["closed_mm"], g["open_mm"], min(1.0, max(0.0, pinch))), 1)
        t = Target(round(x, 1), round(y, 1), round(z, 1), float(m["pitch_deg"]), grip,
                   clamped or c2, hand_uv=(round(su, 3), round(sv, 3)))
        try:
            t.joints = point_to_joints(self.arm, t.x, t.y, t.z, t.pitch)
        except ValueError as e:
            t.refused = str(e)
        return t

    def _clamp(self, x: float, y: float, z: float) -> tuple[float, float, float, bool]:
        """Into the work box, then into the arm's workspace ring. Returns (x, y, z, changed)."""
        wb, ws = self.cfg["work_box"], self.arm.workspace
        x0, y0, z0 = x, y, z
        x = min(max(x, wb["x"][0]), wb["x"][1])
        y = min(max(y, wb["y"][0]), wb["y"][1])
        z = min(max(z, wb["z"][0]), wb["z"][1], ws["z_max"])
        z = max(z, ws["z_min"])
        r = math.hypot(x, y)               # the workspace is a RING round the base, not a box:
        if r > ws["r_max"] or r < ws["r_min"]:   # pull the point along its own direction
            k = min(max(r, ws["r_min"]), ws["r_max"]) / r
            x, y = x * k, y * k
        changed = not np.allclose((x, y, z), (x0, y0, z0), atol=1e-6)
        return x, y, z, changed
