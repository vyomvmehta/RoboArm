r"""V2-6 depth calibration: palm size -> hand distance, for ONE camera at ONE resolution.

Records your palm at taped distances, fits  distance_cm = a / palm_px + b  (pinhole camera: image
size ~ 1 / distance), checks it on held-out distances, and writes the coefficients into the
`depth:` block of config/gestures.yaml (camera name + capture resolution stored next to them).
Until this has run, gestures.yaml has `depth: null` and the arm's reach stays at
mapping.fixed_reach_mm.

RUN IT ON THE DEMO CAMERA, AS THE PERSON WHO WILL DRIVE THE DEMO. The fit is only valid for that
camera, that capture size and that hand (a bigger palm reads as "closer"). At run time a different
resolution prints a loud MISMATCH warning: recalibrate rather than ignore it.

QUICK START
    .venv\Scripts\python tools\depth_calibrate.py --who vyom
    .venv\Scripts\python tools\depth_calibrate.py --who vyom --camera 1 --camera-name "Logitech C920"
    .venv\Scripts\python tools\depth_calibrate.py --refit runs\depth\vyom-20261122-101500   (redo the fit, no camera)

1. CAMERA SETUP
   - Put the camera exactly where it will be for the demo and don't touch it afterwards (a laptop
     camera moves with the lid: set the lid angle once). Lens roughly at palm height, pointing
     straight along the line of tape marks, hand near the CENTRE of the image at every mark.
   - Lighting: even, from the front or overhead. Avoid a window / lamp behind you (dark hand,
     jumpy landmarks), strong side light (shadows on the knuckles), light that changes mid-session.
   - Close anything else using the camera (Camera app, Teams, tools/hand_view.py).

2. 1280x720 CHECK (automatic)
   The tool asks the camera for --width x --height (default 1280x720, what follow mode uses) and
   STOPS if it delivers anything else. Fix the camera (or pass the size it really gives with
   --width/--height, and make follow mode capture at that same size).

3. DISTANCES (tape on the desk, measured from the LENS GLASS to your palm surface)
   Fit:      30 35 42 52 65 90 cm   (default --fit)
   Held out: 47 75 cm               (default --holdout): recorded, NEVER used in the fit, only to
                                     check its predictions -> that error is the tolerance to quote.
   The mapping uses mapping.depth_cm: [40, 80]; the fit deliberately goes a bit past both ends
   so the edges of the work box are interpolated, not extrapolated. Points are spaced evenly in
   1/distance (where the model is a straight line), so they bunch up near the camera.

4. HAND POSE at every mark: palm flat and facing the camera, fingers together pointing up, the
   same pose as in follow mode. Don't tilt or turn the hand (foreshortening shrinks the palm and
   reads as further away), don't curl it, keep the wrist in view.

5. EACH CAPTURE: hold the palm over the mark, press SPACE (1 s to settle, then a 3 s clip). The
   window then shows the median palm size and how steady it was:
   SPACE/Enter keeps it, r redoes it (do redo when it says UNSTEADY), q quits.

6. RESULT: the console prints the residuals of the inverse, linear and inverse-square fits and of
   every palm measure, plus the held-out errors. The chosen fit (default inverse, palm_triangle)
   is written into the `depth:` block of config/gestures.yaml; only that block changes. The clips
   are kept in runs/depth/<who>-<time>/ so --refit can redo the maths later.
   Commit config/gestures.yaml AND that runs/depth/ folder together.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arm.vision.depth import MEASURES, MODELS, fit, palm_px, predict, write_depth_section  # noqa: E402
from arm.vision.hands import load_csv, save_csv  # noqa: E402

OUT = ROOT / "runs" / "depth"
FIT_CM = [30, 35, 42, 52, 65, 90]
HOLDOUT_CM = [47, 75]
MAX_SPREAD = 0.05          # a clip whose palm size varies more than 5% (std / median) gets a "redo?" hint
MIN_VISIBLE = 0.8
BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
         (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


# ------------------------------------------------------------------ camera name
def detect_camera_names() -> list[str]:
    """Windows camera device names (PowerShell). Empty list if it can't tell."""
    if sys.platform != "win32":
        return []
    cmd = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in 'Camera','Image' } "
           "| ForEach-Object { $_.Name }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                             text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def pick_camera_name(given: str | None) -> str:
    if given:
        return given
    names = detect_camera_names()
    if len(names) == 1:
        print(f"camera name: {names[0]} (detected; pass --camera-name to override)")
        return names[0]
    found = "\n  ".join(names) if names else "(none detected)"
    sys.exit(f"Can't tell which camera this is. Cameras found:\n  {found}\n"
             f"Rerun with --camera-name \"<name>\": it is stored next to the coefficients.")


