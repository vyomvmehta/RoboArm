"""V2-7 modes (Nov 20): buttons + a still-palm exit (2 s), dead-man hold, record/replay, command
gestures, point-to-pick wiring. FakeNano controller; real clips + synthetic hands."""
import asyncio
import glob

import numpy as np
import pytest

from arm.calibration import load_calibration
from arm.comms.link import FakeNano
from arm.config import load_arm
from arm.control import Controller
from arm.gestures import load_gesture_config
from arm.modes import ModeMachine, RecordingStore
from arm.vision.hands import HandFrame, load_csv

import yaml

ARM, GCFG = load_arm(), load_gesture_config()
MCFG = yaml.safe_load(open("config/gestures.yaml", encoding="utf-8"))["modes"]
W, H = 1280, 720


def hand(shape="pinch", u=0.5, v=0.5, t=0.0, palm=150):
    """Synthetic hand at image fraction (u, v). shape: palm | fist | thumbs_up | pinch."""
    p = np.zeros((21, 3))
    for name, x, i in (("index", -30, 5), ("middle", 0, 9), ("ring", 25, 13), ("little", 48, 17)):
        p[i] = (x, -100, 0)
        straight = shape == "palm" or (shape == "pinch" and name != "index")
        p[i + 1:i + 4] = ([(x, -140, 0), (x, -165, 0), (x, -185, 0)] if straight
                          else [(x, -125, 0), (x, -100, 0), (x, -75, 0)])
    p[1], p[2] = (-35, -25, 0), (-60, -50, 0)
    p[3], p[4] = {"palm": [(-85, -70, 0), (-110, -85, 0)], "thumbs_up": [(-61, -120, 0), (-62, -180, 0)],
                  "fist": [(-40, -70, 0), (-15, -80, 0)], "pinch": [(-45, -90, 0), (-40, -95, 0)]}[shape]
    p *= palm / 100
    c = p[[0, 5, 9, 13, 17], :2].mean(axis=0)
    p[:, :2] += np.array([u * W, v * H]) - c
    return HandFrame(t, True, p, W, H)


def lost(t):
    return HandFrame(t, False, None, W, H)


async def machine(tmp_path, armed=True):
    c = Controller(FakeNano(), load_calibration(ARM))
    if armed:
        await c.arm()
    return c, ModeMachine(c, ARM, GCFG, MCFG, recordings=RecordingStore(tmp_path / "rec.yaml"))


