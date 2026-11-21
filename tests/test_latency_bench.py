"""tools/latency_bench.py (partial V2-13): replay mode end to end, and live mode's camera failures.
No real camera is ever opened here: live mode is tested with stand-in Camera classes."""
import asyncio
import csv
import glob
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import latency_bench as lb  # noqa: E402

SWEEP = sorted(glob.glob(str(ROOT / "runs" / "hands" / "sweep-*.csv")))[0]


def test_replay_measures_the_downstream_chain_and_says_what_it_skips(tmp_path, capsys):
    out = asyncio.run(lb.main(lb.parse(["--replay", SWEEP, "--frames", "40", "--out", str(tmp_path / "r.csv")])))
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    acc = [r for r in rows if r["accepted"] == "1"]
    assert len(acc) >= 40
    for r in acc:                           # every downstream stage timed, capture stages empty
        for s in ("pinch", "map_pre", "filter", "map_post", "set_target", "processing", "to_send", "total"):
            assert float(r[s + "_ms"]) >= 0, s
        assert r["camera_wait_ms"] == r["track_ms"] == ""
        assert float(r["total_ms"]) == pytest.approx(float(r["processing_ms"]) + float(r["to_send_ms"]), abs=0.01)
        assert float(r["to_send_ms"]) < 200           # the 30 Hz heartbeat picked it up
    text = capsys.readouterr().out
    assert "DOWNSTREAM STAGES ONLY" in text and "NOT hand-to-arm" in text
    assert "frame_interval (recorded in clip)" in text


def test_replay_loops_the_clip_with_a_gap_so_time_keeps_rising():
    src = lb.ReplaySource(SWEEP)
    src.start = time.perf_counter() - 1e6            # due times all in the past: no waiting
    n = len(src.frames)
    ts = [src.next()[0].t for _ in range(n + 3)]
    assert all(b > a for a, b in zip(ts, ts[1:]))
    assert ts[n] - ts[n - 1] >= 1.0                  # > filter.reset_after_s: filter restarts


def _live_with(camera_cls: str, timeout: float = 1.0):
    """Run --live in a subprocess with a stand-in Camera (live failures os._exit)."""
    code = "\n".join([
        "import asyncio, sys, time",
        f"sys.path.insert(0, r'{ROOT / 'tools'}')",
        "import latency_bench as lb",
        textwrap.dedent(camera_cls).strip(),
        "lb.Camera = Cam",
        f"asyncio.run(lb.main(lb.parse(['--live', '--camera-timeout', '{timeout}'])))",
    ])
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=60)
    return p, time.perf_counter() - t0


def test_live_stops_with_a_message_when_the_camera_never_answers():
    p, took = _live_with("""
        class Cam:
            def __init__(self, *a): pass
            def read(self):
                time.sleep(3600)
            def close(self): pass""")
    assert p.returncode == 2
    assert "CAMERA PROBLEM" in p.stderr and "no answer from the camera" in p.stderr
    assert took < 20                                  # 1 s timeout, not a hang


def test_live_stops_with_a_message_when_the_camera_gives_no_frames():
    p, _ = _live_with("""
        class Cam:
            def __init__(self, *a): pass
            def read(self):
                raise RuntimeError("camera stopped giving frames")
            def close(self): pass""")
    assert p.returncode == 2
    assert "CAMERA PROBLEM" in p.stderr and "stopped giving frames" in p.stderr


def test_a_mode_is_required_and_help_explains_both():
    with pytest.raises(SystemExit):
        lb.parse([])
    doc = lb.__doc__
    for phrase in ("--replay", "--live", "DOWNSTREAM", "MediaPipe", "ABOUT A MINUTE", "NOT HAND-TO-ARM"):
        assert phrase in doc
