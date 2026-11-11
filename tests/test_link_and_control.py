"""Step 5: the link and the controller, tested against FakeNano (firmware v0's rules)."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from arm.calibration import load_calibration
from arm.comms.link import FakeNano, LinkError, open_link
from arm.config import load_arm
from arm.control import Controller
from arm.web.server import create_app


@pytest.fixture
def cal():
    return load_calibration(load_arm())


def sent(link, kind):
    """Frames of one type the laptop sent, oldest first."""
    return [l[3:] for l in link.log if l.startswith(">> " + kind + ",")]


# ------------------------------------------------------------------ the link
def test_banner_then_disarmed():
    link = open_link(None, 115200, 1.0, fake=True)
    assert (link.firmware, link.state) == ("fw0.1", "DISARMED")


def test_ack_updates_state_and_round_trip_time():
    link = FakeNano()
    link.send("A")
    assert link.state == "ARMED" and link.rtt_ms is not None


def test_watchdog_fires_without_heartbeat():
    link = FakeNano()
    link.send("A")
    time.sleep(0.45)                                   # > 300 ms with no C frame
    assert link.state == "HOLD" and link.last_error[0] == 6


def test_missing_banner_gives_a_helpful_error():
    link = FakeNano()
    link._banner.clear()
    with pytest.raises(LinkError, match="Serial Monitor"):
        link.wait_for_banner(0.05)


# ------------------------------------------------------------------ the controller
def test_first_frame_after_arming_is_the_park_pose(cal):
    async def go():
        link = FakeNano()
        c = Controller(link, cal, heartbeat_hz=30)
        assert await c.arm() is None
        await asyncio.sleep(0.05)
        await c.disarm()
        return link, c

    link, c = asyncio.run(go())
    frames = [l[3:] for l in link.log if l.startswith(">> ")]
    assert frames[0].startswith("A,")
    first_c = [int(v) for v in frames[1].split("*")[0].split(",")[2:]]
    assert first_c == cal.to_pulses(c.park_values())


def test_heartbeat_keeps_it_armed_at_about_30_hz(cal):
    async def go():
        link = FakeNano()
        c = Controller(link, cal, heartbeat_hz=30)
        await c.arm()
        await asyncio.sleep(0.6)                       # twice the watchdog time
        state = link.state
        await c.disarm()
        return link, state

    link, state = asyncio.run(go())
    assert state == "ARMED"                            # the watchdog never fired
    assert 14 <= len(sent(link, "C")) <= 22            # 0.6 s x 30 Hz = 18


def test_rejected_target_is_not_sent_and_old_target_stays(cal):
    async def go():
        link = FakeNano()
        c = Controller(link, cal)
        await c.arm()
        before = c.target_us
        why = c.set_target([200, 0, 0, 0, 20])         # base at 200 deg: impossible
        await c.disarm()
        return why, before, c.target_us

    why, before, after = asyncio.run(go())
    assert why and after == before


def test_targets_refused_while_disarmed(cal):
    c = Controller(FakeNano(), cal)
    assert "not armed" in c.set_target([0, 60, -70, -30, 20])


def test_disarm_stops_the_heartbeat(cal):
    async def go():
        link = FakeNano()
        c = Controller(link, cal)
        await c.arm()
        await asyncio.sleep(0.1)
        await c.disarm()
        n = len(sent(link, "C"))
        await asyncio.sleep(0.2)
        return link, n

    link, n = asyncio.run(go())
    assert len(sent(link, "C")) == n and link.state == "DISARMED"


# ------------------------------------------------------------------ the web server
def test_browser_disconnect_while_armed_disarms_dead_man_rule():
    link = FakeNano()
    with TestClient(create_app(link)) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "arm"}))
            time.sleep(0.2)
            assert link.state == "ARMED"
        time.sleep(0.2)                                # socket closed: the server reacts
    assert link.state == "DISARMED" and sent(link, "D")


def test_only_one_browser_can_drive_the_arm():
    with TestClient(create_app(FakeNano())) as client:
        with client.websocket_connect("/ws"):
            with client.websocket_connect("/ws") as second:
                assert json.loads(second.receive_text())["type"] == "busy"


# ------------------------------------------------------------------ FakeNano == firmware v0
# Each row: state to put the fake in, frame sent, reply the REAL firmware gives (read off
# the handle_*() functions in firmware/arm_controller/arm_controller.ino). PR #6 review found
# the first two rows wrong in the old FakeNano, which would have let a laptop bug pass tests.
FIRMWARE_CASES = [
    ("ARMED",    "H", [],                          "K", "ARMED"),   # H is a valid type
    ("ARMED",    "C", [1500] * 4,                  "E", "2"),       # wrong field count
    ("DISARMED", "C", [1500] * 4,                  "E", "2"),       # field count checked first
    ("DISARMED", "C", [1500] * 5,                  "E", "4"),       # C while not armed
    ("ARMED",    "C", [1500] * 4 + ["15x0"],       "E", "2"),       # non-number
    ("ARMED",    "C", [1500] * 4 + [2600],         "E", "3"),       # outside the hard limit
    ("DISARMED", "H", [],                          "E", "4"),       # H needs ARMED
    ("DISARMED", "A", [1],                         "E", "2"),       # A takes no fields
    ("ARMED",    "A", [],                          "E", "7"),       # A only from DISARMED
    ("ARMED",    "P", [],                          "K", "ARMED"),   # ping
    ("ARMED",    "X", [],                          "E", "5"),       # unknown type
    ("ARMED",    "D", [],                          "K", "DISARMED"),
]


@pytest.mark.parametrize("state,kind,fields,reply_kind,reply_field", FIRMWARE_CASES)
def test_fake_nano_answers_like_the_firmware(state, kind, fields, reply_kind, reply_field):
    from arm.comms.protocol import decode, encode
    link = FakeNano()
    if state == "ARMED":
        link.send("A")
    link._write(encode(kind, 7, *fields))
    kind_got, seq_got, fields_got = decode(link.log[-1][3:])
    assert (kind_got, seq_got, fields_got[0]) == (reply_kind, 7, reply_field)


def test_fake_nano_limits_are_read_from_the_firmware_source():
    import re
    from arm.comms.link import FIRMWARE, firmware_limits
    src = FIRMWARE.read_text(encoding="utf-8")
    lo, hi = firmware_limits()
    assert len(lo) == len(hi) == 5
    assert str(lo[0]) in re.search(r"PULSE_MIN.*", src).group(0)
    assert FakeNano().pulse_min == lo
