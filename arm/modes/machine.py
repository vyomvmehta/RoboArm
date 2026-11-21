"""V2-7: what the arm does with each camera frame (2026-11-20).

Modes (picked with buttons on the page; Vyom, Nov 20):
  off      camera ignored.
  command  only CONFIRMED gestures act (0.5 s hold): fist -> home, palm -> hold where it is,
           thumbs-up -> replay the last recording.
  follow   the gripper follows the hand (V2-5 mapping); the pinch drives the gripper.
  record   follow + store a pose every record_every_s (and on every gripper change).
           Leaving record saves it as the "last recording".
  replay   plays the last recording (arm/demo.run_sequence: waits for each pose, stops on refusal).
  point    point to pick (V2-16): fingertip on a block for 0.5 s -> pick it once the hand has left
           the table area. Needs the camera image and a table calibration.

The only gesture inside follow / record / replay / point is the EXIT: an open palm held STILL for
exit_hold_s (2 s) -> command mode, arm holds. Still, because a relaxed open hand is normal while
following: moving it keeps following. All other gestures are ignored there, because a pinching
hand sometimes reads as a fist (seen in the Nov 20 clips) and must not send the arm home.

Safety rules (each has a test):
  - DEAD-MAN: hand lost in follow/record -> HOLD where the arm is now. Never carry on to "where
    the hand was last" (the ramp would otherwise keep moving to the old goal).
  - Every move goes through Controller.set_target (limits, base clearance, ramp). A refused target
    is not sent: the arm keeps the last good goal and the reason shows in status.
  - Not armed -> nothing is sent. Disarm / Stop now / manual input on the page are handled by the
    server (V2-8): it calls stop() before acting, so the operator always wins.
"""
from __future__ import annotations

import asyncio
import math
from collections import deque
from pathlib import Path

import yaml

from arm.demo import run_sequence
from arm.gestures import Confirmer, classify, pinch_fraction
from arm.mapping import HandMapper
from arm.targets import point_to_joints
from arm.vision.hands import HandFrame

MODES = ("off", "command", "follow", "record", "replay", "point")
HAND_MODES = ("follow", "record", "replay", "point")      # modes where only the exit gesture counts
DEFAULT_RECORDINGS = Path(__file__).resolve().parents[2] / "config" / "recordings.yaml"


class RecordingStore:
    """Named pose sequences (record mode). 'last' is what thumbs-up replays."""

    def __init__(self, path: Path | str = DEFAULT_RECORDINGS):
        self.path = Path(path)
        self.recs: dict[str, list[list[float]]] = {}
        if self.path.exists():
            self.recs = (yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}).get("recordings", {}) or {}

    def save(self, name: str, poses: list[list[float]]) -> None:
        self.recs[name] = [[round(float(v), 2) for v in p] for p in poses]
        self.recs["last"] = self.recs[name]
        self.path.write_text("# Recordings from record mode (arm/modes). [j0..j3 deg, gripper mm] per pose.\n"
                             + yaml.safe_dump({"recordings": self.recs}, sort_keys=False, default_flow_style=None),
                             encoding="utf-8")

    def get(self, name: str = "last") -> list[list[float]] | None:
        return self.recs.get(name)


