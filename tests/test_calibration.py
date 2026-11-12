import pytest

from arm.calibration import joint_to_pulse

SHOULDER = dict(window=(-30, 150), center_us=1500, direction=1, us_per_deg=5.6,
                min_us=1000, max_us=2000)


def test_window_centre_is_1500():
    # The horn went on with the servo at 1500 us and the shoulder at its window centre.
    assert joint_to_pulse(60, **SHOULDER) == 1500


def test_ten_degrees_up():
    assert joint_to_pulse(70, **SHOULDER) == 1556


def test_direction_flips_the_sign():
    flipped = dict(SHOULDER, direction=-1)
    assert joint_to_pulse(70, **flipped) == 1444


def test_rounds_to_whole_microseconds():
    assert joint_to_pulse(61, **SHOULDER) == 1506  # 1505.6 -> 1506


def test_outside_the_pulse_limits_is_rejected():
    with pytest.raises(ValueError):
        joint_to_pulse(150, **SHOULDER)  # 90 deg above centre = 2004 us > 2000


def test_gripper_endpoints_and_middle():
    from arm.calibration import gripper_to_pulse
    args = dict(closed_mm=0, max_open_mm=40, closed_us=1200, open_us=1800)
    assert gripper_to_pulse(0, **args) == 1200
    assert gripper_to_pulse(40, **args) == 1800
    assert gripper_to_pulse(20, **args) == 1500


def test_real_config_turns_park_pose_into_pulses():
    from arm.calibration import load_calibration
    from arm.config import load_arm
    cal = load_calibration(load_arm())
    pulses = cal.to_pulses([0, 90, -130, -40, 40])
    assert len(pulses) == 5
    for name, p in zip(("j0_base", "j1_shoulder", "j2_elbow", "j3_wrist"), pulses):
        j = cal.cal["joints"][name]
        assert j["min_us"] <= p <= j["max_us"]


def test_every_joint_limit_fits_inside_the_pulse_limits():
    # If this fails, a slider position allowed by arm.yaml would be refused by calibration.
    from arm.calibration import load_calibration
    from arm.config import load_arm
    arm = load_arm()
    cal = load_calibration(arm)
    for name in ("j0_base", "j1_shoulder", "j2_elbow", "j3_wrist"):
        for deg in arm.raw["joints"][name]["limits"]:
            values = [0, 60, -70, -30, 20]
            values[("j0_base", "j1_shoulder", "j2_elbow", "j3_wrist").index(name)] = deg
            cal.to_pulses(values)  # raises if outside min/max
