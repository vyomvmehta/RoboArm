"""V2-2 gestures on SYNTHETIC hands (2026-11-20). Real recorded clips (V2-3) get their own tests.

The synthetic hand is drawn upright in image pixels (y points down, fingers point up), palm
size 100 px, so the ratios are easy to read: a straight finger, a curled one, a thumb that is
out, tucked, or pointing up.
"""
import numpy as np
import pytest

from arm.gestures import Confirmer, classify, features, load_gesture_config, pinch_fraction
from arm.vision.hands import HandFrame, load_csv, save_csv

CFG = load_gesture_config()
MCP_X = {"index": -30, "middle": 0, "ring": 25, "little": 48}
FIRST = {"index": 5, "middle": 9, "ring": 13, "little": 17}


def hand(fingers="straight", thumb="out", shift=(400, 500), scale=1.0, pinch=None):
    """Build 21 landmarks. fingers: straight|curled. thumb: out|tucked|up."""
    p = np.zeros((21, 3))
    p[0] = (0, 0, 0)                                          # wrist
    for name, x in MCP_X.items():
        i = FIRST[name]
        p[i] = (x, -100, 0)                                   # MCP knuckles (middle at palm size 100)
        if fingers == "straight":
            p[i + 1], p[i + 2], p[i + 3] = (x, -140, 0), (x, -165, 0), (x, -185, 0)
        else:                                                 # curled back down into the palm
            p[i + 1], p[i + 2], p[i + 3] = (x, -125, 0), (x, -100, 0), (x, -75, 0)
    p[1], p[2] = (-35, -25, 0), (-60, -50, 0)                 # thumb CMC, MCP
    if thumb == "out":
        p[3], p[4] = (-85, -70, 0), (-110, -85, 0)
    elif thumb == "up":
        p[3], p[4] = (-61, -120, 0), (-62, -180, 0)          # a real thumb is ~1.2 palms long
    else:                                                     # tucked across the palm
        p[3], p[4] = (-40, -70, 0), (-15, -80, 0)
    if pinch is not None:                                     # thumb tip `pinch` px from the index tip
        p[4] = p[8] + (-pinch, 0, 0)
    return p * scale + (*shift, 0)


@pytest.mark.parametrize("args, want", [
    (dict(fingers="straight", thumb="out"), "palm"),
    (dict(fingers="curled", thumb="tucked"), "fist"),
    (dict(fingers="curled", thumb="up"), "thumbs_up"),
    (dict(fingers="straight", thumb="tucked"), "palm"),      # thumb ignored for the palm (Nov 20 clips)
])
def test_each_command_gesture_is_recognised(args, want):
    assert classify(hand(**args), CFG) == want


@pytest.mark.parametrize("scale", [0.4, 1.0, 2.5])
def test_distance_from_the_camera_does_not_change_the_answer(scale):
    assert classify(hand("curled", "tucked", scale=scale), CFG) == "fist"
    assert features(hand(scale=scale), CFG)["palm"] == pytest.approx(100 * scale)


def test_pinch_fraction_runs_from_closed_to_open():
    assert pinch_fraction(hand(pinch=10), CFG) == 0.0          # 0.1 palm: touching
    assert pinch_fraction(hand(pinch=150), CFG) == 1.0         # 1.5 palm: wide open
    mid = pinch_fraction(hand(pinch=65), CFG)                  # 0.65 palm: half way
    assert 0.4 < mid < 0.6


# ------------------------------------------------------------------ hold to confirm
def run(conf, labels, dt=1 / 30):
    return [conf.update(l, i * dt) for i, l in enumerate(labels)]


def test_a_gesture_fires_once_after_the_hold_time():
    out = run(Confirmer(0.5, 0.8), ["fist"] * 40)              # 1.3 s of fist at 30 fps
    fired = [i for i, o in enumerate(out) if o]
    assert len(fired) == 1 and out[fired[0]] == "fist"
    assert 0.45 <= fired[0] / 30 <= 0.6


def test_a_brief_flash_does_not_fire():
    assert not any(run(Confirmer(0.5, 0.8), ["none"] * 10 + ["fist"] * 8 + ["none"] * 20))


def test_one_misread_frame_does_not_fire_the_same_command_twice():
    labels = ["fist"] * 20 + ["none"] + ["fist"] * 40
    assert sum(1 for o in run(Confirmer(0.5, 0.8), labels) if o) == 1


def test_it_fires_again_after_the_hand_has_really_let_go():
    labels = ["fist"] * 20 + [None] * 20 + ["fist"] * 20
    assert sum(1 for o in run(Confirmer(0.5, 0.8), labels) if o) == 2


def test_switching_gestures_fires_the_new_one():
    out = [o for o in run(Confirmer(0.5, 0.8), ["fist"] * 20 + ["palm"] * 20) if o]
    assert out == ["fist", "palm"]


# ------------------------------------------------------------------ recorder round trip
def test_recorded_clips_load_back_exactly(tmp_path):
    frames = [HandFrame(0.0, True, hand(), 1280, 720, "Right", 0.97),
              HandFrame(0.033, False, None, 1280, 720)]
    save_csv(frames, tmp_path / "clip.csv")
    back = load_csv(tmp_path / "clip.csv")
    assert [f.visible for f in back] == [True, False]
    assert np.allclose(back[0].landmarks, frames[0].landmarks, atol=0.01)
    assert back[0].palm_size() == pytest.approx(100, abs=0.01)
