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
        await c.disarm(park_first=False)
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
        await c.disarm(park_first=False)
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


@pytest.mark.parametrize("elbow_step", [0.0, -1.5])
def test_a_frozen_elbow_does_not_freeze_or_reverse_the_arm(arm, elbow_step):
    # PR #15 review (Ishaan): elbow speed <= 0 holds theta2. The four-bar cap used to scale the
    # whole step by 0 (nothing ever moved, "moving" forever) or by a negative (moved away).
    c = Controller(FakeNano(), load_calibration(arm))
    c.max_step = list(c.max_step)
    c.max_step[2] = elbow_step
    cur = [0, 30, -100, -30, 30]
    c.target_values, c.goal_values = list(cur), [0, 90, -100, -30, 30]   # shoulder only
    c._advance()
    assert 30 < c.target_values[1] <= 30 + c.max_step[1] + 1e-9          # toward the goal, within its cap
    for _ in range(100):
        c._advance()
    assert c.target_values == pytest.approx(c.goal_values)
    assert c.status()["moving"] is False


def test_disarm_ramps_to_park_before_going_limp(arm):
    async def go():
        nano = FakeNano()
        c = Controller(nano, load_calibration(arm))
        await c.arm()
        park = c.park_values()
        c.set_target([park[0] + 20] + park[1:])     # move the base 20 deg away
        await asyncio.sleep(0.6)
        assert c.target_values != park
        task = asyncio.create_task(c.disarm())
        await asyncio.sleep(0.05)
        refused = c.set_target(park)                # new targets are refused while parking
        await task
        return c, park, refused
    c, park, refused = asyncio.run(go())
    assert c.target_values == park and not c.armed
    assert refused and "disarming" in refused


def test_disarm_without_park_first_goes_limp_at_once(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        park = c.park_values()
        c.set_target([park[0] + 20] + park[1:])
        await asyncio.sleep(0.3)
        await c.disarm(park_first=False)
        return c, park
    c, park = asyncio.run(go())
    assert not c.armed and c.target_values != park


def test_stop_now_during_parking_goes_limp_at_once_and_sends_d_once(arm):
    # PR #15 review (Ishaan): once Disarm was pressed there was no way to stop immediately.
    async def go():
        nano = FakeNano()
        c = Controller(nano, load_calibration(arm))
        await c.arm()
        park = c.park_values()
        c.set_target([park[0] + 60] + park[1:])
        await asyncio.sleep(1.0)                      # ~45 deg away from park
        parking = asyncio.create_task(c.disarm())     # 1st press: start the park ramp
        await asyncio.sleep(0.1)
        assert c.parking and c.armed
        t0 = asyncio.get_running_loop().time()
        await c.disarm(park_first=False)              # 2nd press: Stop now
        stop_s = asyncio.get_running_loop().time() - t0
        await parking
        return c, nano, park, stop_s
    c, nano, park, stop_s = asyncio.run(go())
    assert stop_s < 0.05 and not c.armed and not c.parking
    assert c.target_values != park                    # it stopped where it was
    assert sum(1 for line in nano.log if line.startswith(">> D,")) == 1


def test_a_refused_park_move_goes_limp_and_says_why(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        park = c.park_values()
        c.set_target([park[0] + 30] + park[1:])
        await asyncio.sleep(0.5)
        class Refusing:                                # stands in for #16's clearance rule
            arm, cal = c.cal.arm, c.cal.cal
            @staticmethod
            def to_pulses(values):
                raise ValueError("simulated: base clearance refused the step")
        c.cal = Refusing()
        t0 = asyncio.get_running_loop().time()
        await c.disarm()
        return c, asyncio.get_running_loop().time() - t0
    c, took = asyncio.run(go())
    assert not c.armed and took < 1.0                 # no 15 s wait
    assert "refused" in c.fault
