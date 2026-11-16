"""The laptop-side speed limit (ramp), 2026-11-15.

The Controller (arm/control.py) keeps two poses:
    goal    what the user asked for (a slider position or a point from IK)
    target  what the heartbeat actually sends, 30 times a second
Every tick it calls step_toward() to move `target` a little closer to `goal`, so a big
request becomes a smooth move at the speeds in config/arm.yaml instead of a jump.

This is the laptop twin of the firmware motion limiter (Ishaan, CLAUDE.md section 5.5).
Two layers on purpose: the laptop ramp keeps normal use smooth; the firmware limiter
still protects the arm if the laptop has a bug or a stale frame arrives.

step_toward: Vyom writes this (core learning piece: same idea as the motion limiter).
Run its tests:  py -m pytest tests/test_motion.py -q
"""
from __future__ import annotations


def step_toward(current: list[float], goal: list[float], max_step: list[float]) -> list[float]:
    """One heartbeat tick: return the new pose, moved from `current` toward `goal`.

    All three lists have 5 entries: j0..j3 in degrees, gripper in mm.
    max_step[i] = the most joint i may move in ONE tick (speed x tick time), always > 0.

    Must:
      - move each joint toward its goal by at most max_step[i]
      - never overshoot: when a joint is within max_step[i] of its goal, land exactly on it
      - work in both directions (goal above or below current)
      - return a NEW list; don't modify `current`

    Design choice (Vyom, Nov 15): all joints ARRIVE TOGETHER, so moves look uniform and are
    easy to follow; each joint at its own top speed looked too chaotic to watch. So joints
    move at DIFFERENT speeds: the one with the longest trip (in ticks) goes at its limit and
    the rest are slowed to finish at the same moment.

    Recomputing every tick keeps them in step: after a tick every joint has covered the same
    fraction of its trip, so the remaining trips keep the same proportions.
    """
    # 1. How many ticks the whole move needs = the slowest joint's trip at its own top speed.
    ticks = max(abs(g - c) / s for c, g, s in zip(current, goal, max_step))

    # 2. Within one tick of the goal (or already there): land exactly on it, no overshoot.
    if ticks <= 1:
        return list(goal)

    # 3. Everyone covers 1/ticks of their remaining trip. The slowest joint's share is exactly
    #    its max_step; every other joint's share is smaller, so no joint exceeds its limit.
    return [c + (g - c) / ticks for c, g in zip(current, goal)]
