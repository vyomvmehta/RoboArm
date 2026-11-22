r"""V2-4: sweep EMA / One Euro parameters over the recorded clips; log raw vs filtered series.

    .venv\Scripts\python tools\filter_sweep.py            sweep -> runs/filter/sweep.csv + table
    .venv\Scripts\python tools\filter_sweep.py --log      raw + filtered series with the settings
                                                          in config/gestures.yaml -> runs/filter/logs/
The filter is fed EXACTLY what HandMapper feeds it: each clip goes through HandMapper with a
smooth= hook that records its input, so the units (mm), the hand-box clamp and the mirror are the
real ones.

Depth: V2-6 is not wired into the mapper yet (it uses fixed_reach_mm), so reach would be flat.
Until it is, palm size is turned into a STAND-IN distance, distance_cm = DEPTH_K / palm_px
(DEPTH_K = 10800: a 180 px palm ~ 60 cm), and passed to map(). Re-run this once V2-6's
calibrated fit exists: the depth (x) numbers here are only as good as that stand-in.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arm.config import load_arm  # noqa: E402
from arm.filtering import EMA, OneEuro, load_filter_config  # noqa: E402
from arm.filtering.metrics import score  # noqa: E402
from arm.mapping import HandMapper, load_mapping_config  # noqa: E402
from arm.vision.hands import load_csv  # noqa: E402

DEPTH_K = 10800.0
OUT = ROOT / "runs" / "filter"
GROUPS = {"image (y, z)": [1, 2], "depth (x)": [0]}   # tuple positions HandMapper passes
MIN_CUTOFFS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]
BETAS = [0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]
ALPHAS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]


def mapper_inputs(path: str):
    """t, visible, and the (x, y, z) mm HandMapper hands to its filter (NaN on lost frames)."""
    arm, mcfg = load_arm(), load_mapping_config()
    seen = []
    m = HandMapper(arm, mcfg, smooth=lambda t, xyz: seen.append(xyz) or xyz)
    frames = load_csv(path)
    t = np.array([f.t for f in frames])
    vis = np.array([f.visible for f in frames])
    raw = np.full((len(frames), 3), np.nan)
    for i, f in enumerate(frames):
        if not f.visible:
            continue
        n = len(seen)
        m.map(f, 0.5, distance_cm=DEPTH_K / f.palm_size())
        assert len(seen) == n + 1
        raw[i] = seen[-1]
    return t, vis, raw


def run(filt, t, vis, raw):
    out = np.full_like(raw, np.nan)
    for i in np.flatnonzero(vis):
        out[i] = filt(t[i], tuple(raw[i]))
    return out


def cfg_with(base: dict, cols, *, mc=None, beta=None, alpha=None) -> dict:
    c = {**base, "one_euro": {a: dict(v) for a, v in base["one_euro"].items()},
         "ema_alpha": dict(base["ema_alpha"])}
    for j in cols:
        a = "xyz"[j]
        if mc is not None:
            c["one_euro"][a] = {"min_cutoff_hz": mc, "beta": beta}
        if alpha is not None:
            c["ema_alpha"][a] = alpha
    return c


def sweep(base: dict, clips: dict):
    rows = []
    gap = base["reset_after_s"]
    data = list(clips.values())
    for gname, cols in GROUPS.items():
        raw_s = score([(t, v, r, r) for t, v, r in data], cols, gap)
        rows.append(dict(group=gname, kind="raw", param="-", **raw_s.__dict__))
        for al in ALPHAS:
            c = cfg_with(base, cols, alpha=al)
            s = score([(t, v, r, run(EMA(c), t, v, r)) for t, v, r in data], cols, gap)
            rows.append(dict(group=gname, kind="ema", param=f"alpha={al}", **s.__dict__))
        for mc in MIN_CUTOFFS:
            for b in BETAS:
                c = cfg_with(base, cols, mc=mc, beta=b)
                s = score([(t, v, r, run(OneEuro(c), t, v, r)) for t, v, r in data], cols, gap)
                rows.append(dict(group=gname, kind="one_euro", param=f"mc={mc} beta={b}",
                                 **s.__dict__))
        print(f"  {gname}: done", flush=True)
    return rows


def write_rows(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()})


def log(cfg: dict, clips: dict):
    """Per clip: t, visible, raw, EMA and One Euro output with the configured settings."""
    d = OUT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    for name, (t, vis, raw) in clips.items():
        e, o = run(EMA(cfg), t, vis, raw), run(OneEuro(cfg), t, vis, raw)
        p = d / f"{name}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "visible"] + [f"{k}_{a}" for k in ("raw", "ema", "oe") for a in "xyz"])
            for i in range(len(t)):
                vals = [] if not vis[i] else [f"{v:.3f}" for v in (*raw[i], *e[i], *o[i])]
                w.writerow([f"{t[i]:.4f}", int(vis[i])] + (vals or [""] * 9))
        print(f"  {p.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true", help="write raw/filtered logs, skip the sweep")
    ap.add_argument("--clips", default=str(ROOT / "runs" / "hands" / "*.csv"))
    args = ap.parse_args()
    cfg = load_filter_config()
    clips = {Path(p).stem: mapper_inputs(p) for p in sorted(glob.glob(args.clips))}
    print(f"{len(clips)} clips: {', '.join(clips)}")
    if args.log:
        log(cfg, clips)
        return
    rows = sweep(cfg, clips)
    write_rows(rows, OUT / "sweep.csv")
    print(f"wrote {OUT.relative_to(ROOT) / 'sweep.csv'} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
