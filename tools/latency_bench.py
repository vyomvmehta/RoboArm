"""Partial V2-13: SOFTWARE-ONLY latency budget of the V2 pipeline (2026-11-21).

THIS IS NOT HAND-TO-ARM LATENCY. Every number is time.perf_counter() on the laptop, from "frame in
hand" to "C frame handed to the (fake) Nano link". It can't see sensor exposure, driver buffering,
USB-serial time to a real Nano, the firmware or the servos: that needs the real arm and a slow-motion
camera (the rest of V2-13).

TWO MODES
  --replay CLIP.csv   No camera. Recorded landmarks (runs/hands/*.csv) are fed, at the clip's own
                      frame timing, through  pinch -> HandMapper (OneEuro as its smooth= hook) ->
                      Controller.set_target -> 30 Hz heartbeat -> FakeNano.
                      Measures the DOWNSTREAM stages only. It SKIPS camera capture and MediaPipe
                      inference, which are probably the biggest costs. The clip is looped (with a
                      1 s gap, so the filter restarts cleanly) until --frames frames are measured.
                      ~1000 frames of a 30 fps clip take ~35-40 s.
  --live              Webcam at 1280x720 -> arm/vision/hands.py (Camera + HandTracker/MediaPipe) ->
                      the same chain. Adds camera wait, frame interval and tracking time.
                      HOLD ONE HAND IN VIEW, palm to the camera, moving slowly around the frame,
                      FOR ABOUT A MINUTE: only frames with a tracked hand reach the mapper and
                      set_target, so 1000 measured frames take ~40-60 s at 30 fps, plus 60 warm-up
                      frames. Close every other app using the camera first. If the camera gives no
                      frame within --camera-timeout seconds the run stops with a message (no hang).

STAGES (ms per frame; "live" = --live only)
  camera_wait     live: blocked in Camera.read() waiting for the next frame (not processing)
  track           live: HandTracker.process = BGR->RGB + MediaPipe hand landmarker
  pinch           pinch_fraction
  map_pre         HandMapper.map up to the filter (hand box -> work box)
  filter          OneEuro (timed through HandMapper's own smooth= hook)
  map_post        clamp + point_to_joints (workspace, IK, joint limits, base clearance)
  set_target      Controller.set_target (calibration + collision check, store the goal)
  to_send         set_target returned -> next heartbeat C frame handed to the link. set_target only
                  stores a goal; the 30 Hz heartbeat sends it, so this is ~0-33 ms by design.
  processing      frame in hand -> set_target returned
  total           frame in hand -> C frame handed to the link   (processing + to_send)
  frame_interval  live: between Camera.read() returns.  replay: the interval RECORDED in the clip.
  track (no hand) live: tracking time on frames with no hand (MediaPipe runs full palm detection)
  heartbeat interval  time between C frames as actually sent (nominal 33.3 ms at 30 Hz): explains
                  to_send values above one period

Instrumented from the OUTSIDE: no file under arm/ is changed. The pipeline runs in a worker thread
and the Controller's heartbeat in the asyncio loop, so a slow frame never delays a heartbeat.
arm/modes is NOT in the chain (no deadband, no follow_hz limit): every accepted target is sent.
Output: raw per-frame CSV in runs/latency/ and a summary table (markdown) on the console.

EXAMPLES
  .venv\\Scripts\\python tools\\latency_bench.py --replay runs\\hands\\sweep-20261120-224150.csv
  .venv\\Scripts\\python tools\\latency_bench.py --live                 (Vyom: hand in view ~1 min)
  .venv\\Scripts\\python tools\\latency_bench.py --live --camera 1 --frames 1500
"""
from __future__ import annotations

import argparse
import asyncio
import bisect
import concurrent.futures as cf
import csv
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.calibration import load_calibration  # noqa: E402
from arm.comms.link import FakeNano  # noqa: E402
from arm.config import load_arm  # noqa: E402
from arm.control import Controller  # noqa: E402
from arm.filtering import OneEuro, load_filter_config  # noqa: E402
from arm.gestures import load_gesture_config, pinch_fraction  # noqa: E402
from arm.mapping import HandMapper  # noqa: E402
from arm.vision.hands import Camera, HandTracker, load_csv  # noqa: E402

