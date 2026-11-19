"""Base clearance: refuse joint poses that drive the forearm or hand into the base (2026-11-17).

Joint limits are a box; the base isn't. A SolidWorks full-assembly check (Nov 17: Arm Human +
flat-finger gripper on Siddharth's base, 20 poses) found poses inside the limits that put the
gripper into the lid/tray, e.g. shoulder 60 with the elbow folded to -130. This is the 2D model
that matched that check (see D23 in docs/DECISIONS.md).

Everything is in the arm's vertical plane, measured from the SHOULDER AXIS (r out, z up), so it
does not depend on shoulder_height. Numbers come from the `base_clearance:` section of
config/arm.yaml. The upper arm is not checked: in the CAD it never reached the base.

Obstacles (each grown by `margin`):
  - box + tray + lid, which turn with the arm:  |r| <= box_half and z <= -lid_below_shoulder
  - fixed base plate:                           |r| <= plate_r  and z <= -plate_top_below_shoulder
Arm parts, sampled as points:
  - forearm: a band of +-forearm_half_width around the elbow -> wrist line
  - hand: rectangles in the gripper frame (origin on the approach line, hand_origin_from_wrist
    out from the wrist axis; v along the approach d, u along X = (-d_z, d_r))
"""
from __future__ import annotations

import math

from arm.kinematics import ArmGeometry, JointAngles

_STEP_MM = 2.0  # sampling pitch; well under the 3 mm margin


def _span(lo: float, hi: float) -> list[float]:
    n = max(1, math.ceil((hi - lo) / _STEP_MM))
    return [lo + (hi - lo) * i / n for i in range(n + 1)]


def _points(geom: ArmGeometry, a: JointAngles, cfg: dict):
    """Yield (part, r, z) sample points, relative to the shoulder axis."""
    a1, a12, phi = a.theta1, a.theta1 + a.theta2, a.phi
    er, ez = geom.l1 * math.cos(a1), geom.l1 * math.sin(a1)              # elbow axis
    wr, wz = er + geom.l2 * math.cos(a12), ez + geom.l2 * math.sin(a12)  # wrist axis

    # Forearm band around elbow -> wrist.
    fr, fz = math.cos(a12), math.sin(a12)
    nr, nz = -fz, fr
    for s in _span(0.0, geom.l2):
        for w in _span(-cfg["forearm_half_width"], cfg["forearm_half_width"]):
            yield "forearm", er + s * fr + w * nr, ez + s * fz + w * nz

    # Hand, in the gripper frame.
    dr, dz = math.cos(phi), math.sin(phi)
    xr, xz = -dz, dr
    o = cfg["hand_origin_from_wrist"]
    or_, oz = wr + o * dr, wz + o * dz
    for part, (half_u, v_lo, v_hi) in (("hand (palm cover)", cfg["hand_body"]),
                                       ("hand (fingers)", cfg["hand_fingers"])):
        for v in _span(v_lo, v_hi):
            for u in _span(-half_u, half_u):
                yield part, or_ + v * dr + u * xr, oz + v * dz + u * xz


def base_collision(geom: ArmGeometry, angles: JointAngles, cfg: dict) -> str | None:
    """None if the forearm and hand clear the base, else a one-line reason."""
    m = cfg["margin"]
    box_r, box_z = cfg["box_half"] + m, -cfg["lid_below_shoulder"] + m
    plate_r, plate_z = cfg["plate_r"] + m, -cfg["plate_top_below_shoulder"] + m
    for part, r, z in _points(geom, angles, cfg):
        if abs(r) <= box_r and z <= box_z:
            where = "lid / tray"
        elif abs(r) <= plate_r and z <= plate_z:
            where = "base plate"
        else:
            continue
        return (f"pose would drive the {part} into the base {where} "
                f"(r {r:.0f}, z {z:.0f} mm from the shoulder axis)")
    return None
