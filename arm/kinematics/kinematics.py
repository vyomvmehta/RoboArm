"""Forward and inverse kinematics for the arm's positioning joints.

Joints (all angles in RADIANS; convert at the edges with math.radians/degrees):
    theta0  J0 base yaw: rotation about the vertical axis, 0 = facing +x.
    theta1  J1 shoulder: upper arm angle above horizontal.
    theta2  J2 elbow: bend relative to the upper arm's direction.
            0 = straight arm, negative = bends down (elbow-up poses have theta2 <= 0).
    theta3  J3 wrist pitch: bend relative to the forearm's direction.

Derived angle:
    phi     gripper pitch above horizontal = theta1 + theta2 + theta3.
            -pi/2 = gripper pointing straight down (picking pose).

Frame: origin on the base rotation axis at the height of the base frame; z up.
The shoulder axis sits `shoulder_height` above the origin and `shoulder_offset`
out from the base axis. The tip is the gripper's grasp point, `l3` from the wrist axis.

Derivation: Vyom, by hand, 2026-10-31 (docs/PROGRESS.md). The planar steps below
follow that recipe exactly: d, gamma (law of cosines), alpha (atan2), beta, theta1 = alpha + beta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Floating-point slack for "exactly at full reach" targets (mm-scale geometry).
_EPS = 1e-9


class UnreachableError(ValueError):
    """The target cannot be reached by any joint angles (too far or too close)."""


class JointLimitError(ValueError):
    """IK found angles, but at least one is outside its allowed range."""


@dataclass(frozen=True)
class ArmGeometry:
    l1: float  # shoulder axis -> elbow axis (mm)
    l2: float  # elbow axis -> wrist axis (mm)
    l3: float  # wrist axis -> gripper grasp point (mm)
    shoulder_height: float = 0.0  # shoulder axis above the frame origin (mm)
    shoulder_offset: float = 0.0  # shoulder axis out from the base axis (mm)


@dataclass(frozen=True)
class JointAngles:
    theta0: float
    theta1: float
    theta2: float
    theta3: float

    @property
    def phi(self) -> float:
        return self.theta1 + self.theta2 + self.theta3


@dataclass(frozen=True)
class JointLimits:
    """Allowed (min, max) per joint, radians, in joint coordinates (not servo angles)."""

    theta0: tuple[float, float]
    theta1: tuple[float, float]
    theta2: tuple[float, float]
    theta3: tuple[float, float]

    def check(self, angles: JointAngles) -> None:
        for name in ("theta0", "theta1", "theta2", "theta3"):
            lo, hi = getattr(self, name)
            value = getattr(angles, name)
            if not lo - _EPS <= value <= hi + _EPS:
                raise JointLimitError(
                    f"{name} = {math.degrees(value):.1f} deg is outside "
                    f"[{math.degrees(lo):.1f}, {math.degrees(hi):.1f}] deg"
                )


def fk(geom: ArmGeometry, angles: JointAngles) -> tuple[float, float, float, float]:
    """Joint angles -> gripper tip (x, y, z) in mm, plus gripper pitch phi in radians."""
    a1 = angles.theta1
    a12 = angles.theta1 + angles.theta2
    phi = angles.phi
    # Planar part: Vyom's Step 1 formulas, plus the shoulder offset/height and the gripper link.
    r = geom.shoulder_offset + geom.l1 * math.cos(a1) + geom.l2 * math.cos(a12) + geom.l3 * math.cos(phi)
    z = geom.shoulder_height + geom.l1 * math.sin(a1) + geom.l2 * math.sin(a12) + geom.l3 * math.sin(phi)
    # Base yaw swings the whole vertical plane around the z axis.
    return r * math.cos(angles.theta0), r * math.sin(angles.theta0), z, phi


def ik(
    geom: ArmGeometry,
    x: float,
    y: float,
    z: float,
    phi: float,
    elbow_up: bool = True,
    limits: JointLimits | None = None,
) -> JointAngles:
    """Gripper tip (x, y, z) in mm with pitch phi (radians) -> joint angles.

    The base always turns to face the target (theta0 = atan2(y, x)); poses that reach
    back over the top of the base are never returned. With a shoulder offset those can
    differ, so a point reachable "over the top" may be reported unreachable here.

    Raises UnreachableError if no solution exists, JointLimitError if `limits`
    is given and the solution violates it.
    """
    # 1. Base: face the target, then work in the arm's vertical plane.
    theta0 = math.atan2(y, x)
    r = math.hypot(x, y) - geom.shoulder_offset
    zs = z - geom.shoulder_height

    # 2. Step back from the tip along the gripper to find where the wrist axis must be.
    rw = r - geom.l3 * math.cos(phi)
    zw = zs - geom.l3 * math.sin(phi)

    # 3. Two-link problem for the wrist point (shoulder -> elbow -> wrist).
    d = math.hypot(rw, zw)
    if d < _EPS:
        raise UnreachableError("wrist point coincides with the shoulder axis")

    cos_gamma = (geom.l1**2 + geom.l2**2 - d**2) / (2 * geom.l1 * geom.l2)
    if not -1 - _EPS <= cos_gamma <= 1 + _EPS:
        # The bonus question: no triangle exists, so acos would fail.
        raise UnreachableError(
            f"wrist point is {d:.1f} mm from the shoulder; reachable range is "
            f"{abs(geom.l1 - geom.l2):.1f}-{geom.l1 + geom.l2:.1f} mm"
        )
    gamma = math.acos(max(-1.0, min(1.0, cos_gamma)))  # inner angle at the elbow
    bend = math.pi - gamma

    alpha = math.atan2(zw, rw)  # d line above horizontal
    cos_beta = (geom.l1**2 + d**2 - geom.l2**2) / (2 * geom.l1 * d)
    beta = math.acos(max(-1.0, min(1.0, cos_beta)))  # triangle corner at the shoulder

    if elbow_up:
        theta1, theta2 = alpha + beta, -bend
    else:
        theta1, theta2 = alpha - beta, bend

    # 4. Wrist makes up the rest of the requested gripper pitch.
    theta3 = phi - theta1 - theta2

    angles = JointAngles(theta0, theta1, theta2, theta3)
    if limits is not None:
        limits.check(angles)
    return angles
