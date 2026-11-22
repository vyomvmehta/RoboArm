"""V2-16 point-to-pick, hardware-free parts (Nov 20): table calibration, blocks, pointing,
the hand-clear safety gate and the pick routine. Synthetic images and hands only."""
import asyncio

import cv2
import numpy as np
import pytest

from arm.calibration import load_calibration
from arm.comms.link import FakeNano
from arm.config import load_arm
from arm.control import Controller
from arm.pick.blocks import detect_blocks, load_pick_config
from arm.pick.routine import PickRefused, pick_steps, run_pick
from arm.pick.select import HandGate, PointSelector, hand_in_area
from arm.pick.table import TableCalibration
from arm.vision.hands import HandFrame

ARM, CFG = load_arm(), load_pick_config()
W, H = 1280, 720
# A front camera looking down at the table: the far edge of the table looks narrower (trapezoid).
MARKS_PX = [[440, 300], [840, 300], [1040, 650], [240, 650]]       # far-left, far-right, near-right, near-left
MARKS_MM = [[220, 100], [220, -100], [120, -100], [120, 100]]      # arm frame: x forward, +y = arm's left


@pytest.fixture
def cal():
    return TableCalibration(MARKS_PX, MARKS_MM)


def table_image(cal, blocks_mm, size_px=36):
    """Grey table, red blocks drawn with their bottom-centre at the given arm-frame points."""
    img = np.full((H, W, 3), 170, np.uint8)
    for mm in blocks_mm:
        x, y = cal.to_px(np.array(mm)).astype(int)
        cv2.rectangle(img, (x - size_px // 2, y - size_px), (x + size_px // 2, y), (30, 30, 220), -1)
    return img


def hand_with_tip(px, t=0.0):
    lm = np.tile(np.array([[px[0], px[1] + 150, 0.0]]), (21, 1))     # palm well below the tip
    lm[8] = (px[0], px[1], 0)
    return HandFrame(t, True, lm, W, H)


# ------------------------------------------------------------------ calibration
def test_the_four_marks_map_exactly_and_round_trip(cal):
    assert np.allclose(cal.to_mm(np.array(MARKS_PX, float)), MARKS_MM, atol=1e-6)
    p = np.array([170.0, 30.0])
    assert np.allclose(cal.to_mm(cal.to_px(p)), p, atol=1e-6)


def test_marks_on_a_line_are_refused():
    with pytest.raises(ValueError):
        TableCalibration([[0, 0], [100, 0], [200, 0], [300, 0]], MARKS_MM)


def test_calibration_saves_and_loads(cal, tmp_path):
    cal.save(tmp_path / "t.yaml")
    back = TableCalibration.load(tmp_path / "t.yaml")
    assert np.allclose(back.to_mm(np.array([600.0, 500.0])), cal.to_mm(np.array([600.0, 500.0])), atol=0.1)


# ------------------------------------------------------------------ blocks
def test_blocks_are_found_at_their_table_position(cal):
    truth = [(170, 40), (150, -60)]
    found = detect_blocks(table_image(cal, truth), cal, CFG)
    assert len(found) == 2
    for t in truth:
        assert min(np.hypot(*(np.array(b.mm) - t)) for b in found) < 5      # within 5 mm


def test_a_block_off_the_table_area_and_specks_are_ignored(cal):
    img = table_image(cal, [(170, 0)])
    cv2.rectangle(img, (20, 20), (70, 70), (30, 30, 220), -1)     # red thing outside the marks
    cv2.circle(img, (640, 500), 3, (30, 30, 220), -1)              # a red speck
    found = detect_blocks(img, cal, CFG)
    assert len(found) == 1 and abs(found[0].mm[0] - 170) < 5


# ------------------------------------------------------------------ pointing
def test_holding_the_fingertip_on_a_block_selects_it_once(cal):
    blocks = detect_blocks(table_image(cal, [(170, 40), (150, -60)]), cal, CFG)
    sel, tip = PointSelector(CFG), blocks[0].px
    picked = [sel.update(hand_with_tip(tip, i / 30), blocks, i / 30) for i in range(40)]
    hits = [p for p in picked if p]
    assert len(hits) == 1 and hits[0].mm == blocks[0].mm
    assert picked.index(hits[0]) / 30 >= CFG["select"]["hold_s"] - 1e-9


def test_sweeping_past_a_block_does_not_select_it(cal):
    blocks = detect_blocks(table_image(cal, [(170, 40)]), cal, CFG)
    sel, (bx, by) = PointSelector(CFG), blocks[0].px
    path = [(bx - 200 + 20 * i, by) for i in range(21)]            # crosses the block in ~0.15 s
    assert not any(sel.update(hand_with_tip(p, i / 30), blocks, i / 30) for i, p in enumerate(path))


# ------------------------------------------------------------------ safety gate
def test_the_gate_opens_only_after_the_hand_has_been_out_long_enough(cal):
    poly = cal.area_polygon(CFG["safety"]["margin_px"])
    gate = HandGate(poly, CFG["safety"]["clear_s"])
    inside, outside = hand_with_tip((640, 500)), hand_with_tip((640, 40))
    outside.landmarks[:, 1] = 40                                    # whole hand above the table area
    assert hand_in_area(inside, poly) and not hand_in_area(outside, poly)
    assert not gate.update(inside, 0.0)
    assert not gate.update(outside, 0.1)
    assert gate.update(outside, 0.1 + CFG["safety"]["clear_s"])
    assert not gate.update(inside, 1.0)                             # back in: closed at once


# ------------------------------------------------------------------ the routine
def test_a_reachable_block_gives_a_checked_nine_step_pick():
    steps = pick_steps(ARM, (165, 0), CFG)
    assert [n for n, _ in steps][:4] == ["above block", "down", "grab", "lift"]
    assert len(steps) == 9 and all(len(p) == 5 for _, p in steps)
    g = ARM.raw["gripper"]
    assert dict(steps)["down"][4] == g["open_mm"] and dict(steps)["grab"][4] == g["closed_mm"]


def test_an_unreachable_block_is_refused_before_anything_moves():
    with pytest.raises(PickRefused, match="above block"):
        pick_steps(ARM, (400, 0), CFG)


def test_the_pick_runs_to_the_end_when_the_hand_stays_away():
    async def go():
        c = Controller(FakeNano(), load_calibration(ARM))
        await c.arm()
        steps = pick_steps(ARM, (165, 0), CFG)
        why = await run_pick(c, steps, hand_clear=lambda: True, dwell_s=0.0)
        final = c.target_values
        await c.disarm(park_first=False)
        return why, final, steps[-1][1]
    why, final, home = asyncio.run(go())
    assert why is None and final == home


def test_the_pick_stops_where_it_is_when_the_hand_comes_back():
    async def go():
        c = Controller(FakeNano(), load_calibration(ARM))
        await c.arm()
        clear = {"v": True}
        task = asyncio.create_task(run_pick(c, pick_steps(ARM, (165, 0), CFG),
                                            hand_clear=lambda: clear["v"], dwell_s=0.0))
        await asyncio.sleep(0.5)
        clear["v"] = False                                          # hand reaches in mid-move
        why = await task
        frozen = list(c.target_values)
        await asyncio.sleep(0.3)
        still = c.target_values == frozen                           # it stays put afterwards
        await c.disarm(park_first=False)
        return why, still
    why, still = asyncio.run(go())
    assert "hand came back" in why and still


def test_the_pick_will_not_start_with_a_hand_in_the_area():
    async def go():
        c = Controller(FakeNano(), load_calibration(ARM))
        await c.arm()
        why = await run_pick(c, pick_steps(ARM, (165, 0), CFG), hand_clear=lambda: False)
        await c.disarm(park_first=False)
        return why
    assert "move it away" in asyncio.run(go())
