"""Demo controls (2026-11-20): saved poses and a pick-and-place sequence, on top of the Controller.

Nothing here talks to the Nano. Every move goes through Controller.set_target(), so it gets the
same checks (calibration limits, base clearance) and the same ramp as a slider or a point.

  PoseStore      named poses, [j0..j3 degrees, gripper mm], saved to config/demo_poses.yaml in
                 the order they were saved. Stored as JOINT ANGLES, not x/y/z: they are recorded
                 from wherever the real arm is, so replaying them needs no IK and can't land on a
                 different IK branch.
  move_and_wait  one move, waiting until the ramp has actually arrived.
  run_sequence   several moves in a row; the first refusal or interruption stops the whole run
                 and says why. A half-finished pick is safer stopped than carried on.

Why a sequence matters beyond the demo: the brief's success-rate and repeatability numbers need
the SAME motion run many times, and this is exactly that (and the skeleton of V2's replay).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "demo_poses.yaml"


class PoseStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self.poses: dict[str, list[float]] = {}
        if self.path.exists():
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            for name, values in (raw.get("poses") or {}).items():
                self.poses[str(name)] = [float(v) for v in values]

    def names(self) -> list[str]:
        return list(self.poses)

    def get(self, name: str) -> list[float]:
        if name not in self.poses:
            raise KeyError(f"no saved pose called {name!r}")
        return list(self.poses[name])

    def save(self, name: str, values: list[float]) -> None:
        name = name.strip()
        if not name:
            raise ValueError("give the pose a name")
        if len(values) != 5:
            raise ValueError(f"a pose has 5 values, got {len(values)}")
        self.poses[name] = [round(float(v), 2) for v in values]   # re-saving a name updates it in place
        self._write()

    def delete(self, name: str) -> None:
        self.poses.pop(name, None)
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        header = ("# Demo poses, saved from the web page (arm/demo.py). [j0, j1, j2, j3 deg, gripper mm].\n"
                  "# Recorded on the calibrated arm: re-record them if calibration.yaml changes.\n")
        body = yaml.safe_dump({"poses": self.poses}, sort_keys=False, default_flow_style=None)
        self.path.write_text(header + body, encoding="utf-8")


async def move_and_wait(controller, values: list[float], timeout_s: float = 20.0,
                        stop: asyncio.Event | None = None) -> str | None:
    """Ask for one pose and wait until the arm has ramped there. None = arrived, else why not."""
    why = controller.set_target(values)
    if why:
        return why
    want = list(values)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        if stop is not None and stop.is_set():
            return "stopped"
        if not controller.armed:
            return "the arm was disarmed"
        if controller.target_values == want:
            return None
        if controller.goal_values != want:
            # Someone else moved the goal, or the ramp held short (base clearance): either way
            # we are not going where this step meant to go.
            return getattr(controller, "blocked", None) or "the goal was changed by another input"
        if loop.time() > deadline:
            return f"did not arrive within {timeout_s:.0f} s"
        await asyncio.sleep(controller.period_s)


async def run_sequence(controller, steps: list[tuple[str, list[float]]], dwell_s: float = 0.3,
                       stop: asyncio.Event | None = None, on_step=None) -> str | None:
    """Move through (name, pose) steps in order. None = all done, else 'step N (name): why'.

    dwell_s: pause after each arrival, so a gripper that just closed has actually squeezed
    before the arm lifts (the ramp ends when the COMMAND arrives, not the fingers).
    """
    if not steps:
        return "no poses to run"
    for i, (name, values) in enumerate(steps, 1):
        if on_step:
            await on_step(i, name)
        why = await move_and_wait(controller, values, stop=stop)
        if why:
            return f"step {i} ({name}): {why}"
        await asyncio.sleep(dwell_s)
    return None