async def feed(m, frames, dt=1 / 30):
    out = []
    for f in frames:
        out.append(await m.step(f))
        await asyncio.sleep(0)            # let the controller's heartbeat run now and then
    return out


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ follow + dead-man
def test_follow_sets_goals_from_the_hand(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        await feed(m, [hand("pinch", 0.5, 0.3, t=i / 30) for i in range(5)])
        g, park = list(c.goal_values), c.park_values()
        await c.disarm(park_first=False)
        return g, park
    goal, park = run(go())
    assert goal != park                                          # the hand moved the goal off park


def test_hand_lost_in_follow_holds_where_the_arm_is(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        await feed(m, [hand("pinch", 0.2, 0.2, t=0.0)])          # far target -> ramp starts
        await asyncio.sleep(0.3)
        st = await m.step(lost(0.4))
        held = list(c.target_values)
        await asyncio.sleep(0.3)
        await c.disarm(park_first=False)
        return st, held, c.goal_values
    st, held, goal = run(go())
    assert "hand lost" in st["refused"]
    assert goal == held                                          # does NOT carry on to the old goal


def test_the_sweep_clip_keeps_following_and_never_exits(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        frames = load_csv(sorted(glob.glob("runs/hands/sweep-*.csv"))[0])
        sts = await feed(m, frames)
        await c.disarm(park_first=False)
        return sts
    sts = run(go())
    assert all(s["mode"] == "follow" for s in sts)               # a moving open hand is not the exit


# ------------------------------------------------------------------ the exit gesture
def test_a_still_open_palm_for_2s_exits_to_command_and_holds(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        sts = await feed(m, [hand("palm", 0.5, 0.5, t=i / 30) for i in range(75)])   # 2.5 s still
        await c.disarm(park_first=False)
        return sts
    sts = run(go())
    exit_at = next(i for i, s in enumerate(sts) if s.get("confirmed") == "exit")
    assert 1.9 <= exit_at / 30 <= 2.2 and sts[-1]["mode"] == "command"


def test_a_palm_held_only_1s_does_not_exit(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        sts = await feed(m, [hand("palm", t=i / 30) for i in range(30)] +
                         [hand("pinch", t=1 + i / 30) for i in range(60)])
        await c.disarm(park_first=False)
        return sts
    assert all(s["mode"] == "follow" for s in run(go()))


def test_a_fist_inside_follow_is_ignored(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("follow")
        sts = await feed(m, [hand("fist", t=i / 30) for i in range(60)])
        await c.disarm(park_first=False)
        return sts
    assert all(s["mode"] == "follow" and s.get("confirmed") is None for s in run(go()))


# ------------------------------------------------------------------ command mode
def test_fist_in_command_mode_sends_the_arm_home(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("command")
        sts = await feed(m, [hand("fist", t=i / 30) for i in range(25)])
        goal = list(c.goal_values)
        await c.disarm(park_first=False)
        return sts, goal
    sts, goal = run(go())
    assert any(s["confirmed"] == "fist" for s in sts)
    from arm.targets import point_to_joints
    h = ARM.raw["poses"]["home"]
    assert goal[:4] == point_to_joints(ARM, h["x"], h["y"], h["z"], h["pitch"])


def test_thumbs_up_with_nothing_recorded_says_so(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("command")
        sts = await feed(m, [hand("thumbs_up", t=i / 30) for i in range(25)])
        await c.disarm(park_first=False)
        return sts
    assert any(s["refused"] and "nothing recorded" in s["refused"] for s in run(go()))


# ------------------------------------------------------------------ record + replay
def test_record_then_thumbs_up_replays_it(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        await m.set_mode("record")
        frames = [hand("pinch", 0.3 + 0.4 * i / 60, 0.4, t=i / 30) for i in range(60)]
        await feed(m, frames)
        await m.set_mode("command")                              # leaving record saves it
        rec = m.recordings.get()
        sts = await feed(m, [hand("thumbs_up", t=3 + i / 30) for i in range(25)])
        replaying = m.mode == "replay"
        await m.stop()
        await c.disarm(park_first=False)
        return rec, sts, replaying
    rec, sts, replaying = run(go())
    assert rec and len(rec) >= 5
    assert any(s["confirmed"] == "thumbs_up" for s in sts) and replaying


def test_replay_button_refuses_with_no_recording(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        why = await m.set_mode("replay")
        await c.disarm(park_first=False)
        return why
    assert "nothing recorded" in run(go())


# ------------------------------------------------------------------ guards
def test_nothing_is_sent_while_disarmed(tmp_path):
    async def go():
        c, m = await machine(tmp_path, armed=False)
        await m.set_mode("follow")
        await feed(m, [hand("pinch", 0.2, 0.2, t=i / 30) for i in range(10)])
        return c.goal_values
    assert run(go()) is None


def test_point_mode_needs_a_table_calibration(tmp_path):
    async def go():
        c, m = await machine(tmp_path)
        why = await m.set_mode("point")
        await c.disarm(park_first=False)
        return why
    assert "table calibration" in run(go())


# ------------------------------------------------------------------ point to pick, end to end
def test_point_selects_waits_for_the_hand_to_leave_then_picks(tmp_path):
    import cv2
    from arm.pick.blocks import load_pick_config
    from arm.pick.table import TableCalibration
    cal = TableCalibration([[440, 300], [840, 300], [1040, 650], [240, 650]],
                           [[220, 100], [220, -100], [120, -100], [120, 100]])
    pcfg = load_pick_config()
    pcfg["pick"]["dwell_s"] = 0.0
    img = np.full((H, W, 3), 170, np.uint8)
    bx, by = cal.to_px(np.array([165.0, 0.0])).astype(int)
    cv2.rectangle(img, (bx - 18, by - 36), (bx + 18, by), (30, 30, 220), -1)

    def tip_on_block(t):
        f = hand("pinch", t=t)
        f.landmarks[:, :2] += np.array([bx, by]) - f.landmarks[8, :2]
        return f

    def hand_away(t):
        f = hand("pinch", 0.5, 0.05, t=t)
        f.landmarks[:, 1] -= f.landmarks[:, 1].max() - 10        # whole hand above the table area
        return f

    async def go():
        c = Controller(FakeNano(), load_calibration(ARM))
        await c.arm()
        m = ModeMachine(c, ARM, GCFG, MCFG, recordings=RecordingStore(tmp_path / "r.yaml"),
                        pick={"cal": cal, "cfg": pcfg})
        assert await m.set_mode("point") is None
        t, picked_at_start = 0.0, None
        for _ in range(20):                                      # 0.67 s pointing at the block
            st = await m.step(tip_on_block(t), img); t += 1 / 30
            picked_at_start = picked_at_start or st.get("selected")
        goal_while_pointing = list(c.goal_values)
        for _ in range(900):                                     # hand away: the pick may start (~9 steps at 45 deg/s)
            st = await m.step(hand_away(t), img); t += 1 / 30
            await asyncio.sleep(1 / 30)
            if m._task and m._task.done():
                break
        why = m._task.result()
        await c.disarm(park_first=False)
        return picked_at_start, goal_while_pointing, c.park_values(), why
    selected, goal_pointing, park, why = run(go())
    assert selected and abs(selected[0] - 165) < 5
    assert goal_pointing == park                                 # nothing moved while the hand was on the table
    assert why is None                                           # full pick completed
