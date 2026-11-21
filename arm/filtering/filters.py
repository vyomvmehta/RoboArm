"""V2-4: smoothing filters for the hand position (2026-11-21).

Contract (docs/V2_TASKS.md, agreed up front):

    f = OneEuro(cfg)
    x, y, z = f(t, (x, y, z))

HandMapper(arm, smooth=f) calls it once per VISIBLE frame with the target in mm, before clamping.
It never calls it on a lost frame (map() returns None first), so a lost hand shows up here as a
jump in t. A jump longer than `reset_after_s` resets the filter: the next value is passed
straight through instead of gliding from where the hand was before it left.

Axes are the TUPLE positions HandMapper passes, not image axes. With mapping option A:
    x = reach   <- palm size (V2-6 depth): by far the noisiest, gets its own heavy settings
    y = left/right  <- image u
    z = height      <- image v

EMA is kept as the baseline the One Euro filter is measured against (tools/filter_sweep.py).
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "gestures.yaml"
AXES = ("x", "y", "z")


def load_filter_config(path: Path | str = DEFAULT_PATH) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["filter"]
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    if cfg["reset_after_s"] <= 0:
        raise ValueError("filter.reset_after_s must be > 0")
    if cfg["d_cutoff_hz"] <= 0:
        raise ValueError("filter.d_cutoff_hz must be > 0")
    for a in AXES:
        oe = cfg["one_euro"][a]
        if oe["min_cutoff_hz"] <= 0:
            raise ValueError(f"filter.one_euro.{a}.min_cutoff_hz must be > 0")
        if oe["beta"] < 0:
            raise ValueError(f"filter.one_euro.{a}.beta must be >= 0")
        if not 0 < cfg["ema_alpha"][a] <= 1:
            raise ValueError(f"filter.ema_alpha.{a} must be in (0, 1]")


def smoothing_factor(cutoff_hz: float, dt: float) -> float:
    """Weight of the new sample for a first-order low-pass at `cutoff_hz` sampled `dt` apart."""
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class _Axis1e:
    """One Euro on one axis (Casiez, Roussel & Vogel, CHI 2012)."""

    def __init__(self, min_cutoff_hz: float, beta: float, d_cutoff_hz: float):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff_hz, beta, d_cutoff_hz
        self.x = None          # filtered position
        self.dx = 0.0          # filtered speed (units/s)

    def __call__(self, value: float, dt: float | None) -> float:
        if self.x is None or dt is None:
            self.x, self.dx = value, 0.0
            return value
        speed = (value - self.x) / dt
        self.dx += smoothing_factor(self.d_cutoff, dt) * (speed - self.dx)
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        self.x += smoothing_factor(cutoff, dt) * (value - self.x)
        return self.x


class _Axis_ema:
    """Plain EMA with a fixed per-frame weight: the textbook version, ignores frame timing."""

    def __init__(self, alpha: float):
        self.alpha, self.x = alpha, None

    def __call__(self, value: float, dt: float | None) -> float:
        if self.x is None or dt is None:
            self.x = value
        else:
            self.x += self.alpha * (value - self.x)
        return self.x


class _Filter3:
    """Shared frame handling: timing, the lost-hand reset, three independent axes."""

    def __init__(self, cfg: dict, axes: list):
        self.reset_after_s = float(cfg["reset_after_s"])
        self._axes = axes
        self._t: float | None = None
        self._out: tuple[float, float, float] | None = None
        self.resets = 0        # how many times a lost hand restarted the filter (for logs/tests)

    def reset(self) -> None:
        for a in self._axes:
            a.x = None
        self._t = self._out = None

    def __call__(self, t: float, xyz: tuple) -> tuple[float, float, float]:
        if self._t is None:
            dt = None                                   # first frame: pass straight through
        else:
            dt = t - self._t
            if dt <= 0:                                 # repeated / out-of-order timestamp:
                return self._out                        # no new information, keep the output
            if dt > self.reset_after_s:                 # hand was lost (or a long stall): the
                self.reset()                            # old position is stale, start again
                self.resets += 1
                dt = None
        self._t = t
        self._out = tuple(float(f(float(v), dt)) for f, v in zip(self._axes, xyz))
        return self._out


class OneEuro(_Filter3):
    def __init__(self, cfg: dict):
        validate(cfg)
        oe = cfg["one_euro"]
        super().__init__(cfg, [_Axis1e(oe[a]["min_cutoff_hz"], oe[a]["beta"], cfg["d_cutoff_hz"])
                               for a in AXES])


class EMA(_Filter3):
    def __init__(self, cfg: dict):
        validate(cfg)
        super().__init__(cfg, [_Axis_ema(cfg["ema_alpha"][a]) for a in AXES])
