"""V2-4: measure jitter and lag of a filter on a recorded clip (2026-11-21).

There is no ground truth, only raw = hand motion + tracking noise. The two are separated by WHERE
in the clip we look:

  jitter  in STILL chunks (0.5 s where a centred, non-causal smooth of the raw IMAGE position
          barely moves): RMS of the filter output around a straight-line fit through that chunk,
          in mm, plus the 95th percentile of its peak-to-peak (read it against modes.deadband_mm).
          The line takes out slow drift of a "still" hand, which no filter should remove.
          Stillness is judged on the image axes even for depth: judging depth by its own speed
          would throw out exactly the noisy chunks we want to measure.
  lag     in MOVING samples, split by speed (slow / fast): the time shift tau that best lines the
          filter output up with raw, i.e. argmin over tau of mean (filtered(t) - raw(t - tau))^2.
          Noise does not bias tau (it does not line up with any shift); motion does the work.
  rms     tracking error (filtered - raw) in those same moving samples, mm: what the arm sees.

Everything works per SEGMENT: a run of visible frames with no gap longer than the filter's
reset_after_s, so a lost hand never gets counted as motion.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CHUNK_S = 0.5              # still chunks are this long
STILL_MM_S = 20.0          # ...and the smoothed hand moves slower than this all through the chunk
SLOW_MM_S = (20.0, 100.0)  # moving samples in this speed band count as slow
FAST_MM_S = 200.0          # ...and at or above this as fast
MAX_LAG_S = 0.5
LAG_STEP_S = 0.002


def segments(t: np.ndarray, visible: np.ndarray, max_gap_s: float) -> list[np.ndarray]:
    """Index arrays of visible runs with no gap over max_gap_s (where the filter would reset)."""
    out, cur = [], []
    for i in np.flatnonzero(visible):
        if cur and t[i] - t[cur[-1]] > max_gap_s:
            out.append(np.array(cur))
            cur = []
        cur.append(i)
    if cur:
        out.append(np.array(cur))
    return [s for s in out if len(s) >= 5]


def _smooth(a: np.ndarray, n: int = 5) -> np.ndarray:
    """Centred moving average (edges padded): the non-causal reference for 'is it moving'."""
    pad = n // 2
    p = np.pad(a, ((pad, pad),) + ((0, 0),) * (a.ndim - 1), mode="edge")
    k = np.ones(n) / n
    return np.stack([np.convolve(p[:, j], k, mode="valid") for j in range(a.shape[1])], axis=1)


def speed(t: np.ndarray, raw: np.ndarray) -> np.ndarray:
    """Speed (units/s) of the smoothed raw signal, combined over the given columns."""
    ref = _smooth(raw)
    v = np.gradient(ref, t, axis=0)
    return np.linalg.norm(v, axis=1)


@dataclass
class Score:
    jitter: float          # mm RMS in still chunks
    p2p95: float           # mm, 95th percentile of peak-to-peak in a still chunk
    slow_lag_ms: float
    fast_lag_ms: float
    slow_rms: float        # mm
    fast_rms: float        # mm
    n_still: int           # still chunks used
    n_slow: int            # moving samples used
    n_fast: int


def _detrended(t, y):
    """Residuals of each column of y around its own straight-line fit."""
    A = np.stack([t - t.mean(), np.ones_like(t)], axis=1)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ coef


def _lag(segs_t, segs_raw, segs_f, segs_mask) -> tuple[float, float, int]:
    """Best shift (ms), RMS error at zero shift (mm), samples used."""
    n = sum(int(m.sum()) for m in segs_mask)
    if n < 10:
        return float("nan"), float("nan"), n
    taus = np.arange(0.0, MAX_LAG_S + 1e-9, LAG_STEP_S)
    err = np.zeros_like(taus)
    cnt = np.zeros_like(taus)
    sq0 = 0.0
    for t, raw, f, m in zip(segs_t, segs_raw, segs_f, segs_mask):
        sq0 += float(((f[m] - raw[m]) ** 2).sum())
        for k, tau in enumerate(taus):
            ok = m & (t - tau >= t[0])
            if not ok.any():
                continue
            shifted = np.stack([np.interp(t[ok] - tau, t, raw[:, j]) for j in range(raw.shape[1])], 1)
            err[k] += float(((f[ok] - shifted) ** 2).sum())
            cnt[k] += ok.sum() * raw.shape[1]
    mse = np.where(cnt > 0, err / np.maximum(cnt, 1), np.inf)
    return float(taus[int(np.argmin(mse))] * 1000), float(np.sqrt(sq0 / (n * segs_raw[0].shape[1]))), n


def score(clips: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
          cols: list[int], max_gap_s: float, still_cols: list[int] = (1, 2)) -> Score:
    """clips: (t, visible, raw (N,3), filtered (N,3)); cols: the axes this score is about;
    still_cols: the axes whose speed decides 'still' (default: HandMapper's image axes y, z)."""
    res = []
    st_t, st_raw, st_f, slow_m, fast_m = [], [], [], [], []
    for t, vis, raw, filt in clips:
        for s in segments(t, vis, max_gap_s):
            ts, rs, fs = t[s], raw[s][:, cols], filt[s][:, cols]
            sp = speed(ts, rs)
            sp_still = speed(ts, raw[s][:, list(still_cols)])
            per = max(5, int(round(CHUNK_S / np.median(np.diff(ts)))))
            for a in range(0, len(s) - per + 1, per):
                b = a + per
                if sp_still[a:b].max() < STILL_MM_S:
                    res.append(_detrended(ts[a:b], fs[a:b]))
            st_t.append(ts)
            st_raw.append(rs)
            st_f.append(fs)
            slow_m.append((sp >= SLOW_MM_S[0]) & (sp < SLOW_MM_S[1]))
            fast_m.append(sp >= FAST_MM_S)
    jit = float(np.sqrt(np.mean(np.concatenate(res) ** 2))) if res else float("nan")
    p2p = float(np.percentile([np.ptp(r, axis=0).max() for r in res], 95)) if res else float("nan")
    sl, sr, ns = _lag(st_t, st_raw, st_f, slow_m)
    fl, fr, nf = _lag(st_t, st_raw, st_f, fast_m)
    return Score(jit, p2p, sl, fl, sr, fr, len(res), ns, nf)
