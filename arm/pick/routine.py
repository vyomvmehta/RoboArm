"""The pick routine (V2-16): block position -> a checked sequence of poses -> run it safely.

pick_steps() turns a block's (x, y) into named poses: open above it, go down, close, lift, carry
to the drop zone, open, back home. EVERY pose goes through point_to_joints (workspace, IK, joint
limits, base clearance) up front, so an unreachable block is refused before the arm moves at all,
with the step and the reason.

run_pick() plays them with arm.demo.run_sequence (each step waits until the ramp has arrived,
stops on any refusal or manual input) and adds the safety gate: if your hand comes back into
the table area, the run stops where it is. Not resumed automatically: you point again.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from arm.config import ArmConfig
from arm.demo import run_sequence
from arm.targets import point_to_joints


class PickRefused(ValueError):
    pass


def pick_steps(arm: ArmConfig, block_xy: tuple[float, float], cfg: dict) -> list[tuple[str, list[float]]]:
    p, g = cfg["pick"], arm.raw["gripper"]
    open_mm = p["open_mm"] if p["open_mm"] is not None else g["open_mm"]
    close_mm = p["close_mm"] if p["close_mm"] is not None else g["closed_mm"]
    bx, by = block_xy
    dx, dy = p["drop_xy"]
    h = arm.raw["poses"]["home"]
    plan = [
        ("above block", (bx, by, p["approach_z"]), open_mm),
        ("down", (bx, by, p["grasp_z"]), open_mm),
        ("grab", (bx, by, p["grasp_z"]), close_mm),
        ("lift", (bx, by, p["lift_z"]), close_mm),
        ("above drop", (dx, dy, p["lift_z"]), close_mm),
        ("lower", (dx, dy, p["drop_z"]), close_mm),
        ("release", (dx, dy, p["drop_z"]), open_mm),
        ("clear", (dx, dy, p["lift_z"]), open_mm),
        ("home", (h["x"], h["y"], h["z"]), open_mm),
    ]
    steps = []
    for name, (x, y, z), grip in plan:
        pitch = h["pitch"] if name == "home" else p["pitch_deg"]
        try:
            joints = point_to_joints(arm, x, y, z, pitch)
        except ValueError as e:
            raise PickRefused(f"step '{name}' at ({x:.0f}, {y:.0f}, {z:.0f}) mm: {e}") from None
        steps.append((name, joints + [float(grip)]))
    return steps


async def run_pick(controller, steps, hand_clear: Callable[[], bool], dwell_s: float = 0.4,
                   on_step=None, stop: asyncio.Event | None = None) -> str | None:
    """None = picked and placed. Otherwise why it stopped (hand came back, refusal, stop...)."""
    if not hand_clear():
        return "your hand is in the table area: move it away first"
    stop = stop or asyncio.Event()
    why_hand = []

    async def watch():                         # the safety gate, checked every heartbeat
        while not stop.is_set():
            if not hand_clear():
                why_hand.append(True)
                stop.set()
                return
            await asyncio.sleep(controller.period_s)

    watcher = asyncio.create_task(watch())
    try:
        why = await run_sequence(controller, steps, dwell_s=dwell_s, stop=stop, on_step=on_step)
    finally:
        stop.set()
        await watcher
    if why_hand:
        # Freeze where we are: the goal becomes the pose being sent right now.
        controller.set_target(list(controller.target_values))
        return "stopped: your hand came back into the table area"
    return why