STAGES = ["camera_wait", "track", "pinch", "map_pre", "filter", "map_post", "set_target",
          "to_send", "processing", "total", "frame_interval"]
COLUMNS = ["mode", "frame", "t_s", "warmup", "visible", "accepted", "refused"] + [s + "_ms" for s in STAGES]
REPLAY_NOTE = ("REPLAY = DOWNSTREAM STAGES ONLY: camera capture and MediaPipe inference are NOT "
               "measured\n(probably the biggest costs). Run --live on a real camera for those.")
SOFTWARE_NOTE = "Software latency on the laptop only: NOT hand-to-arm latency."


class CameraFailed(RuntimeError):
    pass


def ms(a: float, b: float) -> float:
    return round((b - a) * 1000, 3)


# ------------------------------------------------------------------ frame sources
class ReplaySource:
    """Recorded HandFrames released at the clip's own timing, looped with a 1 s gap."""
    mode, has_capture = "replay", False

    def __init__(self, path: Path | str):
        self.frames = load_csv(path)
        if not self.frames:
            raise SystemExit(f"{path}: no frames")
        ts = [f.t for f in self.frames]
        self.t0, self.span = ts[0], ts[-1] - ts[0] + 1.0    # +1 s gap between loops
        self.i, self.start = 0, None

    def describe(self) -> str:
        f = self.frames[0]
        return f"replay of {len(self.frames)} recorded frames ({f.width}x{f.height}), looped"

    def next(self):
        """-> (frame, t_ready, recorded_interval_ms or None). Waits until the frame's due time."""
        n = len(self.frames)
        loop, k = divmod(self.i, n)
        src = self.frames[k]
        t = src.t - self.t0 + loop * self.span
        if self.start is None:
            self.start = time.perf_counter()
        delay = self.start + t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        ready = time.perf_counter()
        interval = ms(self.frames[k - 1].t, src.t) if k > 0 else None
        self.i += 1
        f = type(src)(t, src.visible, src.landmarks, src.width, src.height, src.handedness, src.score)
        return f, ready, interval

    def close(self):
        pass


class LiveSource:
    """Camera + MediaPipe. Every camera call has a timeout so a dead camera can't hang the run."""
    mode, has_capture = "live", True

    def __init__(self, args):
        self.timeout = args.camera_timeout
        self.pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera")
        self.cam = self._call(Camera, args.camera, args.width, args.height, what="opening the camera")
        first = self._call(self.cam.read, what="reading the first frame")
        h, w = first.shape[:2]
        if (w, h) != (args.width, args.height):
            raise CameraFailed(f"camera {args.camera} gives {w}x{h}, not {args.width}x{args.height}. "
                               "Use a camera that does, or pass --width/--height to match follow mode.")
        self.tracker = HandTracker()
        self.size, self.index = (w, h), args.camera
        self.start, self.prev = time.perf_counter(), None

    def _call(self, fn, *a, what: str):
        try:
            return self.pool.submit(fn, *a).result(timeout=self.timeout)
        except cf.TimeoutError:
            raise CameraFailed(f"no answer from the camera after {self.timeout:.0f} s while {what}. "
                               "Another app (browser tab, Camera, Teams) may be using it, or Windows "
                               "Settings > Privacy > Camera blocks desktop apps.") from None
        except RuntimeError as e:                  # hands.py: "did not open" / "stopped giving frames"
            raise CameraFailed(f"{e} (while {what})") from None

    def describe(self) -> str:
        return f"live camera {self.index} at {self.size[0]}x{self.size[1]}"

    def next(self):
        """-> (frame, t_ready, interval_ms or None, camera_wait_ms, track_ms)."""
        r0 = time.perf_counter()
        img = self._call(self.cam.read, what="reading a frame")
        r1 = time.perf_counter()
        hf = self.tracker.process(img, r1 - self.start)
        r2 = time.perf_counter()
        interval = ms(self.prev, r1) if self.prev is not None else None
        self.prev = r1
        return hf, r1, interval, ms(r0, r1), ms(r1, r2), r2

    def close(self):
        for fn in (getattr(self, "tracker", None) and self.tracker.close,
                   getattr(self, "cam", None) and self.cam.close):
            if fn:
                try:
                    self.pool.submit(fn).result(timeout=self.timeout)
                except Exception:
                    pass
        self.pool.shutdown(wait=False, cancel_futures=True)


