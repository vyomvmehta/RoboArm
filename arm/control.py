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
     the way between two valid poses is valid too.
"""
from __future__ import annotations

import asyncio
import logging
import math

from arm.calibration import Calibration
from arm.comms.link import Link
from arm.config import JOINTS
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
        self.parking = False            # True while disarm() ramps to park: new targets refused
        self._limp_sent = False         # D already sent since the last arm(): send it once

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
        self._limp_sent = False
        self.link.send("A")
        self.armed = True
        self._task = asyncio.create_task(self._heartbeat())
        return None

    async def disarm(self, park_first: bool = True, timeout_s: float = 15.0) -> None:
        """Ramp to the park pose, THEN send D (go limp). D-number: D24.

        D makes every servo limp at once, so sending it mid-reach drops the arm. Park is the
        pose a limp arm rests in, so going there first makes "limp" a non-event. The ramp
        (and the firmware limiter behind it) keeps that move at the normal speed caps.

        park_first=False is the EMERGENCY STOP: D right now, wherever the arm is. It also
        works WHILE a park ramp is running (the page's "Stop now" button, PR #15 review):
        the waiting call sees armed go False, stops waiting, and D is sent only once.

        Straight to D as well when there is nothing safe to ramp with: not armed, the
        heartbeat has stopped, the link is down or the Nano is not ARMED. If the park move
        is refused on the way (_advance holds) or not reached within timeout_s, go limp
        where it stopped and say so in `fault`, so the page shows it.
        """
        try:
            if (park_first and not self.parking and self.armed and self._task is not None
                    and self.link.connected and self.link.state == "ARMED"):
                self.parking = True
                park = self.park_values()
                self.goal_values = list(park)
                loop = asyncio.get_running_loop()
                deadline = loop.time() + timeout_s
                while self.armed and self.target_values != park:
                    if self.goal_values != park:         # _advance refused a step and held
                        self._park_failed("the park move was refused on the way")
                        break
                    if loop.time() >= deadline:
                        self._park_failed(f"park not reached within {timeout_s:.0f} s")
                        break
                    await asyncio.sleep(self.period_s)
                if self.armed and self.target_values == park:
                    await asyncio.sleep(self.period_s)   # let the final park frame go out
        finally:
            # Always runs, even if the wait is cancelled (server shutting down, browser gone):
            # a disarm that never sends D would leave the arm powered with nobody driving it.
            self.parking = False
            self.armed = False
            if self._task:
                self._task.cancel()
                self._task = None
            if self.link.connected and not self._limp_sent:
                self.link.send("D")
                self._limp_sent = True

    def _park_failed(self, why: str) -> None:
        log.error("disarm: %s; going limp where the arm is", why)
        self.fault = f"disarm: {why}; went limp where it stopped"

    # ------------------------------------------------------------------ targets
    def set_target(self, values: list[float]) -> str | None:
        """[j0..j3 degrees, gripper mm] -> new GOAL. Returns None if accepted, else why not.

        The arm doesn't jump there: the heartbeat ramps the sent target toward it.
        """
        if not self.armed:
            return "not armed: press Arm first"
        if self.parking:
            return "disarming: moving to the park pose first"
        try:
            self.cal.to_pulses(values)  # validate the END pose; the poses on the way are inside the same box
        except ValueError as e:
            return str(e)              # rejected: the goal (and the ramp) stays as it was
        self.goal_values = list(values)
        return None

    def _advance(self) -> None:
        """One ramp step: move the sent target toward the goal."""
        if self.goal_values is None or self.target_values == self.goal_values:
            return
        nxt = step_toward(self.target_values, self.goal_values, self.max_step)
        nxt = self._cap_four_bar_elbow(self.target_values, nxt)
        try:
            us = self.cal.to_pulses(nxt)
        except ValueError as e:        # only a ramp bug gets here: stop where we are
            log.warning("ramp produced an invalid pose, holding: %s", e)
            self.goal_values = list(self.target_values)
            return
        self.target_values, self.target_us = nxt, us

    def _cap_four_bar_elbow(self, cur: list[float], nxt: list[float]) -> list[float]:
        """Four-bar (D19): the elbow SERVO turns by d(theta1) + d(theta2), not d(theta2).

        step_toward caps theta1 and theta2 separately, so together the elbow servo could be
        asked for twice its speed, more than the firmware's own J2 cap (PR #12) allows; the
        firmware would then lag and bend the path. If that sum is over J2's step, shrink the
        WHOLE step by the same fraction: every joint keeps its share, so they still arrive
        together, just a little later.

        An elbow speed of 0 or less means "theta2 is frozen" (same rule as step_toward). The
        servo still has to turn with the shoulder to hold theta2, so there is no step that keeps
        it still: leave the step alone and let the firmware's own J2 cap be the guard. Scaling
        by 0 here froze the whole arm, and a negative speed reversed it (PR #15 review, Ishaan).
        """
        if "four_bar_window" not in self.cal.cal["joints"]["j2_elbow"]:
            return nxt
        if self.max_step[2] <= 0:
            return nxt
        servo_move = abs((nxt[1] - cur[1]) + (nxt[2] - cur[2]))
        if servo_move <= self.max_step[2] + 1e-9:
            return nxt
        f = self.max_step[2] / servo_move
        return [c + (n - c) * f for c, n in zip(cur, nxt)]

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
        return {**self.link.status(), "armed": self.armed, "fault": self.fault, "parking": self.parking,
                "target_us": self.target_us,
                "target_values": self.target_values, "goal_values": self.goal_values,
                "moving": self.goal_values is not None and self.target_values != self.goal_values}