class ModeMachine:
    def __init__(self, controller, arm, gesture_cfg, modes_cfg: dict, mapper: HandMapper | None = None,
                 recordings: RecordingStore | None = None, pick=None):
        """pick: optional dict for point mode with keys cal, cfg (pick.yaml), and the
        arm.pick functions are imported lazily so V2-7 runs without a table calibration."""
        self.c, self.arm, self.gcfg, self.mcfg = controller, arm, gesture_cfg, modes_cfg
        self.mapper = mapper or HandMapper(arm)
        self.recordings = recordings or RecordingStore()
        self.pick = pick
        self.mode = "off"
        self.command_confirm = Confirmer(gesture_cfg.hold_to_confirm_s, gesture_cfg.min_visible_fraction)
        self.exit_confirm = Confirmer(modes_cfg["exit_hold_s"], gesture_cfg.min_visible_fraction)
        self._task: asyncio.Task | None = None           # replay / pick run in the background
        self._stop = asyncio.Event()
        self._recording: list[list[float]] = []
        self._last_rec_t = -1e9
        self._last_sent_t = -1e9
        self._last_xyz = None
        self._held_for_lost = False
        self.status: dict = {"mode": self.mode}
        self._selector = self._gate = None
        self._now = 0.0
        self._palm_track: deque = deque()                # (t, palm centre px, palm size) for the exit

    # ------------------------------------------------------------------ buttons
    async def set_mode(self, mode: str) -> str | None:
        """Called by the page buttons. Returns None, or why the switch was refused."""
        if mode not in MODES:
            return f"unknown mode {mode!r}"
        if mode == "point" and not self.pick:
            return "point to pick needs a table calibration (tools/table_calibrate.py)"
        if mode == "replay" and not self.recordings.get():
            return "nothing recorded yet: use record first"
        await self.stop()                                # finish whatever ran before
        if self.mode == "record":
            self._save_recording()
        self.mode = mode
        self.command_confirm.reset()
        self.exit_confirm.reset()
        self._held_for_lost, self._last_xyz = False, None
        if mode == "record":
            self._recording, self._last_rec_t = [], -1e9
        if mode == "replay":
            self._start(self._replay())
        if mode == "point":
            from arm.pick.select import HandGate, PointSelector
            self._selector = PointSelector(self.pick["cfg"])
            self._gate = HandGate(self.pick["cal"].area_polygon(self.pick["cfg"]["safety"]["margin_px"]),
                                  self.pick["cfg"]["safety"]["clear_s"])
        self.status = {"mode": self.mode}
        return None

    async def stop(self) -> None:
        """Stop any background run (replay / pick). The server calls this before manual input."""
        if self._task and not self._task.done():
            self._stop.set()
            await self._task
        self._task = None

    # ------------------------------------------------------------------ every camera frame
    async def step(self, frame: HandFrame, image=None) -> dict:
        st = {"mode": self.mode, "hand": frame.visible, "gesture": None, "confirmed": None,
              "target": None, "refused": None, "busy": self._task is not None and not self._task.done()}
        self._now = frame.t                              # camera clock, used by the pick's gate wait
        try:
            label = classify(frame.landmarks, self.gcfg) if frame.visible else None
        except ValueError:                               # degenerate landmarks: treat as no gesture
            label = None
        st["gesture"] = label

        if self.mode == "off" or not self.c.armed:
            self.status = st
            return st

        if self.mode in HAND_MODES:
            if self.exit_confirm.update("palm" if self._still_palm(frame, label) else None, frame.t) == "palm":
                await self._exit_to_command()
                st.update(mode=self.mode, confirmed="exit")
                self.status = st
                return st
        else:                                            # command
            fired = self.command_confirm.update(label, frame.t)
            st["confirmed"] = fired
            if fired:
                await self._command(fired, st)

        if self.mode in ("follow", "record"):
            await self._follow(frame, st)
        elif self.mode == "point" and image is not None:
            await self._point(frame, image, st)
        self.status = st
        return st

    # ------------------------------------------------------------------ the modes
    async def _command(self, gesture: str, st: dict) -> None:
        if gesture == "fist":
            h, goal = self.arm.raw["poses"]["home"], self.c.goal_values or self.c.park_values()
            try:
                pose = point_to_joints(self.arm, h["x"], h["y"], h["z"], h["pitch"]) + [goal[4]]
            except ValueError as e:
                st["refused"] = f"home: {e}"
                return
            st["refused"] = self.c.set_target(pose)
        elif gesture == "palm":
            self._hold()
        elif gesture == "thumbs_up":
            if self.recordings.get():
                self.mode = "replay"
                self._start(self._replay())
            else:
                st["refused"] = "thumbs-up: nothing recorded yet"

    async def _follow(self, frame: HandFrame, st: dict) -> None:
        if not frame.visible:
            if not self._held_for_lost:                  # DEAD-MAN: stop exactly where it is
                self._hold()
                self._held_for_lost = True
            st["refused"] = "hand lost: holding"
            return
        self._held_for_lost = False
        t = self.mapper.map(frame, pinch_fraction(frame.landmarks, self.gcfg))
        st["target"] = {"x": t.x, "y": t.y, "z": t.z, "gripper_mm": t.gripper_mm, "edge": t.clamped}
        if t.refused:                                    # keep the last good goal; say why
            st["refused"] = t.refused
            return
        xyz = (t.x, t.y, t.z, t.gripper_mm)
        if frame.t - self._last_sent_t < 1.0 / self.mcfg["follow_hz"]:
            return
        if self._last_xyz and math.dist(xyz[:3], self._last_xyz[:3]) < self.mcfg["deadband_mm"] \
                and abs(xyz[3] - self._last_xyz[3]) < 0.5:
            return                                       # jitter only: don't wake the ramp
        why = self.c.set_target(t.pose())
        if why:
            st["refused"] = why
            return
        self._last_sent_t, self._last_xyz = frame.t, xyz
        if self.mode == "record":
            gripper_changed = (self._recording and abs(self._recording[-1][4] - t.gripper_mm) >= 1.0)
            if frame.t - self._last_rec_t >= self.mcfg["record_every_s"] or gripper_changed:
                self._recording.append(t.pose())
                self._last_rec_t = frame.t
            st["recorded"] = len(self._recording)

    async def _point(self, frame: HandFrame, image, st: dict) -> None:
        from arm.pick.blocks import detect_blocks
        from arm.pick.routine import PickRefused, pick_steps, run_pick
        gate_open = self._gate.update(frame, frame.t)
        st["hand_clear"] = gate_open
        if self._task is not None and not self._task.done():
            return                                       # a pick is running; the gate watches it
        blocks = detect_blocks(image, self.pick["cal"], self.pick["cfg"])
        st["blocks"] = [b.mm for b in blocks]
        chosen = self._selector.update(frame, blocks, frame.t)
        if chosen is None:
            return
        try:
            steps = pick_steps(self.arm, chosen.mm, self.pick["cfg"])
        except PickRefused as e:
            st["refused"] = str(e)
            return
        st["selected"] = chosen.mm
        gate = self._gate

        async def go():
            # Wait for the hand to leave the table area for clear_s (the gate is updated by
            # every camera frame in step(); self._now is the latest frame's time).
            while not gate.clear(self._now) and not self._stop.is_set():
                await asyncio.sleep(self.c.period_s)
            if self._stop.is_set():
                return "stopped"
            return await run_pick(self.c, steps, hand_clear=lambda: not gate.inside,
                                  dwell_s=self.pick["cfg"]["pick"]["dwell_s"], stop=self._stop)
        self._start(go())

    async def _replay(self) -> str | None:
        rec = self.recordings.get() or []
        why = await run_sequence(self.c, [(f"pose {i + 1}", p) for i, p in enumerate(rec)],
                                 dwell_s=0.0, stop=self._stop)
        self.mode = "command"                            # replay done (or stopped): back to command
        return why

    # ------------------------------------------------------------------ helpers
    def _still_palm(self, frame: HandFrame, label) -> bool:
        """Open palm AND held still (exit gesture). A moving open hand is just following."""
        if label != "palm":
            self._palm_track.clear()
            return False
        c = frame.landmarks[[0, 5, 9, 13, 17], :2].mean(axis=0)
        self._palm_track.append((frame.t, c, frame.palm_size()))
        while self._palm_track and frame.t - self._palm_track[0][0] > self.mcfg["exit_hold_s"]:
            self._palm_track.popleft()
        pts = [p for _, p, _ in self._palm_track]
        span = max(math.dist(a, b) for a in pts for b in pts[-1:]) if len(pts) > 1 else 0.0
        return span <= self.mcfg["exit_still"] * frame.palm_size()

    def _hold(self) -> None:
        if self.c.target_values is not None:
            self.c.set_target(list(self.c.target_values))   # goal = where it is right now

    async def _exit_to_command(self) -> None:
        await self.stop()
        if self.mode == "record":
            self._save_recording()
        self.mode = "command"
        self._hold()
        self.command_confirm.reset()

    def _save_recording(self) -> None:
        if len(self._recording) >= 2:
            self.recordings.save("last", self._recording)
        self._recording = []

    def _start(self, coro) -> None:
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(coro)
