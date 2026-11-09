"""Joint angle (degrees) -> servo pulse (microseconds).

Inputs come from two files:
  config/arm.yaml          window: [low, high] for each joint (the servo's 180 degrees, in joint angles)
  config/calibration.yaml  center_us, and per joint: direction, us_per_deg, min_us, max_us

joint_to_pulse: written by Vyom (step 3, 2026-11-08).
Run the tests:  py -m pytest tests/test_calibration.py -q
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from arm.config import JOINTS, ArmConfig

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "calibration.yaml"


def joint_to_pulse(deg: float, window: tuple[float, float], center_us: float,
                   direction: int, us_per_deg: float, min_us: int, max_us: int) -> int:
    """Return the pulse width (whole microseconds) that puts this joint at `deg`.

    Raise ValueError if the pulse would fall outside [min_us, max_us]. Do NOT quietly
    clamp it: a clamped pulse means the arm silently goes somewhere other than asked.
    """
    low, high = window
    centre_deg = (high + low) / 2
    pulse = direction * us_per_deg * (deg - centre_deg) + center_us
    pulse = round(pulse)

    if not (min_us <= pulse <= max_us):
        raise ValueError(f"pulse {pulse} us is outside {min_us}-{max_us} us (joint at {deg} deg)")
    return pulse


def gripper_to_pulse(open_mm: float, closed_mm: float, max_open_mm: float,
                     closed_us: int, open_us: int) -> int:
    """Gripper opening (mm) -> pulse. Same straight-line idea as joint_to_pulse, but drawn
    between two measured points (fully closed, fully open) instead of a centre plus a slope.
    """
    if not (closed_mm <= open_mm <= max_open_mm):
        raise ValueError(f"gripper {open_mm} mm is outside {closed_mm}-{max_open_mm} mm")
    fraction = (open_mm - closed_mm) / (max_open_mm - closed_mm)  # 0 = closed, 1 = open
    return round(closed_us + fraction * (open_us - closed_us))


@dataclass(frozen=True)
class Calibration:
    """Both config files together: turns the page's 5 numbers into 5 pulses."""
    arm: ArmConfig
    cal: dict

    def to_pulses(self, values: list[float]) -> list[int]:
        """[j0..j3 in degrees, gripper in mm] -> 5 pulses. Raises ValueError naming the joint."""
        if len(values) != 5:
            raise ValueError(f"expected 5 values, got {len(values)}")
        pulses = []
        for name, deg in zip(JOINTS, values[:4]):
            j = self.cal["joints"][name]
            try:
                pulses.append(joint_to_pulse(
                    deg, self.arm.raw["joints"][name]["window"], self.cal["center_us"],
                    j["direction"], j["us_per_deg"], j["min_us"], j["max_us"]))
            except ValueError as e:
                raise ValueError(f"{name}: {e}") from None
        g, gc = self.arm.raw["gripper"], self.cal["gripper"]
        pulses.append(gripper_to_pulse(values[4], g["closed_mm"], g["open_mm"],
                                       gc["closed_us"], gc["open_us"]))
        return pulses


def load_calibration(arm: ArmConfig, path: Path | str = DEFAULT_PATH) -> Calibration:
    cal = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for name in JOINTS:
        if cal["joints"][name]["direction"] not in (1, -1):
            raise ValueError(f"{name}: direction must be 1 or -1")
    return Calibration(arm=arm, cal=cal)
