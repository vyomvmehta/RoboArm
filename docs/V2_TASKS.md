# V2: gesture control — task page

Started 2026-11-20 (Fri). Branch `v2/gestures`. V2 = the hand-gesture control in CLAUDE.md §1/§5, built **on top of V1**:
the gesture pipeline only produces a 5-value pose and hands it to the same `Controller.set_target()`
as the web page. So V2 inherits, for free, everything V1 already enforces: calibration limits, base
clearance (D23), the laptop ramp, the elbow cap, the firmware limiter, Disarm / Stop now (D24).

```
webcam -> MediaPipe landmarks -> filter -> hand -> (x, y, z, pitch) -> IK (point_to_joints) -> Controller.set_target -> ramp -> Nano
                               \-> gestures (pinch, fist, palm, thumbs-up) -> modes (mimic / command / record / replay)
```

**Rule for this weekend:** V1 comes first. Nothing here runs on the real arm until V1 has passed on
Sunday (calibrated joints, a working pick-and-place). Until then everything runs on `--fake` with
the web page's side/top views as the simulator.

**Nov 20 progress:** V2-0 done (Python 3.12 `.venv`, mediapipe 1.2.3 Tasks API, model in `models/`). V2-1/V2-2 done: 14 tests on synthetic hands, and Vyom confirmed live (one hand tracked; fist, palm, thumbs-up all confirmed). V2-3 clips recorded Nov 20 (`runs/hands/`, renamed by content: pinch, fist, palm, thumbs_up, sweep, lost). They showed the open palm never counted (thumb rule too strict): palm is now four straight fingers, thumb threshold 0.75 → 0.60. **Watch for V2-7:** a pinching hand sometimes reads as fist / thumbs-up / palm, so in mimic mode command gestures must be off except one agreed exit gesture. Tracked in Notion (Tasks: V2-0 … V2-15).

Status: ☐ todo · ◐ in progress · ☑ done. Owner "Claude" = boilerplate Claude writes, Vyom reviews.
**Split (Nov 20):** Ishaan takes the lighter half: the filter (V2-4) and depth calibration (V2-6), both core learning pieces (he writes them, Claude gives hints only). Vyom takes the critical path: mapping (V2-5), modes (V2-7), page + server (V2-8). Checkers swap: Vyom checks Ishaan's, Ishaan checks Vyom's.

**Interfaces agreed up front so nobody waits:** filter `f = OneEuro(cfg); xyz = f(t, xyz)` (mapping passes values straight through until it exists); depth `palm_px -> distance_cm` (mapping uses a fixed z until it exists).

## Setup (each laptop, once)

```
py install 3.12
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-v2.txt
mkdir models
curl -L -o models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
.venv\Scripts\python tools\hand_view.py
```
MediaPipe 1.x only has the Tasks API (`mp.solutions` is gone), which needs that model file (7.8 MB, git-ignored).

## Phase A: runs on the laptop only (Fri night – Sat)

| # | Task | Owner | Est. | Needs | Status |
|---|---|---|---|---|---|
| V2-0 | **Python env with MediaPipe** (see "Setup" below). The laptop's default Python 3.14 has no MediaPipe, so V2 runs in a 3.12 `.venv`. | Vyom | 20 min | — | ☑ |
| V2-1 | **`arm/vision/hands.py`**: camera capture + MediaPipe Hands → 21 landmarks per frame (image-normalised + palm size), "hand visible / lost". Plus a **recorder** that saves landmark streams to CSV, so every later step is tested from recordings, not a live camera. | Claude | 1 h | V2-0 | ☑ |
| V2-2 | **`arm/gestures/`**: pinch distance normalised by palm size; fist / open palm / thumbs-up classifier; **hold-to-confirm** (a gesture must hold ~0.5 s before it counts). Thresholds in `config/gestures.yaml`. Tests on recorded clips. | Claude | 1.5 h | V2-1 | ☑ |
| V2-3 | **Record test clips**: 20–30 s each of pinch open/close, fist, palm, thumbs-up, slow and fast hand sweeps, hand leaving the frame. These become the test fixtures. | Vyom | 20 min | V2-1 | ☑ |
| V2-4 | **Smoothing filter** (core learning piece): EMA first, then a **One Euro filter**; measure jitter vs lag on the recorded clips and pick parameters. | **Ishaan** (hints) | 1.5 h | V2-3 | ☐ |
| V2-5 | **`arm/mapping/`**: hand position → gripper target (x, y, z mm) in a box inside the workspace; clamp to the workspace; pinch → gripper mm; fixed pitch −90 for picking. | Vyom (+ Claude) | 1 h | V2-2 | ☐ |
| V2-6 | **Depth from palm size** (core learning piece, calibration maths): hold the hand at 3–4 known distances, fit z vs apparent palm size, store in `gestures.yaml`. | **Ishaan** (hints) | 45 min | V2-1 | ☐ |
| V2-7 | **`arm/modes/`**: state machine mimic / command / record / replay. **Dead-man rule:** hand lost → hold (no new goals). Fist → home, palm held → hold, thumbs-up → replay last recording. Mode switch only on a confirmed gesture. | Vyom (+ Claude) | 1.5 h | V2-2, V2-5 | ☐ |
| V2-8 | **Server + page**: a "Gesture" panel (camera preview, mode, gesture seen, target), start/stop gesture control. Gestures drive `set_target` at ≤ 30 Hz; the page's Disarm / Stop now still win. Record → saves a sequence into the demo pose store (reuses `arm/demo.py`). | Vyom (+ Claude) | 1.5 h | V2-7 | ☐ |
| V2-9 | **Fake-arm run**: hand drives the simulated arm on the page; log targets + timing to CSV; check the hand-lost hold and every refusal (out of reach, base clearance) on screen. | Vyom + Claude | 45 min | V2-8 | ☐ |

## Phase B: on the real arm (Sun, only after V1 passes)

| # | Task | Owner | Est. | Needs | Status |
|---|---|---|---|---|---|
| V2-10 | First real run: **low speed caps** (halve `speed_limits_deg_per_s`), kill switch in reach, start in command mode (fist → home) before mimic. | All | 1 h | V1 done, V2-9 | ☐ |
| V2-11 | Mimic pick of the 30 g block; tune mapping box and filter on the real arm. | Vyom | 1 h | V2-10 | ☐ |
| V2-12 | Record a pick in mimic, replay with thumbs-up. | Vyom | 30 min | V2-11 | ☐ |

## Phase C: measure and write up (after the Nov 29 demo)

| # | Task | Owner | Status |
|---|---|---|---|
| V2-13 | Hand-to-arm latency (phone slow-mo, median) | Vyom | ☐ |
| V2-14 | Jitter with vs without the filter (from V2-4's logs) | Vyom | ☐ |
| V2-15 | Mimic pick-and-place success rate over N tries | Vyom | ☐ |

## Known risks

- **MediaPipe on Python 3.14** (V2-0): if no wheel exists, everything V2 runs in a 3.12 venv. Check first.
- **Lag**: the ramp caps the big joints at 45 °/s, so fast hand moves will trail. That is the safe direction; widen speeds only after calibration.
- **Single camera, no true depth** (z from palm size): expect z to be the noisiest axis. Option if it is unusable: z on a key/scroll, x/y from the hand.
- **Lighting / background** change MediaPipe's confidence: test in the demo room.