# ------------------------------------------------------------------ pipeline
def run_pipeline(source, ctrl: Controller, args, rows: list[dict], stop: threading.Event):
    arm, gcfg = load_arm(), load_gesture_config()
    filt = OneEuro(load_filter_config())
    mark: dict[str, float] = {}

    def timed_filter(t, xyz):              # HandMapper's own smooth= hook: no mapper change
        mark["f0"] = time.perf_counter()
        out = filt(t, xyz)
        mark["f1"] = time.perf_counter()
        return out

    mapper = HandMapper(arm, smooth=timed_filter)
    print(f"{source.describe()}. Measuring {args.frames} full-chain frames.", flush=True)
    t_start, measured, i = time.perf_counter(), 0, 0
    while measured < args.frames and not stop.is_set():
        if time.perf_counter() - t_start > args.max_seconds:
            print(f"stopping after {args.max_seconds:.0f} s with {measured} measured frames "
                  "(was a hand in view?)", flush=True)
            break
        if source.has_capture:
            hf, r1, interval, cam_ms, track_ms, r2 = source.next()
        else:
            hf, r1, interval = source.next()
            cam_ms = track_ms = ""
            r2 = r1
        warm = i < args.warmup
        row = {"mode": source.mode, "frame": i, "t_s": round(r1 - t_start, 4), "warmup": int(warm),
               "visible": int(hf.visible), "accepted": 0, "refused": "",
               "camera_wait_ms": cam_ms, "track_ms": track_ms,
               "frame_interval_ms": "" if interval is None else interval}
        if hf.visible:
            pinch = pinch_fraction(hf.landmarks, gcfg)
            r3 = time.perf_counter()
            mark.clear()
            target = mapper.map(hf, pinch)
            r4 = time.perf_counter()
            row.update(pinch_ms=ms(r2, r3), map_pre_ms=ms(r3, mark["f0"]),
                       filter_ms=ms(mark["f0"], mark["f1"]), map_post_ms=ms(mark["f1"], r4))
            if target.refused:
                row["refused"] = "mapper: " + target.refused
            else:
                why = ctrl.set_target(target.pose())
                r5 = time.perf_counter()
                row["set_target_ms"] = ms(r4, r5)
                if why:
                    row["refused"] = "set_target: " + why
                else:
                    row.update(accepted=1, _r5=r5, _r1=r1, processing_ms=ms(r1, r5))
                    measured += 0 if warm else 1
        rows.append(row)
        i += 1
        if i % 300 == 0:
            print(f"  {i} frames, {measured}/{args.frames} measured", flush=True)


def fill_to_send(rows: list[dict], sends: list[float]) -> None:
    """to_send = set_target returned -> the first heartbeat C frame after it."""
    for row in rows:
        r5, r1 = row.pop("_r5", None), row.pop("_r1", None)
        if r5 is None:
            continue
        k = bisect.bisect_right(sends, r5)
        if k < len(sends):
            row["to_send_ms"] = ms(r5, sends[k])
            row["total_ms"] = ms(r1, sends[k])


