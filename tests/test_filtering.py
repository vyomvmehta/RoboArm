"""V2-4 filter: the contract, the lost-hand path, and jitter-vs-lag on synthetic + real clips (Nov 21)."""
import copy
import glob
import math

import numpy as np
import pytest
import yaml

from arm.config import load_arm
from arm.filtering import EMA, OneEuro, load_filter_config, smoothing_factor
from arm.filtering.metrics import score
from arm.mapping import HandMapper, load_mapping_config
from arm.vision.hands import load_csv

CFG = load_filter_config()
DT = 1 / 30


def cfg(**axes):
    """CFG with every axis (or the named ones) set to the given One Euro settings / EMA alpha."""
    c = copy.deepcopy(CFG)
    for a in "xyz":
        if "mc" in axes:
            c["one_euro"][a] = {"min_cutoff_hz": axes["mc"], "beta": axes.get("beta", 0.0)}
        if "alpha" in axes:
            c["ema_alpha"][a] = axes["alpha"]
    return c


def feed(f, t, xs):
    """Feed a 1-D signal on all three axes; return the x output."""
    return np.array([f(ti, (v, v, v))[0] for ti, v in zip(t, xs)])


def clip(name):
    return load_csv(sorted(glob.glob(f"runs/hands/{name}-*.csv"))[0])


# ------------------------------------------------------------------ contract
def test_contract_returns_three_floats_and_passes_first_frame_through():
    f = OneEuro(CFG)
    out = f(0.0, (175.0, -20.0, 60.0))
    assert out == (175.0, -20.0, 60.0)
    x, y, z = f(DT, (176.0, -19.0, 61.0))
    assert all(isinstance(v, float) for v in (x, y, z))


def test_constant_input_gives_constant_output():
    f = OneEuro(CFG)
    for i in range(60):
        assert f(i * DT, (170.0, 10.0, 50.0)) == pytest.approx((170.0, 10.0, 50.0))


def test_axes_are_independent_and_depth_is_smoothed_harder():
    """The step goes into all three axes; x (reach, from palm size) must follow it slowest."""
    f = OneEuro(CFG)
    f(0.0, (0.0, 0.0, 0.0))
    x, y, z = f(DT, (10.0, 10.0, 10.0))
    assert y == pytest.approx(z) and x < y


def test_config_validation():
    bad = copy.deepcopy(CFG)
    bad["one_euro"]["y"]["min_cutoff_hz"] = 0
    with pytest.raises(ValueError):
        OneEuro(bad)
    bad = cfg(alpha=1.5)
    with pytest.raises(ValueError):
        EMA(bad)


def test_smoothing_factor_limits():
    assert smoothing_factor(1.0, DT) == pytest.approx(1 / (1 + 1 / (2 * math.pi) / DT))
    assert smoothing_factor(1e6, DT) > 0.999        # huge cutoff: passes straight through
    assert smoothing_factor(1e-6, DT) < 1e-6        # tiny cutoff: barely moves


def test_ema_alpha_one_is_a_pass_through():
    f = EMA(cfg(alpha=1.0))
    xs = np.random.default_rng(0).normal(size=50)
    np.testing.assert_allclose(feed(f, np.arange(50) * DT, xs), xs)


# ------------------------------------------------------------------ timing and the lost hand
def test_repeated_timestamp_keeps_the_last_output():
    f = OneEuro(CFG)
    f(0.0, (0.0, 0.0, 0.0))
    a = f(DT, (5.0, 5.0, 5.0))
    assert f(DT, (99.0, 99.0, 99.0)) == a            # dt = 0: no divide by zero, no jump
    assert f(DT / 2, (99.0, 99.0, 99.0)) == a        # out of order: ignored too


def test_short_flicker_keeps_filtering_long_loss_resets():
    gap = CFG["reset_after_s"]
    f = OneEuro(CFG)
    f(0.0, (100.0, 0.0, 0.0))
    x, y, _ = f(gap * 0.5, (150.0, 50.0, 0.0))       # brief dropout: still smoothing
    assert x < 150.0 and y < 50.0 and f.resets == 0
    out = f(gap * 0.5 + gap * 1.5, (150.0, 50.0, 0.0))   # long loss: stale state dropped
    assert out == (150.0, 50.0, 0.0) and f.resets == 1


def test_lost_clip_through_handmapper():
    """Real 'lost' clip (hand leaves 9 times): no crash, no NaN, a reset after every real loss."""
    f = OneEuro(CFG)
    m = HandMapper(load_arm(), load_mapping_config(), smooth=f)
    frames = clip("lost")
    out = [m.map(fr, 0.5) for fr in frames]
    assert sum(o is None for o in out) == sum(not fr.visible for fr in frames)
    assert all(math.isfinite(v) for o in out if o for v in (o.x, o.y, o.z))
    t = np.array([fr.t for fr in frames if fr.visible])
    assert f.resets == int((np.diff(t) > CFG["reset_after_s"]).sum()) > 0


