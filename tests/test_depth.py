"""V2-6 depth from palm size: measures, fit, config round trip, resolution warning (Nov 21)."""
import glob
import shutil

import numpy as np
import pytest

from arm.gestures import load_gesture_config
from arm.vision.depth import (MEASURES, SECTION_MARKER, Depth, fit, load_depth_config, palm_px,
                              predict, write_depth_section)
from arm.vision.hands import HandFrame, load_csv

W, H = 1280, 720
F_PX, PALM_CM = 900.0, 8.0          # a made-up camera + hand: s = F * L / Z


def hand(scale: float, tilt_deg: float = 0.0, u=W / 2, v=H / 2) -> np.ndarray:
    """A flat synthetic hand (21 landmarks, px). scale 1 = palm triangle ~100 px.
    tilt_deg rotates it about the vertical image axis (foreshortens x)."""
    lm = np.zeros((21, 3))
    knuckles = {5: (-35, -95), 9: (-10, -100), 13: (15, -97), 17: (38, -88)}
    for i, (x, y) in knuckles.items():
        lm[i, :2] = (x, y)
    for f, base in zip(range(4), (5, 9, 13, 17)):           # straight fingers above each knuckle
        for j in range(1, 4):
            lm[base + j, :2] = lm[base, :2] + (0, -25 * j)
    lm[1:5, :2] = [(-30, -20), (-50, -40), (-65, -55), (-75, -65)]
    lm[:, 0] *= np.cos(np.radians(tilt_deg))
    lm[:, :2] *= scale
    lm[:, :2] += (u, v)
    return lm


def frame(lm, w=W, h=H):
    return HandFrame(0.0, True, lm, w, h)


def cfg(**over):
    c = {"model": "inverse", "a": 3000.0, "b": 1.0, "measure": "palm_triangle",
         "camera_name": "test cam", "width": W, "height": H, "fit_range_cm": [30, 90]}
    return {**c, **over}


# ------------------------------------------------------------------ measures
@pytest.mark.parametrize("m", sorted(MEASURES))
def test_every_measure_halves_when_the_hand_is_twice_as_far(m):
    near, far = palm_px(hand(2.0), m), palm_px(hand(1.0), m)
    assert far == pytest.approx(near / 2, rel=1e-9)


def test_palm_triangle_ignores_the_fingers_bbox_does_not():
    open_ = hand(1.0)
    fist = open_.copy()
    for base in (5, 9, 13, 17):                              # curl every finger onto its knuckle
        fist[base + 1:base + 4] = fist[base]
    assert palm_px(fist) == pytest.approx(palm_px(open_))
    assert palm_px(fist, "bbox_diag") < 0.8 * palm_px(open_, "bbox_diag")


def test_palm_triangle_is_steadier_than_wrist_mcp9_on_the_recorded_clips():
    """The reason it is the default (docs: Nov 20 clips, at roughly fixed distance)."""
    for name in ("palm", "pinch", "thumbs_up"):
        frames = [f for f in load_csv(sorted(glob.glob(f"runs/hands/{name}-*.csv"))[0]) if f.visible]
        cv = {m: np.std(s) / np.median(s)
              for m in ("palm_triangle", "wrist_mcp9")
              for s in [[palm_px(f.landmarks, m) for f in frames]]}
        assert cv["palm_triangle"] < cv["wrist_mcp9"], name


def test_unknown_measure_is_refused():
    with pytest.raises(ValueError, match="unknown palm measure"):
        palm_px(hand(1.0), "knuckle_vibes")


# ------------------------------------------------------------------ fit
def pinhole(z_cm):
    return F_PX * PALM_CM / np.asarray(z_cm, dtype=float)


def test_inverse_fit_recovers_the_pinhole_camera_exactly():
    z = np.array([30, 35, 42, 52, 65, 90.0])
    a, b, res = fit(pinhole(z) , z + 2.0, "inverse")          # +2: tape starts 2 cm behind the pinhole
    assert a == pytest.approx(F_PX * PALM_CM)
    assert b == pytest.approx(2.0)
    assert np.abs(res).max() < 1e-9
    assert predict("inverse", a, b, pinhole(47)) == pytest.approx(49.0)


def test_linear_and_inverse_square_misfit_a_pinhole_over_30_to_90_cm():
    z = np.array([30, 35, 42, 52, 65, 90.0])
    for model in ("linear", "inverse_square"):
        _, _, res = fit(pinhole(z), z, model)
        assert np.abs(res).max() > 2.0, model                 # several cm off: the curvature shows


def test_noisy_inverse_fit_predicts_held_out_distances():
    rng = np.random.default_rng(0)
    z = np.array([30, 35, 42, 52, 65, 90.0])
    s = pinhole(z) * (1 + rng.normal(0, 0.01, z.size))        # 1% palm-size noise per distance
    a, b, _ = fit(s, z, "inverse")
    for zh in (47, 75):
        assert abs(predict("inverse", a, b, pinhole(zh)) - zh) < 0.03 * zh


def test_fit_needs_three_distances_and_positive_sizes():
    with pytest.raises(ValueError, match="at least 3"):
        fit([100, 50], [40, 80])
    with pytest.raises(ValueError, match="positive"):
        fit([100, 0, 50], [40, 60, 80])


# ------------------------------------------------------------------ runtime
def test_depth_maps_palm_px_to_cm_and_flags_extrapolation():
    d = Depth(cfg())
    assert d(100.0) == pytest.approx(31.0)
    assert d.in_range(60) and not d.in_range(150) and not d.in_range(10)
    assert d.from_frame(HandFrame(0.0, False, None, W, H)) is None


