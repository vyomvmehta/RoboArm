r"""V2-14: jitter with vs without the filter, from the logs tools/filter_sweep.py --log wrote.

    .venv\Scripts\python tools\filter_eval.py

Reads runs/filter/logs/*.csv only (no camera, no filter code). Prints the numbers that go in
docs/V2_FILTER_RESULTS.md and writes runs/filter/filter_eval.png.

Columns in the logs are HandMapper's TUPLE positions, not image axes:
    x = reach (from palm size, stand-in depth), y = left/right, z = height.

jitter  std of frame-to-frame deltas inside STILL chunks: 0.5 s chunks where a centred 5-frame
        mean of the raw image position (y, z) moves < 20 mm/s the whole way (the same rule as
        arm/filtering/metrics.py). Deltas are taken inside a chunk, never across chunks.
lag     peak of the cross-correlation between the raw and the filtered position, per axis, on the
        sweep clip. Each gap-free segment (gap <= reset_after_s) is resampled to a 5 ms grid,
        mean-removed, cross-correlated; the segments' correlations are summed; the peak is
        refined with a parabola through its 3 neighbours.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arm.filtering import load_filter_config  # noqa: E402
from arm.filtering import metrics as M  # noqa: E402

LOGS = ROOT / "runs" / "filter" / "logs"
OUT = ROOT / "runs" / "filter" / "filter_eval.png"
GAP = load_filter_config()["reset_after_s"]
AXES = {"reach (palm size)": 0, "left/right": 1, "height": 2}     # log column index
SRC = ("raw", "ema", "oe")
GRID = 0.005
MAX_LAG = 0.5


def load(path):
    a = np.genfromtxt(path, delimiter=",", skip_header=1)
    return a[:, 0], a[:, 1] > 0, {"raw": a[:, 2:5], "ema": a[:, 5:8], "oe": a[:, 8:11]}


def clips():
    return {os.path.basename(p).split("-")[0]: load(p) for p in sorted(glob.glob(str(LOGS / "*.csv")))}


def still_chunks(t, vis, sig, still_mm_s=20.0):
    """[(clip-local index array)] of still 0.5 s chunks, judged on the raw image axes."""
    out = []
    for s in M.segments(t, vis, GAP):
        ts = t[s]
        sp = M.speed(ts, sig["raw"][s][:, [1, 2]])
        per = max(5, int(round(M.CHUNK_S / np.median(np.diff(ts)))))
        for a in range(0, len(s) - per + 1, per):
            if sp[a:a + per].max() < still_mm_s:
                out.append(s[a:a + per])
    return out


def jitter(data, still_mm_s=20.0):
    """{clip: {axis: {src: deltas}}} pooled later; also chunk and frame counts per clip."""
    res, counts = {}, {}
    for name, (t, vis, sig) in data.items():
        ch = still_chunks(t, vis, sig, still_mm_s)
        counts[name] = (len(ch), sum(len(c) for c in ch))
        for ax, j in AXES.items():
            for src in SRC:
                d = [np.diff(sig[src][c][:, j]) for c in ch]
                res.setdefault(ax, {}).setdefault(src, []).extend(d)
    pooled = {ax: {src: (np.concatenate(v) if v else np.array([])) for src, v in d.items()}
              for ax, d in res.items()}
    return pooled, counts


def xcorr_lag(t, vis, a, b, lo=None, hi=None):
    """Lag (ms, b behind a is positive) from the summed cross-correlation of a and b."""
    n = int(MAX_LAG / GRID)
    acc, used = np.zeros(2 * n + 1), 0
    for s in M.segments(t, vis, GAP):
        ts = t[s]
        if lo is not None:
            keep = (ts >= lo) & (ts < hi)
            s, ts = s[keep], ts[keep]
            if len(s) < 10 or np.diff(ts).max() > GAP:
                continue
        g = np.arange(ts[0], ts[-1], GRID)
        if len(g) < 2 * n:
            continue
        x = np.interp(g, ts, a[s]); y = np.interp(g, ts, b[s])
        x -= x.mean(); y -= y.mean()
        full = np.correlate(y, x, mode="full")            # index len-1 is lag 0
        mid = len(x) - 1
        acc += full[mid - n: mid + n + 1] / (np.std(x) * np.std(y))     # length-weighted sum
        used += len(s)
    if not used:
        return float("nan"), 0
    k = int(np.argmax(acc))
    if 0 < k < 2 * n:                                     # parabolic refinement
        y0, y1, y2 = acc[k - 1], acc[k], acc[k + 1]
        den = y0 - 2 * y1 + y2
        k = k + (0.5 * (y0 - y2) / den if den else 0.0)
    return (k - n) * GRID * 1000, used


def main():
    data = clips()
    still, counts = jitter(data)
    print("still chunks (20 mm/s, 0.5 s) per clip: chunks / frames")
    for k, (c, f) in counts.items():
        print(f"  {k:10s} {c:3d} {f:5d}")
    print(f"  total      {sum(c for c, _ in counts.values()):3d} {sum(f for _, f in counts.values()):5d}")
    print("\njitter: std of frame-to-frame deltas in still chunks (mm), pooled")
    for ax in AXES:
        r = still[ax]
        row = {s: float(np.std(r[s])) for s in SRC}
        print(f"  {ax:18s} n_deltas={len(r['raw']):4d} raw={row['raw']:.3f} ema={row['ema']:.3f} "
              f"oe={row['oe']:.3f} oe/raw={row['oe'] / row['raw']:.2f}")
    t, vis, sig = data["sweep"]
    print("\nlag on the sweep clip (cross-correlation, ms)")
    for ax, j in AXES.items():
        row = {}
        for s in ("ema", "oe"):
            row[s] = xcorr_lag(t, vis, sig["raw"][:, j], sig[s][:, j])
        print(f"  {ax:18s} samples={row['oe'][1]} ema={row['ema'][0]:.1f} oe={row['oe'][0]:.1f}")
    print("\nlag split on the sweep clip (oe, ms): window = clip time since first frame")
    t0 = t[0]
    for name, lo, hi in (("slow 1-17 s", 1.0, 17.0), ("fast 19-23.5 s", 19.0, 23.5),
                         ("first half", 0.0, 11.9), ("second half", 11.9, 24.0)):
        cells = []
        for ax, j in AXES.items():
            lag, n = xcorr_lag(t, vis, sig["raw"][:, j], sig["oe"][:, j], t0 + lo, t0 + hi)
            cells.append(f"{ax} {lag:6.1f} (n={n})")
        print(f"  {name:15s} " + "  ".join(cells))
    print("\nper gap-free segment (oe, ms):")
    for s_ in M.segments(t, vis, GAP):
        row = []
        for ax, j in AXES.items():
            lag, n = xcorr_lag(t, vis, sig["raw"][:, j], sig["oe"][:, j], t[s_[0]], t[s_[-1]] + 1e-6)
            row.append(f"{lag:6.1f}")
        print(f"  {t[s_[0]] - t0:5.1f}-{t[s_[-1]] - t0:5.1f}s n={len(s_):3d}  " + "  ".join(row))
    print("\nsensitivity: still threshold 40 mm/s")
    st2, c2 = jitter(data, 40.0)
    print("  chunks/frames:", {k: v for k, v in c2.items()})
    for ax in AXES:
        r = st2[ax]
        print(f"  {ax:18s} n={len(r['raw'])} raw={np.std(r['raw']):.3f} oe={np.std(r['oe']):.3f}")
    plot(data, still)


def plot(data, still):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.3]})
    names = list(AXES)
    x = np.arange(len(names))
    for i, (src, col) in enumerate((("raw", "#888"), ("oe", "#1f77b4"))):
        v = [float(np.std(still[n][src])) for n in names]
        a.bar(x + (i - 0.5) * 0.36, v, 0.36, label={"raw": "raw", "oe": "One Euro"}[src], color=col)
    a.set_xticks(x, names)
    a.set_ylabel("std of frame-to-frame delta (mm)")
    a.set_title("Jitter, still chunks")
    a.legend(frameon=False)
    t, vis, sig = data["sweep"]
    lo, hi = 19.0, 21.0                                    # fast left/right strokes
    m = vis & (t - t[0] >= lo) & (t - t[0] < hi)
    a2 = t[m] - t[0]
    b.plot(a2, sig["raw"][m][:, 1], color="#888", lw=1.2, label="raw")
    b.plot(a2, sig["oe"][m][:, 1], color="#1f77b4", lw=1.6, label="One Euro")
    b.plot(a2, sig["ema"][m][:, 1], color="#d62728", lw=1.0, ls="--", label="EMA (baseline)")
    b.set_xlabel("sweep clip time (s)")
    b.set_ylabel("left/right target y (mm)")
    b.set_title("Lag, fast strokes (sweep clip, 19-21 s)")
    b.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT, dpi=130)
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