# ------------------------------------------------------------------ jitter vs lag, synthetic
def synthetic(seed=1, noise=0.5):
    """Still, a slow 75 mm/s ramp, still, two fast 300 mm/s ramps with stops between; + white noise."""
    t = np.arange(0, 8, DT)
    v = np.interp(t, [0, 2, 4, 5, 5.5, 6.5, 7, 8], [0, 0, 150, 150, 0, 0, 150, 150])
    return t, v, v + np.random.default_rng(seed).normal(0, noise, len(t))


FAST = lambda t: ((t > 5.0) & (t < 5.5)) | ((t > 6.5) & (t < 7.0))   # noqa: E731
STILL = lambda t: (t > 0.5) & (t < 2.0)                             # noqa: E731


def lag_ms(t, truth, out, mask):
    taus = np.arange(0, 0.5, 0.001)
    err = [np.mean((out[mask] - np.interp(t[mask] - tau, t, truth)) ** 2) for tau in taus]
    return taus[int(np.argmin(err))] * 1000


def test_one_euro_beats_ema_at_equal_stillness():
    """The point of One Euro: at the SAME jitter at rest, far less lag in a fast move."""
    t, truth, noisy = synthetic()
    ema = feed(EMA(cfg(alpha=0.1)), t, noisy)
    ema_jit = np.std(ema[STILL(t)])
    # the least-smoothing One Euro (beta 0.05) that is at least as still as that EMA
    for mc in (2.0, 1.5, 1.0, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05):
        oe = feed(OneEuro(cfg(mc=mc, beta=0.05)), t, noisy)
        if np.std(oe[STILL(t)]) <= ema_jit:
            break
    else:
        pytest.fail("no One Euro setting as still as EMA alpha=0.1")
    assert lag_ms(t, truth, oe, FAST(t)) < 0.5 * lag_ms(t, truth, ema, FAST(t))


def test_beta_zero_is_a_fixed_low_pass_with_lag_tau():
    """beta = 0: a plain low-pass. On a long ramp its lag settles at tau = 1 / (2 pi fc)."""
    t = np.arange(0, 4, DT)
    truth = 100 * t
    out = feed(OneEuro(cfg(mc=1.0, beta=0.0)), t, truth)
    steady = t > 2.0                                  # > 10 tau in: transient gone
    assert lag_ms(t, truth, out, steady) == pytest.approx(1000 / (2 * math.pi), rel=0.05)


def test_beta_cuts_fast_lag():
    t, truth, noisy = synthetic()
    l0 = lag_ms(t, truth, feed(OneEuro(cfg(mc=1.0, beta=0.0)), t, noisy), FAST(t))
    l1 = lag_ms(t, truth, feed(OneEuro(cfg(mc=1.0, beta=0.05)), t, noisy), FAST(t))
    assert l1 < l0 / 3


def test_lag_estimator_recovers_a_known_delay():
    """metrics.score must find a pure 80 ms delay, without ground truth, from noisy raw."""
    t, truth, noisy = synthetic(noise=0.3)
    delayed = np.interp(t - 0.080, t, truth)
    raw = np.stack([noisy] * 3, 1)
    filt = np.stack([delayed] * 3, 1)
    s = score([(t, np.ones(len(t), bool), raw, filt)], [1, 2], 0.2)
    assert s.fast_lag_ms == pytest.approx(80, abs=6)
    assert s.slow_lag_ms == pytest.approx(80, abs=6)
    assert s.n_still >= 4


# ------------------------------------------------------------------ jitter vs lag, real clips
def mapper_series(name):
    seen = []
    m = HandMapper(load_arm(), load_mapping_config(), smooth=lambda t, xyz: seen.append(xyz) or xyz)
    frames = clip(name)
    t = np.array([f.t for f in frames])
    vis = np.array([f.visible for f in frames])
    raw = np.full((len(frames), 3), np.nan)
    for i, f in enumerate(frames):
        if f.visible:
            m.map(f, 0.5, distance_cm=10800 / f.palm_size())     # stand-in depth, as the sweep
            raw[i] = seen[-1]
    return t, vis, raw


def test_configured_filter_on_real_clips_meets_the_chosen_numbers():
    """Guards the config: if someone retunes it, the jitter/lag the comments promise must hold."""
    data = [mapper_series(n) for n in ("sweep", "palm", "fist", "pinch")]
    runs = []
    for t, vis, raw in data:
        f, out = OneEuro(CFG), np.full_like(raw, np.nan)
        for i in np.flatnonzero(vis):
            out[i] = f(t[i], tuple(raw[i]))
        runs.append((t, vis, raw, out))
    gap = CFG["reset_after_s"]
    img = score(runs, [1, 2], gap)
    dep_raw = score([(t, v, r, r) for t, v, r, _ in runs], [0], gap)
    dep = score(runs, [0], gap)
    with open("config/gestures.yaml", encoding="utf-8") as fh:
        deadband = yaml.safe_load(fh)["modes"]["deadband_mm"]
    assert img.p2p95 < deadband                      # a still hand never moves the arm sideways/up
    assert img.slow_lag_ms <= 50 and img.fast_lag_ms <= 30
    assert dep.p2p95 < 0.5 * dep_raw.p2p95
    assert dep.slow_lag_ms <= 250
