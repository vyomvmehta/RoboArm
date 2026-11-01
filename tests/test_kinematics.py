import math
import random

import pytest

from arm.kinematics import (
    ArmGeometry,
    JointAngles,
    JointLimitError,
    JointLimits,
    UnreachableError,
    fk,
    ik,
)

deg = math.radians

# Vyom's hand example: two equal links, no gripper, shoulder at the origin.
PLANAR = ArmGeometry(l1=120, l2=120, l3=0)
# Something closer to the real arm (placeholder lengths until the layout sketch).
ARM = ArmGeometry(l1=110, l2=100, l3=70, shoulder_height=60, shoulder_offset=15)


def test_fk_matches_hand_example():
    # Step 1 on paper: theta1 = 30 deg, theta2 = -60 deg -> tip at (207.8, 0).
    x, y, z, _ = fk(PLANAR, JointAngles(0, deg(30), deg(-60), 0))
    assert x == pytest.approx(207.846, abs=1e-3)
    assert y == pytest.approx(0, abs=1e-9)
    assert z == pytest.approx(0, abs=1e-9)


def test_ik_matches_hand_example():
    # Steps 2-3 on paper: target (180, 60) -> theta1 = 56.2 deg, theta2 = -75.5 deg.
    a = ik(PLANAR, 180, 0, 60, phi=0)
    assert math.degrees(a.theta1) == pytest.approx(56.19, abs=0.01)
    assert math.degrees(a.theta2) == pytest.approx(-75.52, abs=0.01)


@pytest.mark.parametrize("elbow_up", [True, False])
def test_round_trip_fk_ik_fk(elbow_up):
    # FK(IK(p)) == p for many random reachable poses.
    rng = random.Random(42)
    for _ in range(2000):
        bend = rng.uniform(deg(5), deg(170))
        start = JointAngles(
            theta0=rng.uniform(deg(-170), deg(170)),
            theta1=rng.uniform(deg(-30), deg(150)),
            theta2=-bend if elbow_up else bend,
            theta3=rng.uniform(deg(-120), deg(120)),
        )
        x, y, z, phi = fk(ARM, start)
        # IK only returns poses that face the target. Skip poses that reach back over
        # the base (tip behind the base axis) or sit on the axis, where yaw is ambiguous.
        planar_r, *_ = fk(ARM, JointAngles(0, start.theta1, start.theta2, start.theta3))
        if planar_r < 1:
            continue
        solved = ik(ARM, x, y, z, phi, elbow_up=elbow_up)
        x2, y2, z2, phi2 = fk(ARM, solved)
        assert (x2, y2, z2) == pytest.approx((x, y, z), abs=1e-6)
        assert phi2 == pytest.approx(phi, abs=1e-9)


def test_elbow_up_puts_elbow_above_the_wrist_line():
    a = ik(PLANAR, 180, 0, 60, phi=0, elbow_up=True)
    b = ik(PLANAR, 180, 0, 60, phi=0, elbow_up=False)
    elbow_z_up = 120 * math.sin(a.theta1)
    elbow_z_down = 120 * math.sin(b.theta1)
    assert elbow_z_up > elbow_z_down


def test_base_yaw_faces_the_target():
    a = ik(ARM, 0, 150, 60, phi=deg(-90))
    assert math.degrees(a.theta0) == pytest.approx(90)


def test_gripper_pointing_down_reaches_requested_pitch():
    a = ik(ARM, 150, 0, 20, phi=deg(-90))
    *_, phi = fk(ARM, a)
    assert math.degrees(phi) == pytest.approx(-90)


def test_full_reach_is_reachable_but_one_mm_more_is_not():
    ik(PLANAR, 240, 0, 0, phi=0)  # arm dead straight: exactly L1 + L2
    with pytest.raises(UnreachableError):
        ik(PLANAR, 241, 0, 0, phi=0)


def test_too_close_is_unreachable_with_unequal_links():
    geom = ArmGeometry(l1=120, l2=60, l3=0)  # cannot fold closer than 60 mm
    with pytest.raises(UnreachableError):
        ik(geom, 30, 0, 0, phi=0)


def test_joint_limits_reject_out_of_range_solution():
    limits = JointLimits(
        theta0=(deg(-90), deg(90)),
        theta1=(deg(0), deg(180)),
        theta2=(deg(-150), deg(0)),
        theta3=(deg(-90), deg(90)),
    )
    ik(PLANAR, 180, 0, 60, phi=0, limits=limits)  # fine
    with pytest.raises(JointLimitError):
        ik(PLANAR, -180, 0, 60, phi=0, limits=limits)  # behind the base: theta0 = 180 deg
