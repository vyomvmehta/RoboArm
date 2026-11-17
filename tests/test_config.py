import math

import pytest

from arm.config import load_arm
from arm.kinematics import UnreachableError, fk, ik


@pytest.fixture(scope="module")
def cfg():
    return load_arm()


def test_arm_yaml_loads_and_home_is_reachable(cfg):
    # load_arm runs IK on the home target and checks both poses against the limits.
    x, y, z, phi = fk(cfg.geometry, cfg.home)
    home = cfg.raw["poses"]["home"]
    assert (x, y, z) == pytest.approx((home["x"], home["y"], home["z"]), abs=1e-6)
    assert math.degrees(phi) == pytest.approx(home["pitch"])


def test_pick_zone_is_reachable_pointing_down(cfg):
    # The demo picks a 30 mm block (grasp ~15 mm up) anywhere in the workspace ring, straight down.
    ws = cfg.workspace
    for r in range(ws["r_min"], ws["r_max"] + 1, 10):
        for deg_yaw in (-60, 0, 60):
            yaw = math.radians(deg_yaw)
            ik(cfg.geometry, r * math.cos(yaw), r * math.sin(yaw), 15, -math.pi / 2, limits=cfg.limits)


def test_beyond_full_reach_is_rejected(cfg):
    g = cfg.geometry
    too_far = g.shoulder_offset + g.l1 + g.l2 + g.l3 + 1
    with pytest.raises(UnreachableError):
        ik(g, too_far, 0, g.shoulder_height, 0)


def test_geared_base_window_may_span_180_times_the_ratio(cfg):
    # D22: the base turns 2.25 deg per servo degree, so its window can be 405 deg wide.
    lo, hi = cfg.raw["joints"]["j0_base"]["window"]
    assert cfg.raw["joints"]["j0_base"]["gear_ratio"] == 2.25
    assert hi - lo == pytest.approx(180 * 2.25)


def _write_arm(tmp_path, j0):
    import yaml
    from arm.config import DEFAULT_PATH
    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["joints"]["j0_base"] = j0
    p = tmp_path / "arm.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return p


def test_window_wider_than_180_needs_a_gear_ratio(tmp_path):
    with pytest.raises(ValueError, match="wider than the servo"):
        load_arm(_write_arm(tmp_path, {"window": [-120, 120], "limits": [-85, 85]}))
    with pytest.raises(ValueError, match="gear ratio 1.2"):
        load_arm(_write_arm(tmp_path, {"gear_ratio": 1.2, "window": [-120, 120], "limits": [-85, 85]}))
    load_arm(_write_arm(tmp_path, {"gear_ratio": 1.5, "window": [-120, 120], "limits": [-85, 85]}))


@pytest.mark.parametrize("bad", [0, -2, "2.25"])
def test_gear_ratio_must_be_positive(tmp_path, bad):
    with pytest.raises(ValueError, match="gear_ratio"):
        load_arm(_write_arm(tmp_path, {"gear_ratio": bad, "window": [-90, 90], "limits": [-85, 85]}))