def test_matching_resolution_is_silent(capsys):
    d = Depth(cfg())
    d.from_frame(frame(hand(1.0)))
    assert not d.mismatch
    assert capsys.readouterr().err == ""


def test_other_resolution_warns_loudly_once_and_sets_the_flag(capsys, caplog):
    d = Depth(cfg())
    d.from_frame(frame(hand(1.0), 640, 480))
    err = capsys.readouterr().err
    assert "DEPTH CALIBRATION MISMATCH" in err and "640x480" in err and "1280x720" in err
    assert "test cam" in err
    assert "MISMATCH" in caplog.text
    assert d.mismatch
    d.from_frame(frame(hand(1.0), 640, 480))
    assert capsys.readouterr().err == ""                      # not every frame
    d.from_frame(frame(hand(1.0), 1920, 1080))
    assert "1920x1080" in capsys.readouterr().err             # but every NEW resolution


# ------------------------------------------------------------------ config
def test_the_repo_yaml_still_loads_for_gestures_and_depth():
    load_gesture_config()                                     # `depth:` must not reach GestureConfig
    d = load_depth_config()
    assert d is None or Depth(d)(100.0) > 0


def test_write_depth_section_keeps_the_rest_and_round_trips(tmp_path):
    p = tmp_path / "gestures.yaml"
    shutil.copy("config/gestures.yaml", p)
    before = p.read_text(encoding="utf-8")
    head = before[:before.find(SECTION_MARKER)]
    for _ in range(2):                                        # rewriting replaces, never duplicates
        write_depth_section({**cfg(), "holdout_error_cm": {47.0: -0.8, 75.0: 1.9}}, p, "note one\nnote two")
    after = p.read_text(encoding="utf-8")
    assert after.startswith(head.rstrip("\n"))
    assert after.count(SECTION_MARKER) == 1 and "# note two" in after
    d = load_depth_config(p)
    assert (d["width"], d["height"], d["camera_name"]) == (W, H, "test cam")
    assert d["holdout_error_cm"][75.0] == 1.9
    load_gesture_config(p)


def test_incomplete_depth_section_is_refused(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text("depth:\n  model: inverse\n  a: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_depth_config(p)


# ------------------------------------------------------------------ depth: null (uncalibrated)
import logging  # noqa: E402

import arm.vision.depth as depth_mod  # noqa: E402
from arm.config import load_arm  # noqa: E402
from arm.mapping import HandMapper, load_mapping_config  # noqa: E402


@pytest.fixture
def null_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(depth_mod, "_UNCALIBRATED_LOGGED", False)
    p = tmp_path / "g.yaml"
    p.write_text("depth: null\n", encoding="utf-8")
    return p


def test_null_depth_loads_as_none_and_logs_once(null_yaml, caplog):
    with caplog.at_level(logging.WARNING, logger="arm.vision.depth"):
        assert depth_mod.load_depth(null_yaml) is None
        assert depth_mod.load_depth(null_yaml) is None          # e.g. a second start-up path
    msgs = [r for r in caplog.records if "uncalibrated" in r.getMessage()]
    assert len(msgs) == 1


def test_null_depth_has_no_resolution_guard_to_fire(null_yaml, capsys, caplog):
    assert depth_mod.load_depth(null_yaml) is None
    assert "MISMATCH" not in capsys.readouterr().err and "MISMATCH" not in caplog.text


def test_mapper_falls_back_to_fixed_reach_when_depth_is_null(null_yaml):
    cfg = load_mapping_config()
    d = depth_mod.load_depth(null_yaml)
    fr = frame(hand(1.0))
    dist = d.from_frame(fr) if d else None
    t = HandMapper(load_arm(), cfg).map(fr, 0.5, distance_cm=dist)
    assert dist is None and t.x == pytest.approx(cfg["fixed_reach_mm"])


def test_the_repo_yaml_is_uncalibrated_until_the_demo_camera_is_calibrated(monkeypatch):
    monkeypatch.setattr(depth_mod, "_UNCALIBRATED_LOGGED", False)
    assert depth_mod.load_depth() is None


def test_calibrating_never_touches_a_section_merged_after_depth(tmp_path):
    """V2-4 (filter) also appends its section at the end of gestures.yaml; after a merge it may
    sit AFTER the depth block. Writing the depth block must leave it intact."""
    p = tmp_path / "g.yaml"
    filt = ("# ---------------------------------------------------------------- V2-4 filter (arm/filtering)\n"
            "filter:\n  reset_after_s: 0.2\n")
    p.write_text("modes:\n  follow_hz: 30\n\n" + SECTION_MARKER + " (arm/vision/depth.py)\n"
                 "depth: null\n\n" + filt, encoding="utf-8")
    write_depth_section(cfg(), p)
    text = p.read_text(encoding="utf-8")
    assert text.endswith(filt) and text.startswith("modes:\n  follow_hz: 30\n")
    import yaml
    raw = yaml.safe_load(text)
    assert raw["filter"] == {"reset_after_s": 0.2} and raw["depth"]["width"] == W
    write_depth_section(cfg(a=1234.0), p)                       # twice: still one block, filter kept
    text = p.read_text(encoding="utf-8")
    assert text.count(SECTION_MARKER) == 1 and text.endswith(filt) and "1234" in text
