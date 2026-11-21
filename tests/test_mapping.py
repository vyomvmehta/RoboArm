"""V2-5 mapping: hand -> gripper target, on Vyom's real clips + synthetic edge cases (Nov 20)."""
import glob

import numpy as np
import pytest

from arm.config import load_arm
from arm.gestures import load_gesture_config, pinch_fraction
from arm.mapping import HandMapper, load_mapping_config
from arm.mapping.hand_to_target import PALM_POINTS, check_work_box
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
    assert all(t.joints is not None and t.refused is None for t in seen)   # never unreachable


# Most a target can move per unit of palm movement across the image (0..1): the work-box span
# over the hand-box span, per axis. Clamping per axis can only shrink a step, never grow it.
def _mm_per_image_unit(m):
    u0, u1, v0, v1 = m.cfg["hand_box"]
    wb = m.cfg["work_box"]
    return max((wb["y"][1] - wb["y"][0]) / (u1 - u0), (wb["z"][1] - wb["z"][0]) / (v1 - v0),
               (wb["x"][1] - wb["x"][0]) / (v1 - v0))


def _palm_uv(f):
    c = f.landmarks[PALM_POINTS, :2].mean(axis=0)
    return np.array([c[0] / f.width, c[1] / f.height])


def _assert_continuous(frames, targets, m, extra_mm=0.0):
    """Every step between consecutive visible frames is bounded by how far the palm moved."""
    k, pairs = _mm_per_image_unit(m), [(f, t) for f, t in zip(frames, targets) if t]
    for (f0, a), (f1, b) in zip(pairs, pairs[1:]):
        step = np.linalg.norm([b.x - a.x, b.y - a.y, b.z - a.z])
        allowed = k * np.linalg.norm(_palm_uv(f1) - _palm_uv(f0)) + extra_mm + 0.2   # 0.1 mm rounding
        assert step <= allowed, (f1.t, step, allowed, a.clamped, b.clamped)


def test_the_sweep_gives_a_continuous_reachable_path_through_every_clamp():
    m, frames = mapper(), clip("sweep")
    targets = [m.map(f, 0.5) for f in frames]
    seen = [t for t in targets if t]
    flips = sum(a.clamped != b.clamped for a, b in zip(seen, seen[1:]))
    assert flips > 0                                     # the clip really crosses the box edge
    assert all(t.refused is None for t in seen)
    _assert_continuous(frames, targets, m)


def test_the_sweep_with_depth_covers_the_full_reach_and_stays_reachable():
    # V2-6 doesn't exist yet: ramp a fake distance from far past `far` to near past `near`, so x
    # sweeps the whole work box (and is clamped at both ends) while the real clip moves y and z.
    m, frames = mapper(), clip("sweep")
    near, far = MCFG["depth_cm"]
    dist = np.linspace(far + 10, near - 10, len(frames))
    targets = [m.map(f, 0.5, distance_cm=d) for f, d in zip(frames, dist)]
    seen = [t for t in targets if t]
    wb = MCFG["work_box"]
    assert min(t.x for t in seen) == wb["x"][0] and max(t.x for t in seen) == wb["x"][1]
    assert all(t.refused is None and in_workspace(t) for t in seen)
    dx_per_frame = (wb["x"][1] - wb["x"][0]) / (far - near) * abs(dist[1] - dist[0])
    _assert_continuous(frames, targets, m, extra_mm=dx_per_frame * 10)   # tracking gaps skip frames


def test_walking_the_hand_out_past_every_edge_never_jumps_or_refuses():
    m = mapper()
    for (ua, va), (ub, vb) in [((0.5, 0.5), (-0.1, 0.5)), ((0.5, 0.5), (1.1, 0.5)),
                               ((0.5, 0.5), (0.5, -0.1)), ((0.5, 0.5), (0.5, 1.1)),
                               ((0.0, 0.0), (1.0, 1.0)), ((1.0, 0.0), (0.0, 1.0))]:
        frames = [hand_at(ua + (ub - ua) * s, va + (vb - va) * s) for s in np.linspace(0, 1, 400)]
        targets = [m.map(f, 0.5) for f in frames]
        assert all(t.refused is None and in_workspace(t) for t in targets)
        _assert_continuous(frames, targets, m)


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


def test_an_unreachable_work_box_is_refused_at_start_up():
    # The old box (x up to 200): its far corners are past r_max / the wrist's reach.
    with pytest.raises(ValueError, match="not fully reachable"):
        mapper(work_box={**MCFG["work_box"], "x": [150, 200]})
    with pytest.raises(ValueError, match="not fully reachable"):    # into the base (D23 / IK)
        mapper(work_box={"x": [95, 96], "y": [-1, 1], "z": [5, 6]})


def test_the_configured_work_box_is_reachable_everywhere_on_a_fine_grid():
    check_work_box(ARM, {**MCFG, "box_check_mm": 5})


def test_a_refused_target_still_says_why_and_gives_no_pose():
    # Backstop only: a valid box can't produce one, so swap in a bad box after the start-up check.
    m = mapper()
    m.cfg = {**MCFG, "work_box": {"x": [95, 96], "y": [-1, 1], "z": [5, 6]}}
    t = m.map(hand_at(0.5, 0.9), 0.5)
    assert t.refused and t.pose() is None


def test_a_filter_plugs_in_without_changes():
    calls = []

    def smooth(t, xyz):
        calls.append(xyz)
        return xyz
    HandMapper(ARM, MCFG, smooth=smooth).map(hand_at(0.5, 0.5), 0.5)
    assert len(calls) == 1
