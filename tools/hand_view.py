r"""Live hand viewer + clip recorder (V2-1 / V2-3).

    .venv\\Scripts\\python tools\\hand_view.py            (camera 0)
    .venv\\Scripts\\python tools\\hand_view.py --camera 1

Window shows the 21 landmarks, the gesture each frame is classified as, the CONFIRMED gesture
(after hold-to-confirm), the pinch fraction, palm size and FPS.

Keys:  r = start / stop recording a clip (asks nothing: named by time, saved in runs/hands/)
       1-6 = start recording a NAMED clip for V2-3:
             1 pinch   2 fist   3 palm   4 thumbs_up   5 sweep   6 lost (hand leaving the frame)
       q / Esc = quit
Nothing is saved except the landmark CSVs (no images).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm.config import load_arm  # noqa: E402
from arm.gestures import Confirmer, classify, load_gesture_config, pinch_fraction  # noqa: E402
from arm.mapping import HandMapper  # noqa: E402
from arm.vision.hands import Camera, HandTracker, save_csv  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "runs" / "hands"
NAMED = {ord("1"): "pinch", ord("2"): "fist", ord("3"): "palm", ord("4"): "thumbs_up",
         ord("5"): "sweep", ord("6"): "lost"}
BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
         (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    args = ap.parse_args()

    cfg = load_gesture_config()
    cam, tracker = Camera(args.camera), HandTracker()
    conf = Confirmer(cfg.hold_to_confirm_s, cfg.min_visible_fraction)
    mapper = HandMapper(load_arm())      # V2-5: where the gripper would go (nothing is sent)
    t0 = time.perf_counter()
    rec, rec_name, last_fired, fired_at = None, "", "", 0.0
    fps, last = 0.0, t0
    try:
        while True:
            frame = cam.read()
            now = time.perf_counter()
            fr = tracker.process(frame, now - t0)
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6)
            last = now
            label = classify(fr.landmarks, cfg) if fr.visible else None
            fired = conf.update(label, fr.t)
            if fired:
                last_fired, fired_at = fired, now
            if rec is not None:
                rec.append(fr)

            view = cv2.flip(frame, 1)                       # mirror, so moving right looks right
            w = view.shape[1]
            if fr.visible:
                pts = [(int(w - x), int(y)) for x, y, _ in fr.landmarks]
                for a, b in BONES:
                    cv2.line(view, pts[a], pts[b], (80, 200, 120), 2)
                for p in pts:
                    cv2.circle(view, p, 4, (255, 255, 255), -1)
            lines = [
                f"{fps:4.1f} fps   hand: {'yes' if fr.visible else 'LOST'}",
                f"frame: {label or '-'}",
                f"CONFIRMED: {last_fired}" if now - fired_at < 1.5 else "CONFIRMED: -",
            ]
            if fr.visible:
                pinch = pinch_fraction(fr.landmarks, cfg)
                lines += [f"pinch {pinch:.2f}   palm {fr.palm_size():.0f} px"]
                t = mapper.map(fr, pinch)
                lines += [f"target x{t.x:.0f} y{t.y:+.0f} z{t.z:.0f} grip {t.gripper_mm:.0f} mm"
                          + ("  (edge)" if t.clamped else "")]
                if t.refused:
                    lines += [f"REFUSED: {t.refused[:60]}"]
                # the hand box: only this part of the image counts
                u0, u1, v0, v1 = mapper.cfg["hand_box"]
                hh, ww = view.shape[:2]
                cv2.rectangle(view, (int(ww * u0), int(hh * v0)), (int(ww * u1), int(hh * v1)), (200, 160, 60), 1)
            if rec is not None:
                lines += [f"REC {rec_name}  {len(rec)} frames  (r to stop)"]
            for i, s in enumerate(lines):
                cv2.putText(view, s, (12, 30 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 0, 255) if s.startswith(("REC", "REFUSED")) else (255, 255, 255), 2)
            cv2.imshow("RoboArm hand view (q quits)", view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("r") or key in NAMED:
                if rec is None:
                    rec = []
                    rec_name = NAMED.get(key, "clip")
                else:
                    path = OUT / f"{rec_name}-{time.strftime('%Y%m%d-%H%M%S')}.csv"
                    save_csv([f for f in rec], path)
                    print(f"saved {len(rec)} frames -> {path}")
                    rec = None
    finally:
        if rec:
            save_csv(rec, OUT / f"{rec_name}-{time.strftime('%Y%m%d-%H%M%S')}.csv")
        cam.close()
        tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