def summary(rows: list[dict], mode: str, sends: list[float] | None = None) -> str:
    use = [r for r in rows if not r["warmup"]]
    acc = [r for r in use if r["accepted"]]
    out = [SOFTWARE_NOTE] + ([REPLAY_NOTE] if mode == "replay" else []) + [
        "", f"mode {mode}: frames {len(rows)} (warm-up {len(rows) - len(use)} excluded), "
        f"hand visible {sum(r['visible'] for r in use)}, full chain {len(acc)}, "
        f"refused {sum(bool(r['refused']) for r in use)}",
        "", "| stage | n | median ms | p95 ms | max ms |", "|---|---|---|---|---|"]
    for s in STAGES:
        src = use if s in ("camera_wait", "frame_interval") else acc
        v = np.array([r[s + "_ms"] for r in src if r.get(s + "_ms") not in (None, "")], float)
        if len(v):
            label = "frame_interval (recorded in clip)" if (s == "frame_interval" and mode == "replay") else s
            out.append(f"| {label} | {len(v)} | {np.median(v):.2f} | {np.percentile(v, 95):.2f} | {v.max():.2f} |")
    nohand = np.array([r["track_ms"] for r in use if not r["visible"] and r["track_ms"] != ""], float)
    if len(nohand):
        out.append(f"| track (no hand) | {len(nohand)} | {np.median(nohand):.2f} | "
                   f"{np.percentile(nohand, 95):.2f} | {nohand.max():.2f} |")
    if sends and len(sends) > 2:            # the Controller's own 30 Hz tick, as actually delivered
        hb = np.diff(sends) * 1000
        out.append(f"| heartbeat interval (C to C) | {len(hb)} | {np.median(hb):.2f} | "
                   f"{np.percentile(hb, 95):.2f} | {hb.max():.2f} |")
    return "\n".join(out)


async def main(args, source_factory=None) -> Path:
    try:
        source = source_factory() if source_factory else (
            ReplaySource(args.replay) if args.replay else LiveSource(args))
    except CameraFailed as e:
        print(f"CAMERA PROBLEM: {e}\nNothing measured.", file=sys.stderr, flush=True)
        os._exit(2)                        # a camera call may still be stuck in its thread
    link = FakeNano()
    sends: list[float] = []
    original = link._write

    def timed_write(line: str):            # this instance only: FakeNano itself is unchanged
        if line.startswith("C"):
            sends.append(time.perf_counter())
        original(line)

    link._write = timed_write
    comms = yaml.safe_load((ROOT / "config" / "comms.yaml").read_text(encoding="utf-8"))
    ctrl = Controller(link, load_calibration(load_arm()), comms["heartbeat_hz"])
    why = await ctrl.arm()
    if why:
        raise SystemExit(f"could not arm the fake arm: {why}")
    rows: list[dict] = []
    stop = threading.Event()
    failed = None
    try:
        await asyncio.to_thread(run_pipeline, source, ctrl, args, rows, stop)
        await asyncio.sleep(0.1)           # let the heartbeat send after the last set_target
    except CameraFailed as e:
        failed = e
    finally:
        stop.set()
        await ctrl.disarm(park_first=False)
        link.close()
        source.close()
    fill_to_send(rows, sends)
    out = Path(args.out) if args.out else (
        ROOT / "runs" / "latency" / f"latency-{source.mode}-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    if failed:
        print(f"CAMERA PROBLEM mid-run: {failed}\nPartial CSV: {shown}", file=sys.stderr, flush=True)
        os._exit(2)
    print(f"\nraw CSV: {shown}\n")
    print(summary(rows, source.mode, sends))
    return out


def parse(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--replay", metavar="CLIP.csv", help="recorded landmarks, no camera (downstream only)")
    m.add_argument("--live", action="store_true", help="webcam + MediaPipe + the same chain")
    p.add_argument("--frames", type=int, default=1000, help="full-chain frames to measure (default 1000)")
    p.add_argument("--warmup", type=int, default=None,
                   help="first frames excluded (default: 60 live, for model + exposure; 0 replay)")
    p.add_argument("--camera", type=int, default=0, help="live: OpenCV camera index (default 0)")
    p.add_argument("--width", type=int, default=1280, help="live: capture width (default 1280)")
    p.add_argument("--height", type=int, default=720, help="live: capture height (default 720)")
    p.add_argument("--camera-timeout", type=float, default=10,
                   help="live: stop if the camera doesn't answer within this many seconds (default 10)")
    p.add_argument("--max-seconds", type=float, default=180, help="give up after this long (default 180)")
    p.add_argument("--out", help="CSV path (default runs/latency/latency-<mode>-<time>.csv)")
    a = p.parse_args(argv)
    if a.warmup is None:
        a.warmup = 60 if a.live else 0
    return a


if __name__ == "__main__":
    asyncio.run(main(parse()))
