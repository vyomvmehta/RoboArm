"""Base clearance (D23, 2026-11-17): the 2D model against the Nov 17 SolidWorks check, and its hooks."""
import math

import pytest

from arm.calibration import load_calibration
from arm.clearance import base_collision
from arm.comms.link import FakeNano
from arm.config import load_arm
from arm.control import Controller
from arm.kinematics import ArmGeometry, JointAngles
from arm.targets import point_to_joints

# The CAD check used the Arm Human links (13 / 12 cm, cad/arm-shell). main's arm.yaml still has
# 11 / 10, so the pose list is checked against the CAD geometry the poses came from.
CAD = ArmGeometry(l1=130, l2=120, l3=88)

# (theta1, forearm absolute = theta1 + theta2, theta3), degrees.
# "near" (24, -80, -10) is NOT in this list: it was clear in the Nov 17 CAD check, which was run
# on the with-tray base (shoulder 174.5), and it is refused on the as-built no-tray base
# (shoulder 134.5). See test_near_pose_is_lost_without_the_electronics_tray below and D28.
CLEAR = [
    (46, -60, -30), (0, -34, -56), (114, -4, 4),                       # home, far, high
    (60, -30, -70), (60, -30, -80), (60, -30, -90), (60, -30, 50),    # wrist sweep
    (60, 50, -60),                                                    # elbow straight
    (90, -40, -20),                                                   # park (theta3 -20)
    (-20, -20, 0),                                                    # shoulder low, elbow straight
    (140, 120, -30), (140, 20, -30),                                  # shoulder back
    (0, 0, 0), (0, 0, -85), (0, 0, -90), (0, 0, 50),                  # flat reach
]
COLLIDE = [(60, -70, -30), (60, -75, -30), (-20, -150, -40)]


def angles(t1, forearm, t3):
    return JointAngles(0, math.radians(t1), math.radians(forearm - t1), math.radians(t3))


@pytest.fixture
def arm():
    return load_arm()


@pytest.mark.parametrize("pose", CLEAR)
def test_cad_clear_poses_are_clear(arm, pose):
    assert base_collision(CAD, angles(*pose), arm.base_clearance) is None


@pytest.mark.parametrize("pose", COLLIDE)
def test_cad_colliding_poses_are_refused(arm, pose):
    assert "into the base" in base_collision(CAD, angles(*pose), arm.base_clearance)


def test_near_pose_is_lost_without_the_electronics_tray(arm):
    """D28: dropping the 40 mm tray lowers the shoulder 174.5 -> 134.5 and costs one of the 20
    CAD-verified poses. At "near" the palm cover reaches r 100, z -126 from the shoulder axis,
    and the fixed base plate top is now at -128.5, so the 3 mm margin refuses it - by about
    half a millimetre. Fit a 40 mm spacer under the Shoulder Bracket, or print the tray, to get
    it back; do NOT widen the margin."""
    near = angles(24, -80, -10)
    reason = base_collision(CAD, near, arm.base_clearance)
    assert reason and "base plate" in reason

    with_tray = dict(arm.base_clearance, plate_top_below_shoulder=168.5)
    assert base_collision(CAD, near, with_tray) is None


def test_old_park_wrist_minus_40_dips_into_the_lid(arm):
    assert base_collision(CAD, angles(90, -40, -40), arm.base_clearance)


def test_park_and_home_are_clear_with_the_real_config(arm):
    assert base_collision(arm.geometry, arm.park, arm.base_clearance) is None
    assert base_collision(arm.geometry, arm.home, arm.base_clearance) is None


# ------------------------------------------------------------------ hooks
def armed_controller():
    """A controller at the park pose without the heartbeat task (we drive _advance by hand)."""
    c = Controller(FakeNano(), load_calibration(load_arm()))
    park = c.park_values()
    c.armed, c.target_values, c.goal_values = True, park, list(park)
    c.target_us = c.cal.to_pulses(park)
    return c


def test_set_target_refuses_a_colliding_goal():
    c = armed_controller()
    before = list(c.goal_values)
    why = c.set_target([0, 60, -130, -30, 40])          # shoulder 60, elbow -130
    assert why and "into the base" in why
    assert c.goal_values == before


def test_ramp_holds_where_the_straight_path_crosses_the_base():
    c = armed_controller()
    goal = [0, 100, -120, -100, 40]                      # clear, but the line from park dips in
    assert c.set_target(goal) is None
    for _ in range(300):
        c._advance()
        if c.blocked:
            break
    assert c.blocked and "into the base" in c.blocked
    assert c.goal_values == c.target_values != goal     # held short of the goal
    assert c._collision(c.target_values) is None         # and still clear
    assert c.status()["blocked"] == c.blocked
    assert c.status()["moving"] is False


def test_ramp_may_move_out_of_a_colliding_pose():
    c = armed_controller()
    inside = [0, 60, -130, -30, 40]
    c.target_values = inside                             # e.g. armed while folded into the base
    c.target_us = c.cal.to_pulses(inside)
    c.set_target(c.park_values())
    start = list(c.target_values)
    c._advance()
    assert c.target_values != start and c.blocked is None


def test_point_to_joints_refuses_a_colliding_solution(arm):
    """Clearance is the THIRD gate in point_to_joints, after the workspace box and IK, so a target
    has to get past the first two to exercise it at all.

    (90, 0, 5, -90) did not: r 90 is inside r_min and z 5 is below z_min, so the workspace box
    refused it first and this test was green on the wrong message, then red from 2026-11-24 when
    the message was checked. Any point that only fails the box tests the box, not the clearance.

    (152, 0, 40, -50) is r 152, z 40 - inside the box with room above both gates (r_min is 140
    here and 150 on fix/shoulder-recal) - and IK solves it at shoulder 43.7 / elbow -131.8 /
    wrist 38.1, which is 3.2 deg clear of the -135 elbow limit. That solution puts the palm cover
    8 mm inside the lid, so it is refused on geometry and not on the 3 mm margin: it stays refused
    with margin 0, and on the with-tray plate height as well, so neither D28 nor a margin change
    can flip it.
    """
    with pytest.raises(ValueError, match="into the base"):
        point_to_joints(arm, 152, 0, 40, -50)
