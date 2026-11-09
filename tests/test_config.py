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
