"""Move-to-point (2026-11-15): point -> IK -> goal, and the controller's goal/target split."""
import asyncio
import json
import math
import time

import pytest
from fastapi.testclient import TestClient

from arm.calibration import load_calibration
from arm.comms.link import FakeNano
from arm.config import load_arm
from arm.control import Controller
from arm.kinematics import JointAngles, fk
from arm.targets import point_to_joints
from arm.web.server import create_app


@pytest.fixture
def arm():
    return load_arm()


# ------------------------------------------------------------------ point_to_joints
def test_a_reachable_point_round_trips_through_fk(arm):
    deg = point_to_joints(arm, 150, 40, 30, -90)
    x, y, z, phi = fk(arm.geometry, JointAngles(*(math.radians(d) for d in deg)))
    assert (x, y, z) == pytest.approx((150, 40, 30), abs=0.01)
    assert math.degrees(phi) == pytest.approx(-90, abs=0.01)


@pytest.mark.parametrize("x, y, z, why", [
    (40, 0, 50, "workspace"),     # inside the base
    (500, 0, 50, "workspace"),    # far out of reach
    (150, 0, 0, "workspace"),     # into the table
])
def test_points_outside_the_workspace_are_refused(arm, x, y, z, why):
    with pytest.raises(ValueError, match=why):
        point_to_joints(arm, x, y, z, -90)


def test_a_point_ik_cannot_reach_is_refused(arm):
    ws = arm.workspace
    # inside the workspace box but far too high for the arm with the gripper pointing down
    with pytest.raises(ValueError):
        point_to_joints(arm, ws["r_max"], 0, ws["z_max"], -90)


# ------------------------------------------------------------------ controller: goal vs target
def test_set_target_sets_the_goal_not_the_sent_pulses(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        park_us = c.target_us
        why = c.set_target(point_to_joints(arm, 150, 0, 60, -90) + [30])
        same = c.target_us == park_us       # nothing jumps on the call itself
        await c.disarm()
        return why, same, c.goal_values

    why, same, goal = asyncio.run(go())
    assert why is None and same and goal[4] == 30


def test_heartbeat_moves_the_sent_pose_toward_the_goal(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        goal = point_to_joints(arm, 150, 0, 60, -90) + [30]
        c.set_target(goal)
        await asyncio.sleep(0.2)
        await c.disarm()
        return c.target_values, goal

    target, goal = asyncio.run(go())
    # with the jump stub this lands on the goal; with Vyom's ramp it is partway there.
    # Either way every sent pose must be a valid one, and it moves the right way:
    assert abs(target[1] - goal[1]) < abs(90 - goal[1])


def test_max_step_comes_from_the_speed_limits(arm):
    c = Controller(FakeNano(), load_calibration(arm), heartbeat_hz=30)
    assert c.max_step[0] == pytest.approx(arm.speed_limits_deg_per_s["j0_base"] / 30)
    assert c.max_step[4] == pytest.approx(arm.raw["gripper_speed_mm_per_s"] / 30)


# ------------------------------------------------------------------ the web server
def test_point_over_the_websocket_is_accepted_or_explained(arm):
    with TestClient(create_app(FakeNano())) as client:
        cfg = client.get("/config").json()
        assert {"links", "workspace", "home", "base_limits"} <= cfg.keys()
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "arm"}))
            time.sleep(0.1)
            ws.send_text(json.dumps({"type": "point", "x": 150, "y": 0, "z": 60, "pitch": -90}))
            ws.send_text(json.dumps({"type": "point", "x": 40, "y": 0, "z": 60, "pitch": -90}))
            got = []
            while len([m for m in got if m["type"] in ("pose", "error")]) < 3:   # park pose + 2 replies
                got.append(json.loads(ws.receive_text()))
    replies = [m for m in got if m["type"] in ("pose", "error")]
    assert replies[1]["type"] == "pose" and replies[1]["point"]
    assert replies[2]["type"] == "error" and "NOT SENT" in replies[2]["msg"]


def test_a_heartbeat_crash_disarms_and_reports_instead_of_dying_silently(arm):
    # PR #11 review: an exception in the heartbeat used to kill the task with armed still True.
    async def go():
        nano = FakeNano()
        c = Controller(nano, load_calibration(arm))
        await c.arm()
        def boom():
            raise RuntimeError("simulated port failure")
        c._advance = boom
        await asyncio.sleep(0.15)
        return c, nano
    c, nano = asyncio.run(go())
    assert c.armed is False
    assert "simulated port failure" in c.status()["fault"]


def test_four_bar_elbow_servo_never_exceeds_the_j2_cap(arm):
    # PR #12 follow-up: shoulder up + elbow bend the same way = elbow SERVO moves the sum.
    c = Controller(FakeNano(), load_calibration(arm))
    cur = [0, 30, -100, -30, 30]
    c.target_values, c.goal_values = list(cur), [0, 90, -40, -30, 30]   # both +60 deg
    for _ in range(200):
        before = list(c.target_values)
        c._advance()
        servo = (c.target_values[1] - before[1]) + (c.target_values[2] - before[2])
        assert abs(servo) <= c.max_step[2] + 1e-9
    assert c.target_values == pytest.approx(c.goal_values)
