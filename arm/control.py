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
  5. The ramp (2026-11-15): inputs set a GOAL; each heartbeat tick moves the sent TARGET one
     step toward it (arm/motion.py step_toward) at the speeds in config/arm.yaml, so a big
     request becomes a smooth move, not a jump. Joint limits are a box, so every pose on
     the way between two valid poses is inside the limits too.
  6. Base clearance (2026-11-17, D23): the base isn't a box. A goal whose end pose drives the
     forearm or hand into the base is refused, and since the ramp is a straight line in joint
     space, each step is checked too: a step that would enter the base HOLDS the arm where it
     is and says why (status()["blocked"]). Steps out of a colliding pose are allowed.
"""
from __future__ import annotations

import asyncio
import logging
import math

from arm.calibration import Calibration
from arm.clearance import base_collision
from arm.comms.link import Link
from arm.config import JOINTS
from arm.kinematics import JointAngles
from arm.motion import step_toward

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, link: Link, calibration: Calibration, heartbeat_hz: float = 30):
        self.link = link
        self.cal = calibration
        self.period_s = 1 / heartbeat_hz
        self.armed = False
        self.target_us: list[int] | None = None   # what the heartbeat sends
        self.target_values: list[float] | None = None
        self.goal_values: list[float] | None = None  # where the ramp is heading
        arm = calibration.arm
        # Most each joint may move in one tick: speed x tick time (degrees, gripper mm).
        self.max_step = ([arm.speed_limits_deg_per_s[n] * self.period_s for n in JOINTS]
                         + [arm.raw["gripper_speed_mm_per_s"] * self.period_s])
        self._task: asyncio.Task | None = None
        self.fault: str | None = None   # why the heartbeat stopped itself; shown on the page
        self.blocked: str | None = None  # why the ramp is holding short of the goal (base clearance)

    def _collision(self, values: list[float]) -> str | None:
        arm = self.cal.arm
        angles = JointAngles(*(math.radians(v) for v in values[:4]))
        return base_collision(arm.geometry, angles, arm.base_clearance)

    def park_values(self) -> list[float]:
        """Park pose as [j0..j3 degrees, gripper mm], from config/arm.yaml."""
        park = self.cal.arm.park
        g = self.cal.arm.raw["gripper"]
        # Named fields, not vars(park).values(): reordering JointAngles must not silently
        # scramble the park pose (PR #6 review).
        joints = (park.theta0, park.theta1, park.theta2, park.theta3)
        return [round(math.degrees(v), 3) for v in joints] + [g["open_mm"]]

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
        self.goal_values = list(park)
        self.fault = None
        self.blocked = None
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
        """[j0..j3 degrees, gripper mm] -> new GOAL. Returns None if accepted, else why not.

        The arm doesn't jump there: the heartbeat ramps the sent target toward it.
        """
        if not self.armed:
            return "not armed: press Arm first"
        try:
            self.cal.to_pulses(values)  # validate the END pose; the poses on the way are inside the same box
        except ValueError as e:
            return str(e)              # rejected: the goal (and the ramp) stays as it was
        why = self._collision(values)
        if why:
            return why
        self.goal_values = list(values)
        self.blocked = None
        return None

    def _advance(self) -> None:
        """One ramp step: move the sent target toward the goal."""
        if self.goal_values is None or self.target_values == self.goal_values:
            return
        nxt = step_toward(self.target_values, self.goal_values, self.max_step)
        try:
            us = self.cal.to_pulses(nxt)
        except ValueError as e:        # only a ramp bug gets here: stop where we are
            log.warning("ramp produced an invalid pose, holding: %s", e)
            self.goal_values = list(self.target_values)
            return
        why = self._collision(nxt)
        if why and not self._collision(self.target_values):
            # Clear now, into the base next: hold here. (Already colliding: let it move out.)
            log.warning("ramp holding short of the goal: %s", why)
            self.blocked = f"stopped on the way: the straight path {why[5:]}"
            self.goal_values = list(self.target_values)
            return
        self.target_values, self.target_us = nxt, us

    # ------------------------------------------------------------------ heartbeat
    async def _heartbeat(self):
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while self.armed:
                if not self.link.connected or self.link.state == "FAULT":
                    self.armed = False     # nothing safe to do but stop sending
                    return
                self._advance()
                self.link.send("C", *self.target_us)
                # Schedule against a fixed clock, not "sleep 33 ms after sending": that way a
                # slow send doesn't make every later frame late too (no drift).
                next_tick += self.period_s
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            # Anything else (a ramp bug, the port dying mid-write) must NOT leave the page saying
            # ARMED while no C frames go out (PR #11 review). Stop, try to send D, and say why.
            log.exception("heartbeat stopped")
            self.fault = f"heartbeat stopped: {type(e).__name__}: {e}"
            self.armed = False
            self._task = None
            try:
                if self.link.connected:
                    self.link.send("D")
            except Exception:
                log.exception("could not send D after the heartbeat stopped")

    def status(self) -> dict:
        return {**self.link.status(), "armed": self.armed, "fault": self.fault,
                "blocked": self.blocked,
                "target_us": self.target_us,
                "target_values": self.target_values, "goal_values": self.goal_values,
                "moving": self.goal_values is not None and self.target_values != self.goal_values}
