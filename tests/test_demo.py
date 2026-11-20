"""Demo controls (2026-11-20): saved poses, gripper/home buttons, the pick-and-place sequence."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from arm.calibration import load_calibration
from arm.comms.link import FakeNano
from arm.config import load_arm
from arm.control import Controller
from arm.demo import PoseStore, move_and_wait, run_sequence
from arm.web.server import create_app


@pytest.fixture
def arm():
    return load_arm()


def near_park(c, d0=0.0, grip=None):
    p = c.park_values()
    return [p[0] + d0] + p[1:4] + [p[4] if grip is None else grip]


# ------------------------------------------------------------------ PoseStore
def test_poses_survive_a_restart_in_the_order_saved(tmp_path):
    f = tmp_path / "poses.yaml"
    s = PoseStore(f)
    s.save("above block", [10, 60, -100, -30, 40])
    s.save("grab", [10, 50, -110, -20, 26])
    s.save("above block", [12, 60, -100, -30, 40])          # re-save updates in place
    again = PoseStore(f)
    assert again.names() == ["above block", "grab"]
    assert again.get("above block")[0] == 12


def test_bad_pose_names_and_sizes_are_refused(tmp_path):
    s = PoseStore(tmp_path / "p.yaml")
    with pytest.raises(ValueError):
        s.save("   ", [0, 0, 0, 0, 30])
    with pytest.raises(ValueError):
        s.save("x", [0, 0, 0])
    with pytest.raises(KeyError):
        s.get("nope")


# ------------------------------------------------------------------ moves and sequences
def test_move_and_wait_returns_once_the_ramp_has_arrived(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        want = near_park(c, d0=10)
        why = await move_and_wait(c, want)
        target = c.target_values
        await c.disarm()
        return why, target, want
    why, target, want = asyncio.run(go())
    assert why is None and target == want


def test_a_refused_pose_comes_back_with_the_reason(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        why = await move_and_wait(c, [0, 0, 0, 0, 999])      # gripper far out of range
        await c.disarm()
        return why
    assert "gripper" in asyncio.run(go())


def test_sequence_visits_every_pose_in_order(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        g = arm.raw["gripper"]
        steps = [("a", near_park(c, 8)), ("b", near_park(c, 8, g["closed_mm"])), ("c", near_park(c, 0))]
        seen = []

        async def on_step(i, name):
            seen.append(name)
        why = await run_sequence(c, steps, dwell_s=0.0, on_step=on_step)
        final = c.target_values
        await c.disarm()
        return why, seen, final, steps
    why, seen, final, steps = asyncio.run(go())
    assert why is None and seen == ["a", "b", "c"] and final == steps[-1][1]


def test_a_refusal_stops_the_whole_sequence_and_names_the_step(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        steps = [("ok", near_park(c, 5)), ("bad", [0, 0, 0, 0, 999]), ("never", near_park(c, 0))]
        why = await run_sequence(c, steps, dwell_s=0.0)
        await c.disarm()
        return why
    why = asyncio.run(go())
    assert why.startswith("step 2 (bad)")


def test_stop_interrupts_a_running_sequence(arm):
    async def go():
        c = Controller(FakeNano(), load_calibration(arm))
        await c.arm()
        stop = asyncio.Event()
        task = asyncio.create_task(run_sequence(c, [("far", near_park(c, 60))], stop=stop))
        await asyncio.sleep(0.2)
        stop.set()
        why = await task
        moved_part_way = c.target_values != near_park(c, 60)
        await c.disarm()
        return why, moved_part_way
    why, part = asyncio.run(go())
    assert why.endswith("stopped") and part


# ------------------------------------------------------------------ over the websocket
def test_buttons_save_goto_and_sequence_over_the_websocket(arm, tmp_path):
    with TestClient(create_app(FakeNano(), poses_path=tmp_path / "poses.yaml")) as client:
        with client.websocket_connect("/ws") as ws:
            def send(**m):
                ws.send_text(json.dumps(m))

            def wait_for(pred, limit=200):
                for _ in range(limit):
                    m = json.loads(ws.receive_text())
                    if pred(m):
                        return m
                raise AssertionError("message never came")

            send(type="arm"); time.sleep(0.1)
            send(type="gripper", open=False)
            closed = wait_for(lambda m: m["type"] == "pose" and m.get("point"))
            assert closed["values"][4] == arm.raw["gripper"]["closed_mm"]
            send(type="home")
            wait_for(lambda m: m["type"] == "pose" and m.get("point"))
            time.sleep(1.5)                                      # let the ramp reach home
            send(type="save_pose", name="home-closed")
            wait_for(lambda m: m["type"] == "info" and "saved" in m["msg"])
            send(type="gripper", open=True)
            send(type="run_sequence")
            done = wait_for(lambda m: m["type"] in ("info", "error") and "sequence" in m["msg"])
            assert done["type"] == "info" and "done" in done["msg"], done
            st = wait_for(lambda m: m["type"] == "status")
            assert st["poses"] == ["home-closed"] and not st["sequence_running"]
