"""Point-and-go: a gripper target (x, y, z, pitch) -> joint angles, or a clear "no" (2026-11-15).

Order of checks (CLAUDE.md section 5.2: reject, say why, send nothing):
  1. the workspace box in config/arm.yaml (cheap, and catches "inside the base" / "into the table")
  2. inverse kinematics with the joint limits (unreachable, or reachable only past a limit)
"""
from __future__ import annotations

import math

from arm.config import ArmConfig
from arm.kinematics import ik


def point_to_joints(cfg: ArmConfig, x: float, y: float, z: float, pitch_deg: float) -> list[float]:
    """Gripper tip (mm) + pitch (degrees, -90 = pointing down) -> [j0..j3] in degrees.

    Raises ValueError (or its subclasses UnreachableError / JointLimitError) with a reason.
    """
    ws = cfg.workspace
    r = math.hypot(x, y)
    if not ws["r_min"] <= r <= ws["r_max"]:
        raise ValueError(f"{r:.0f} mm from the base axis is outside the workspace "
                         f"({ws['r_min']}-{ws['r_max']} mm)")
    if not ws["z_min"] <= z <= ws["z_max"]:
        raise ValueError(f"z = {z:.0f} mm is outside the workspace ({ws['z_min']}-{ws['z_max']} mm)")
    a = ik(cfg.geometry, x, y, z, math.radians(pitch_deg), limits=cfg.limits)
    return [round(math.degrees(v), 3) for v in (a.theta0, a.theta1, a.theta2, a.theta3)]