# ------------------------------------------------------------------ recording
def clip_stats(frames, measure: str) -> dict:
    vis = [f for f in frames if f.visible]
    s = np.array([palm_px(f.landmarks, measure) for f in vis])
    return {"n": len(frames), "visible": len(vis) / max(len(frames), 1),
            "median": float(np.median(s)) if len(s) else 0.0,
            "spread": float(s.std() / np.median(s)) if len(s) > 1 else 1.0}


def record_session(args) -> Path:
    import cv2
    from arm.vision.hands import Camera, HandTracker

    name = pick_camera_name(args.camera_name)
    session = OUT / f"{args.who}-{time.strftime('%Y%m%d-%H%M%S')}"
    session.mkdir(parents=True, exist_ok=True)
    cam, tracker = Camera(args.camera, args.width, args.height), HandTracker()
    first = cam.read()
    h, w = first.shape[:2]
    if (w, h) != (args.width, args.height):
        cam.close()
        tracker.close()
        session.rmdir()
        sys.exit(f"STOP: asked camera {args.camera} for {args.width}x{args.height}, it delivers {w}x{h}.\n"
                 f"The fit is only valid at the size follow mode captures at. Fix the camera, or rerun\n"
                 f"with --width {w} --height {h} AND make follow mode capture at {w}x{h} too.")
    print(f"camera {args.camera} '{name}': {w}x{h} OK")
    meta = {"who": args.who, "camera_index": args.camera, "camera_name": name,
            "width": w, "height": h, "fit_cm": args.fit, "holdout_cm": args.holdout,
            "date": time.strftime("%Y-%m-%d %H:%M"), "seconds": args.seconds}
    (session / "session.yaml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")

    todo = sorted([(z, "fit") for z in args.fit] + [(z, "HELD OUT") for z in args.holdout])
    t0 = time.perf_counter()
    win = "Depth calibration (q quits)"

    def show(frame, fr, lines, red=False):
        view = cv2.flip(frame, 1)
        if fr is not None and fr.visible:
            pts = [(int(w - x), int(y)) for x, y, _ in fr.landmarks]
            for a, b in BONES:
                cv2.line(view, pts[a], pts[b], (80, 200, 120), 2)
        for i, s in enumerate(lines):
            cv2.putText(view, s, (12, 34 + 32 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                        (0, 0, 255) if red and i == 0 else (255, 255, 255), 2)
        cv2.imshow(win, view)
        return cv2.waitKey(1) & 0xFF

    try:
        k = 0
        while k < len(todo):
            z, kind = todo[k]
            label = f"[{k + 1}/{len(todo)}] palm at {z} cm ({kind})"
            # aim: live palm size, wait for SPACE
            while True:
                frame = cam.read()
                fr = tracker.process(frame, time.perf_counter() - t0)
                px = f"palm {palm_px(fr.landmarks, args.measure):.0f} px" if fr.visible else "hand LOST"
                key = show(frame, fr, [label, px, "palm flat, facing camera. SPACE = record"])
                if key in (ord("q"), 27):
                    return session
                if key == ord(" "):
                    break
            # settle 1 s, then record
            t_start = time.perf_counter()
            clip = []
            while True:
                frame = cam.read()
                now = time.perf_counter()
                fr = tracker.process(frame, now - t0)
                if now - t_start < 1.0:
                    show(frame, fr, [label, "hold still..."])
                    continue
                clip.append(fr)
                show(frame, fr, [f"REC {z} cm  {len(clip)} frames"], red=True)
                if now - t_start >= 1.0 + args.seconds:
                    break
            st = clip_stats(clip, args.measure)
            ok = st["visible"] >= MIN_VISIBLE and st["spread"] <= MAX_SPREAD
            verdict = "looks good" if ok else "UNSTEADY or hand lost: redo?"
            summary = (f"{z} cm: {st['median']:.1f} px, spread {100 * st['spread']:.1f}%, "
                       f"seen {100 * st['visible']:.0f}%")
            print(summary + ("" if ok else "   <- " + verdict))
            while True:
                frame = cam.read()
                key = show(frame, None, [summary, verdict, "SPACE/Enter = keep   r = redo   q = quit"],
                           red=not ok)
                if key in (ord(" "), 13):
                    save_csv(clip, session / f"{z}cm.csv")
                    k += 1
                    break
                if key == ord("r"):
                    break
                if key in (ord("q"), 27):
                    return session
    finally:
        cam.close()
        tracker.close()
        cv2.destroyAllWindows()
    return session


# ------------------------------------------------------------------ fitting
def load_session(session: Path) -> tuple[dict, dict[float, list]]:
    meta = yaml.safe_load((session / "session.yaml").read_text(encoding="utf-8"))
    clips = {}
    for p in sorted(session.glob("*cm.csv")):
        clips[float(p.stem[:-2])] = load_csv(p)
    return meta, clips


def medians(clips: dict, measure: str) -> dict[float, float]:
    out = {}
    for z, frames in clips.items():
        st = clip_stats(frames, measure)
        if st["visible"] * st["n"] < 10:
            print(f"  skipping {z:g} cm: hand seen in only {st['visible'] * st['n']:.0f} frames")
            continue
        out[z] = st["median"]
    return out


def evaluate(med: dict, fit_cm: list, holdout_cm: list, model: str) -> dict:
    zf = [z for z in fit_cm if z in med]
    zh = [z for z in holdout_cm if z in med]
    a, b, res = fit([med[z] for z in zf], zf, model)
    hold = {z: float(predict(model, a, b, med[z]) - z) for z in zh}     # predicted - true
    return {"a": a, "b": b, "res": dict(zip(zf, res.tolist())), "hold": hold,
            "rms": float(np.sqrt(np.mean(res ** 2))), "max": float(np.max(np.abs(res))),
            "hold_max": max((abs(e) for e in hold.values()), default=float("nan"))}


def report_and_write(session: Path, args) -> dict:
    meta, clips = load_session(session)
    fit_cm = [float(z) for z in meta["fit_cm"]]
    hold_cm = [float(z) for z in meta["holdout_cm"]]
    res_set = {(f.width, f.height) for c in clips.values() for f in c if f.width}
    if len(res_set) != 1:
        sys.exit(f"clips were recorded at different resolutions {res_set}: can't fit them together")
    w, h = res_set.pop()

    med = medians(clips, args.measure)
    print(f"\nSession {session.name}: {meta['who']}, '{meta['camera_name']}', {w}x{h}, measure {args.measure}")
    print(f"{'Z cm':>6} {'role':>9} {'palm px':>8} {'spread':>7} {'Z*px':>8}")
    for z in sorted(med):
        st = clip_stats(clips[z], args.measure)
        role = "HELD OUT" if z in hold_cm else "fit"
        # Z*px should be ~constant if Z = a/s (b small): a quick eyeball check of the physics
        print(f"{z:6g} {role:>9} {med[z]:8.1f} {100 * st['spread']:6.1f}% {z * med[z]:8.0f}")
    if len([z for z in fit_cm if z in med]) < 3:
        sys.exit("need at least 3 fit distances with a visible hand")

    print("\nModels (residual = measured - fitted; held-out error = predicted - true), cm:")
    results = {}
    for model in MODELS:
        r = results[model] = evaluate(med, fit_cm, hold_cm, model)
        hold = "  ".join(f"{z:g}cm {e:+.1f}" for z, e in r["hold"].items())
        print(f"  {model:15s} a={r['a']:11.4g} b={r['b']:+7.2f}   fit RMS {r['rms']:5.2f}  "
              f"max {r['max']:5.2f}   held out: {hold}")
        print("  " + " " * 15 + "residuals: " + "  ".join(f"{z:g}:{e:+.1f}" for z, e in r["res"].items()))

    print("\nPalm measures with the inverse model (lower = better):")
    for m in MEASURES:
        r = evaluate(medians(clips, m), fit_cm, hold_cm, "inverse")
        print(f"  {m:15s} fit RMS {r['rms']:5.2f}   worst held-out {r['hold_max']:5.2f}")

    chosen = results[args.model]
    cfg = {
        "model": args.model, "a": round(chosen["a"], 4), "b": round(chosen["b"], 3),
        "measure": args.measure,
        "camera_name": meta["camera_name"], "camera_index": meta["camera_index"],
        "width": w, "height": h,
        "who": meta["who"], "date": meta["date"], "session": (session.relative_to(ROOT) if session.is_relative_to(ROOT) else session).as_posix(),
        "fit_range_cm": [min(chosen["res"]), max(chosen["res"])],
        "fit_distances_cm": sorted(chosen["res"]),
        "fit_rms_cm": round(chosen["rms"], 2),
        "fit_max_residual_cm": round(chosen["max"], 2),
        "holdout_error_cm": {float(z): round(e, 2) for z, e in chosen["hold"].items()},
    }
    if args.no_write:
        print("\n--no-write: gestures.yaml left alone")
    else:
        notes = (f"Pose: palm flat facing the camera, distance from the lens front. {meta['who']}'s hand:\n"
                 f"another person's palm size shifts every Z by the same %. Recalibrate for them.")
        write_depth_section(cfg, args.config, notes)
        print(f"\nwrote depth: ({args.model}, {args.measure}) -> {args.config}")
    return cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--who", help="whose hand (stored: the fit is per person)")
    ap.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default 0)")
    ap.add_argument("--camera-name", help="stored next to the coefficients (auto-detected if only one)")
    ap.add_argument("--width", type=int, default=1280, help="capture width; must match follow mode (default 1280)")
    ap.add_argument("--height", type=int, default=720, help="capture height; must match follow mode (default 720)")
    ap.add_argument("--fit", type=float, nargs="+", default=FIT_CM, metavar="CM",
                    help="distances used in the fit (default 30 35 42 52 65 90)")
    ap.add_argument("--holdout", type=float, nargs="+", default=HOLDOUT_CM, metavar="CM",
                    help="held-out distances, never fitted, only checked (default 47 75)")
    ap.add_argument("--seconds", type=float, default=3.0, help="clip length per distance (default 3)")
    ap.add_argument("--measure", default="palm_triangle", choices=sorted(MEASURES),
                    help="palm-size measure (default palm_triangle: steadiest under tilt)")
    ap.add_argument("--model", default="inverse", choices=sorted(MODELS),
                    help="model written to the yaml (default inverse: the pinhole one)")
    ap.add_argument("--refit", type=Path, help="fit an existing runs/depth/<session> (no camera)")
    ap.add_argument("--no-write", action="store_true", help="print the fit, leave gestures.yaml alone")
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "gestures.yaml",
                    help="yaml to write the depth: block into (default config/gestures.yaml)")
    args = ap.parse_args()
    if set(args.fit) & set(args.holdout):
        ap.error("a held-out distance can't also be a fit distance")

    if args.refit:
        session = args.refit if args.refit.is_absolute() else (Path.cwd() / args.refit)
    else:
        if not args.who:
            ap.error("--who is required when recording")
        session = record_session(args)
    report_and_write(session.resolve(), args)


if __name__ == "__main__":
    main()
