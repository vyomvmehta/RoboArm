"""V2-5 mapping: hand -> gripper target, on Vyom's real clips + synthetic edge cases (Nov 20)."""
import glob

import numpy as np
import pytest

from arm.config import load_arm
from arm.gestures import load_gesture_config, pinch_fraction
from arm.mapping import HandMapper, load_mapping_config
from arm.vision.hands import HandFrame, load_csv

ARM, GCFG, MCFG = load_arm(), load_gesture_config(), load_mapping_config()
W, H = 1280, 720


def clip(name):
    return load_csv(sorted(glob.glob(f"runs/hands/{name}-*.csv"))[0])


def hand_at(u, v, palm=150):
    """A synthetic hand whose palm centre sits at image fraction (u, v)."""
    lm = np.zeros((21, 3))
    lm[0] = (0, 0, 0)
    for i, x in zip((5, 9, 13, 17), (-30, 0, 25, 48)):
        lm[i] = (x * palm / 100, -palm, 0)
    centre = lm[[0, 5, 9, 13, 17], :2].mean(axis=0)
    lm[:, :2] += np.array([u * W, v * H]) - centre
    return HandFrame(0.0, True, lm, W, H)


def mapper(**over):
    return HandMapper(ARM, {**MCFG, **over})


def in_workspace(t):
    ws, r = ARM.workspace, np.hypot(t.x, t.y)
    return ws["r_min"] - 1e-6 <= r <= ws["r_max"] + 1e-6 and ws["z_min"] <= t.z <= ws["z_max"]


# ------------------------------------------------------------------ real clips
def test_every_target_from_the_sweep_clip_stays_inside_the_workspace():
    m = mapper()
    targets = [m.map(f, 0.5) for f in clip("sweep")]
    seen = [t for t in targets if t]
    assert len(seen) > 500
    assert all(in_workspace(t) for t in seen)
    wb = MCFG["work_box"]
    assert all(wb["y"][0] <= t.y <= wb["y"][1] and wb["z"][0] <= t.z <= wb["z"][1] for t in seen)


def test_the_sweep_covers_the_work_box_and_mostly_reaches():
    seen = [t for t in (mapper().map(f, 0.5) for f in clip("sweep")) if t]
    ys, zs = [t.y for t in seen], [t.z for t in seen]
    wb = MCFG["work_box"]
    assert max(ys) - min(ys) > 0.8 * (wb["y"][1] - wb["y"][0])     # the hand covers left..right
    assert max(zs) - min(zs) > 0.8 * (wb["z"][1] - wb["z"][0])     # and low..high
    assert sum(t.joints is not None for t in seen) / len(seen) > 0.9


def test_pinch_clip_drives_the_gripper_from_closed_to_open():
    m, g = mapper(), ARM.raw["gripper"]
    grips = [m.map(f, pinch_fraction(f.landmarks, GCFG)).gripper_mm for f in clip("pinch") if f.visible]
    assert min(grips) == pytest.approx(g["closed_mm"]) and max(grips) == pytest.approx(g["open_mm"])


def test_no_hand_means_no_target():
    frames = clip("lost")
    out = [mapper().map(f, 0.5) for f in frames]
    assert all((o is None) == (not f.visible) for f, o in zip(frames, out))
    assert any(o is None for o in out)


# ------------------------------------------------------------------ directions + edges
def test_moving_your_hand_to_your_right_moves_the_gripper_to_your_right():
    # Layout: you FACE the arm, camera beside it looking at you. Your right = the image's LEFT,
    # and from where you sit the gripper moving to your right = the arm's LEFT = +y.
    your_right, your_left = mapper().map(hand_at(0.3, 0.5), 0.5), mapper().map(hand_at(0.7, 0.5), 0.5)
    assert your_right.y > your_left.y
    flipped = mapper(mirror=False)                      # standing behind the arm instead
    assert flipped.map(hand_at(0.3, 0.5), 0.5).y < flipped.map(hand_at(0.7, 0.5), 0.5).y


def test_hand_up_moves_the_arm_up():
    assert mapper().map(hand_at(0.5, 0.25), 0.5).z > mapper().map(hand_at(0.5, 0.75), 0.5).z


def test_a_hand_at_the_image_corner_is_clamped_not_escaped():
    t = mapper().map(hand_at(0.02, 0.98), 0.5)
    assert t.clamped and in_workspace(t)
    assert t.z == MCFG["work_box"]["z"][0]


def test_depth_pushing_your_hand_toward_the_camera_reaches_further():
    m = mapper()
    near, far = MCFG["depth_cm"]
    assert m.map(hand_at(0.5, 0.5), 0.5, distance_cm=near).x > m.map(hand_at(0.5, 0.5), 0.5, distance_cm=far).x


def test_option_b_uses_image_height_for_reach():
    m = mapper(axes="B")
    hi, lo = m.map(hand_at(0.5, 0.25), 0.5), m.map(hand_at(0.5, 0.75), 0.5)
    assert hi.x > lo.x and hi.z == lo.z == MCFG["fixed_z_mm"]


def test_a_refused_target_says_why_and_gives_no_pose():
    # a work box straight into the base: inside the ring check it's clamped out, so use one
    # the ring allows but the base clearance / IK refuses
    m = mapper(work_box={"x": [95, 96], "y": [-1, 1], "z": [5, 6]})
    t = m.map(hand_at(0.5, 0.9), 0.5)
    assert t.refused and t.pose() is None


def test_a_filter_plugs_in_without_changes():
    calls = []

    def smooth(t, xyz):
        calls.append(xyz)
        return xyz
    HandMapper(ARM, MCFG, smooth=smooth).map(hand_at(0.5, 0.5), 0.5)
    assert len(calls) == 1
