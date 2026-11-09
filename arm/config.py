"""Load config/arm.yaml into the kinematics types (degrees in the file, radians in the code)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from arm.kinematics import ArmGeometry, JointAngles, JointLimits, ik

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "arm.yaml"
JOINTS = ("j0_base", "j1_shoulder", "j2_elbow", "j3_wrist")


@dataclass(frozen=True)
class ArmConfig:
    geometry: ArmGeometry
    limits: JointLimits
    windows: JointLimits  # the servo's full 180 degrees, in joint angles
    home: JointAngles
    park: JointAngles
    workspace: dict
    speed_limits_deg_per_s: dict
    raw: dict  # the whole file, for anything not wrapped above


def _range(pair) -> tuple[float, float]:
    lo, hi = (math.radians(v) for v in pair)
    if lo >= hi:
        raise ValueError(f"range {pair} must be [low, high]")
    return lo, hi


def _joint_set(joints: dict, key: str) -> JointLimits:
    return JointLimits(*(_range(joints[name][key]) for name in JOINTS))


def load_arm(path: Path | str = DEFAULT_PATH) -> ArmConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    geometry = ArmGeometry(**raw["links"])
    limits = _joint_set(raw["joints"], "limits")
    windows = _joint_set(raw["joints"], "window")

    for name, (lo, hi), (wlo, whi) in zip(JOINTS, vars(limits).values(), vars(windows).values()):
        if lo < wlo or hi > whi:
            raise ValueError(f"{name}: limits must sit inside the servo window")
        if whi - wlo > math.radians(180) + 1e-9:
            raise ValueError(f"{name}: window is wider than the servo's 180 degrees")

    h = raw["poses"]["home"]
    home = ik(geometry, h["x"], h["y"], h["z"], math.radians(h["pitch"]), limits=limits)
    p = raw["poses"]["park"]
    park = JointAngles(*(math.radians(p[k]) for k in ("theta0", "theta1", "theta2", "theta3")))
    limits.check(park)

    return ArmConfig(
        geometry=geometry,
        limits=limits,
        windows=windows,
        home=home,
        park=park,
        workspace=raw["workspace"],
        speed_limits_deg_per_s=raw["speed_limits_deg_per_s"],
        raw=raw,
    )
