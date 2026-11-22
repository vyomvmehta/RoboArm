# V2 software latency budget (partial V2-13)

> **Software latency only, NOT hand-to-arm latency.** Every number is `time.perf_counter()` on the
> laptop, from "frame in hand" to "C frame handed to the Nano link" (a `FakeNano`). Not included:
> sensor exposure, camera driver buffering, USB-serial to the real Nano, firmware, servo motion.
> Hand-to-arm latency needs the real arm and a slow-motion camera (the rest of V2-13).

Harness: `tools/latency_bench.py` (`--help` has the full guide). Chain:

```
[live only] Camera.read -> HandTracker (MediaPipe)
pinch_fraction -> HandMapper.map [hand box -> work box | OneEuro | clamp + point_to_joints IK]
-> Controller.set_target -> next 30 Hz heartbeat tick -> FakeNano
```

Instrumented from outside: no file under `arm/` is changed. OneEuro is timed through HandMapper's
own `smooth=` hook, and the C frames through a wrapper on one FakeNano instance. The pipeline runs
in a worker thread and the heartbeat in asyncio. `arm/modes` is not in the chain (no deadband or
rate limit), so every accepted target is sent.

## Replay: MEASURED (downstream stages only)

**Skips camera capture and MediaPipe inference**, probably the biggest costs. Recorded landmarks
are replayed at the clip's own frame timing through everything after tracking.

Run 2026-11-21: `runs/hands/sweep-20261120-224150.csv` (706 frames, 1280x720), looped to
1,000 full-chain frames, 0 refused. Laptop: Intel 24-core, Python 3.12.11, Windows 11.
Raw CSV: `runs/latency/latency-replay-20261121-041508.csv`.

| stage | median ms | p95 ms | max ms |
|---|---|---|---|
| pinch | 0.17 | 0.39 | 3.23 |
| map_pre (hand box -> work box) | 0.09 | 0.18 | 0.64 |
| filter (OneEuro) | 0.02 | 0.04 | 0.21 |
| map_post (clamp + IK + clearance) | 1.84 | 3.98 | 8.16 |
| set_target | 1.56 | 3.52 | 9.04 |
| **processing** (frame in hand -> goal set) | **3.67** | **8.15** | **13.17** |
| to_send (goal set -> next heartbeat C) | 10.14 | 39.15 | 49.12 |
| **total** (frame in hand -> C sent) = processing + to_send, see below | **14.89** | **44.21** | **53.95** |
| frame interval (recorded in the clip) | 32.30 | 45.70 | 50.10 |
| heartbeat interval (C to C, nominal 33.3) | 32.88 | 48.62 | 58.66 |

### Total vs processing: where the ~11 ms goes

`total` is exactly `processing + to_send` (checked per frame in the tests). The whole gap between
~15 ms and ~4 ms is **`to_send`: waiting for the Controller's 30 Hz heartbeat to send the goal.**
It is **not a replay artefact**, and it exists on the real system too. Checked against the code:

- **Not replay pacing.** The replay sleeps until a frame is due *before* the "frame in hand"
  timestamp, so that wait is outside `processing` and `total`.
- **Not simulated serial timing.** `FakeNano` has no simulated delay, and the C frame is
  timestamped as it is handed to the link, before FakeNano does anything with it. Real
  USB-serial time to the Nano is not measured at all and would come **on top**.
- **Not the follow-mode rate limit.** `arm/modes` (`modes.follow_hz: 30`, `deadband_mm`) is not
  in this chain, so every target goes straight to `set_target`. In follow mode that limit can
  drop frames, but it doesn't add a wait to the ones it passes.
- **It is the heartbeat** (`config/comms.yaml heartbeat_hz: 30`, `Controller._heartbeat`).
  `set_target` only stores the goal, and the next tick sends a ramp step toward it. Camera
  frames and ticks run on unrelated clocks, so a goal waits 0-33 ms, ~17 ms on average. Late
  ticks on Windows stretch the tail (p95 39 ms). The real Controller has the same wait.

**So: pipeline compute is ~4 ms median (8 ms p95). The ~15 ms total includes ~10-18 ms of
heartbeat wait**, and the median of that wait moves between runs because frames (~32.3 ms) and
ticks (~32.9 ms) run at nearly the same rate, so their phase drifts only slowly within a 35 s run.
Quote the wait as "up to one heartbeat period (33 ms), ~17 ms average", not as pipeline cost.
Raising `heartbeat_hz` would shrink it. The firmware watchdog only sets a lower bound.

What it says:
- **Downstream processing is small:** ~4 ms median, under 9 ms at p95. IK + base clearance
  (`map_post`) and `set_target`'s calibration + collision check are most of it. The filter
  costs almost nothing.
- **Waiting for the heartbeat dominates downstream.** `set_target` only stores a goal; the 30 Hz
  heartbeat sends it. The expected wait is half a period (~17 ms), and up to a full period.
- **The heartbeat ticks late sometimes:** the C-to-C interval reaches 49 ms at p95 and 59 ms
  max against a nominal 33.3 ms, which pushes `to_send` above one period. Likely cause: Windows
  timer resolution under `asyncio.sleep` (not investigated further). The fixed-clock schedule
  catches up, so the median stays on time.
- **The camera interval is the floor:** a new hand position only arrives every ~32 ms (p95 46).
- **Run-to-run spread:** a second identical run gave a `to_send` median of 17.7 ms and a
  processing p95 of 3.9 ms. Phase between frames and ticks, plus machine load, moves these by a
  few ms, so treat single-digit differences as noise.

## Live: PENDING (Vyom, on his camera)

Measures what replay can't: camera wait, frame interval, MediaPipe tracking (with and without
a hand). Not run here: no camera is available on this machine.

1. Close every app using the camera. Camera at 1280x720 (the run stops if it isn't).
2. **Hold one hand in view, palm to the camera, moving slowly, for about a minute**
   (60 warm-up frames + 1,000 measured, ~40-60 s at 30 fps). Frames without a hand don't
   reach the mapper.
3. Run:
   ```
   .venv\Scripts\python tools\latency_bench.py --live
   ```
   (`--camera 1` for another camera.) If the camera gives no frame within 10 s, it stops with
   a message instead of hanging.
4. Paste the printed table here under "Live", and commit the CSV from `runs/latency/`.

| stage | median ms | p95 ms | max ms |
|---|---|---|---|
| camera_wait | pending | | |
| track (MediaPipe) | pending | | |
| processing | pending | | |
| total | pending | | |
| frame interval | pending | | |
| track, no hand | pending | | |

## Reproduce the replay

```
.venv\Scripts\python tools\latency_bench.py --replay runs\hands\sweep-20261120-224150.csv
```
Tests: `tests/test_latency_bench.py` (replay end to end; live camera failures with stand-in cameras).
