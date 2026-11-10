"""The one place that decides what goes to the arm (step 5, 2026-11-10).

Every input (web sliders now, gestures in V2) only sets a TARGET here. This class owns:

  1. Arming in a safe order:   A  ->  first C = the PARK pose  ->  only then the sliders.
     Firmware v0 has no motion limiter yet, so the first C is a jump from wherever the limp
     servos are. Park is where the arm rests when limp, so that first jump is (nearly) zero.
  2. The heartbeat: while armed, send the latest target as a C frame at a FIXED rate
     (30 Hz), whether or not anything changed. The firmware's watchdog drops into HOLD if
     no C arrives for 300 ms; a steady heartbeat keeps it ARMED, and the fixed rate means a
     fast-dragging slider can never flood the serial line (latest target wins, as in step 2).
  3. The dead-man rule: if the controlling browser disconnects, disarm.
  4. The "clear no": a target that calibration rejects is NOT sent; the arm keeps the
     previous target and the caller gets the reason.
"""
from __future__ import annotations

import asyncio
import math

from arm.calibration import Calibration
from arm.comms.link import Link


class Controller:
    def __init__(self, link: Link, calibration: Calibration, heartbeat_hz: float = 30):
        self.link = link
        self.cal = calibration
        self.period_s = 1 / heartbeat_hz
        self.armed = False
        self.target_us: list[int] | None = None   # what the heartbeat sends
        self.target_values: list[float] | None = None
        self._task: asyncio.Task | None = None

    def park_values(self) -> list[float]:
        """Park pose as [j0..j3 degrees, gripper mm], from config/arm.yaml."""
        park = self.cal.arm.park
        g = self.cal.arm.raw["gripper"]
        return [round(math.degrees(v), 3) for v in vars(park).values()] + [g["open_mm"]]

    # ------------------------------------------------------------------ arming
    async def arm(self) -> str | None:
        """Returns None on success, or the reason it refused."""
        if self.armed:
            return "already armed"
        if self.link.state != "DISARMED":
            return f"Nano is {self.link.state}, not DISARMED"
        park = self.park_values()
        try:
            park_us = self.cal.to_pulses(park)
        except ValueError as e:
            return f"park pose is outside the calibration limits: {e}"
        # Set the target BEFORE arming, so the very first C the heartbeat sends is park.
        self.target_values, self.target_us = park, park_us
        self.link.send("A")
        self.armed = True
        self._task = asyncio.create_task(self._heartbeat())
        return None

    async def disarm(self) -> None:
        # PROTOCOL.md: D = go limp (v0 skips "move to park first"; that needs the limiter).
        self.armed = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self.link.connected:
            self.link.send("D")

    # ------------------------------------------------------------------ targets
    def set_target(self, values: list[float]) -> str | None:
        """[j0..j3 degrees, gripper mm]. Returns None if accepted, else why it was rejected."""
        if not self.armed:
            return "not armed: press Arm first"
        try:
            us = self.cal.to_pulses(values)
        except ValueError as e:
            return str(e)              # rejected: the heartbeat keeps sending the OLD target
        self.target_values, self.target_us = list(values), us
        return None

    # ------------------------------------------------------------------ heartbeat
    async def _heartbeat(self):
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while self.armed:
                if not self.link.connected or self.link.state == "FAULT":
                    self.armed = False     # nothing safe to do but stop sending
                    return
                self.link.send("C", *self.target_us)
                # Schedule against a fixed clock, not "sleep 33 ms after sending": that way a
                # slow send doesn't make every later frame late too (no drift).
                next_tick += self.period_s
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except asyncio.CancelledError:
            pass

    def status(self) -> dict:
        return {**self.link.status(), "armed": self.armed, "target_us": self.target_us}
