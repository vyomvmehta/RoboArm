"""The laptop's side of the serial link to the Nano (docs/PROTOCOL.md).

Three classes with the same interface, so the server never cares which one it has:

  SerialLink  the real USB cable (pyserial). A background thread reads the Nano's replies.
  FakeNano    a pretend Nano in software that follows the same rules as Ishaan's firmware v0
              (banner, acks, error codes, 300 ms watchdog). Used with --fake and in the tests.
  Link        the shared part: sequence numbers, sending frames, reading replies, and keeping
              track of what state the Nano says it is in.

Why a background thread: reading the serial port BLOCKS (the call waits until a line arrives).
The web server must never block, or every browser freezes. So one thread does nothing but
wait for lines from the Nano and record what they say; everything else just reads that record.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from pathlib import Path

from arm.comms.protocol import decode, encode

# PROTOCOL.md section 5, for messages a human can read.
ERRORS = {
    1: "bad checksum", 2: "malformed line", 3: "pulse outside the firmware's hard limit",
    4: "C received while not armed", 5: "unknown message type",
    6: "watchdog: no C for 300 ms, holding position", 7: "A refused (not DISARMED)",
    8: "PCA9685 not found at boot",
}


class LinkError(RuntimeError):
    pass


class Link:
    """Shared logic. Subclasses only provide _write(text) and start/close."""

    def __init__(self):
        self.seq = 0
        self.state = "UNKNOWN"          # what the Nano last told us: DISARMED/ARMED/HOLD/FAULT
        self.firmware = None            # from the R banner, e.g. "fw0.1"
        self.last_error = None          # (code, text) of the most recent E line
        self.rtt_ms = None              # round-trip time of the most recent acknowledged C
        self.connected = False
        self._sent_at = {}              # seq -> time sent, to measure round-trip time
        self._lock = threading.Lock()   # send() can be called from more than one place
        self._banner = threading.Event()
        self.log = deque(maxlen=50)     # last few lines in both directions, for debugging

    # ---------------------------------------------------------------- sending
    def send(self, kind: str, *fields) -> str:
        with self._lock:
            self.seq = (self.seq + 1) % 65536
            line = encode(kind, self.seq, *fields)
            self._sent_at[self.seq] = time.perf_counter()
            if len(self._sent_at) > 200:            # forget old ones that never got an ack
                for s in list(self._sent_at)[:100]:
                    del self._sent_at[s]
            self.log.append(">> " + line.strip())
            self._write(line)
            return line

    def _write(self, line: str):
        raise NotImplementedError

    # ---------------------------------------------------------------- receiving
    def _handle_line(self, raw: str):
        """Called for every line the Nano sends. Updates our record of the Nano's state."""
        raw = raw.strip()
        if not raw:
            return
        self.log.append("<< " + raw)
        try:
            kind, seq, fields = decode(raw)
        except ValueError:
            return  # a garbled reply: ignore it, exactly like the firmware ignores ours
        if kind == "R":                      # boot banner: R,0,<fw>,<state>
            self.firmware, self.state = fields[0], fields[1]
            self._banner.set()
        elif kind == "K":                    # ack: K,<seq>,<state>
            self.state = fields[0]
            sent = self._sent_at.pop(seq, None)
            if sent is not None:
                self.rtt_ms = (time.perf_counter() - sent) * 1000
        elif kind == "E":                    # error: E,<seq>,<code>
            code = int(fields[0])
            self.last_error = (code, ERRORS.get(code, f"error {code}"))
            if code == 6:
                self.state = "HOLD"          # the watchdog fired (PROTOCOL.md section 6)
            elif code == 8:
                self.state = "FAULT"

    def wait_for_banner(self, timeout_s: float) -> None:
        if not self._banner.wait(timeout_s):
            raise LinkError(
                f"no R banner from the Nano within {timeout_s} s. Check: right COM port? "
                "firmware uploaded? Arduino IDE Serial Monitor closed (it locks the port)?")
        if self.state != "DISARMED":
            raise LinkError(f"Nano booted in {self.state}, not DISARMED (PCA9685 wired?)")

    def status(self) -> dict:
        err = self.last_error
        return {"connected": self.connected, "state": self.state, "firmware": self.firmware,
                "error": f"E{err[0]}: {err[1]}" if err else None,
                "rtt_ms": round(self.rtt_ms, 1) if self.rtt_ms is not None else None}

    def close(self):
        self.connected = False


class SerialLink(Link):
    def __init__(self, port: str, baud: int = 115200):
        super().__init__()
        import serial  # pyserial; imported here so --fake and the tests don't need a port

        try:
            # Opening the port toggles DTR, which RESETS the Nano (PROTOCOL.md section 7).
            # That's safe by design: it reboots DISARMED with the servos limp.
            self._port = serial.Serial(port, baud, timeout=0.1)
        except serial.SerialException as e:
            raise LinkError(f"could not open {port}: {e}") from None
        self.connected = True
        self._reader = threading.Thread(target=self._read_forever, daemon=True)
        self._reader.start()

    def _read_forever(self):
        buf = b""
        while self.connected:
            try:
                # Read whatever has ARRIVED (at least 1 byte, waiting up to 0.1 s for it).
                # read(64) would wait until 64 bytes piled up (several K replies) on Windows,
                # which delayed each reply and inflated the measured round trip (Nov 10 bench).
                chunk = self._port.read(self._port.in_waiting or 1)
            except Exception:                     # cable pulled, port gone
                self.connected = False
                self.state = "DISCONNECTED"
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line.decode("ascii", errors="replace"))

    def _write(self, line: str):
        try:
            self._port.write(line.encode("ascii"))
        except Exception as e:
            self.connected = False
            self.state = "DISCONNECTED"
            raise LinkError(f"write failed: {e}") from None

    def close(self):
        super().close()
        try:
            self._port.close()
        except Exception:
            pass


FIRMWARE = Path(__file__).resolve().parents[2] / "firmware" / "arm_controller" / "arm_controller.ino"


def firmware_limits(path: Path = FIRMWARE) -> tuple[list[int], list[int]]:
    """PULSE_MIN / PULSE_MAX read straight from the firmware source, so FakeNano can never
    drift from the real hard limits (they are about to be widened, PR #6 review)."""
    src = path.read_text(encoding="utf-8")

    def array(name):
        m = re.search(name + r"\s*\[\s*NJOINTS\s*\]\s*=\s*\{([^}]*)\}", src)
        if not m:
            raise LinkError(f"{name} not found in {path}")
        return [int(v) for v in m.group(1).split(",")]

    return array("PULSE_MIN"), array("PULSE_MAX")


class FakeNano(Link):
    """A pretend Nano that answers exactly like firmware/arm_controller (v0), handler by
    handler, so the whole laptop side can be tested with no hardware. It moves nothing.

    Each branch below mirrors one handle_*() in the .ino, including the ORDER of its checks
    (e.g. a C frame's field count is checked before the armed state), so the same frame
    gets the same reply here and on the real Nano."""

    def __init__(self, watchdog_ms: float = 300):
        super().__init__()
        self.connected = True
        self.watchdog_s = watchdog_ms / 1000
        self.pulse_min, self.pulse_max = firmware_limits()
        self.pulses = None                      # what the servos would be doing
        self._fw_state = "DISARMED"
        self._last_c = None
        self._timer = threading.Thread(target=self._watchdog_forever, daemon=True)
        self._timer.start()
        self._reply("R", 0, "fw0.1", "DISARMED")

    def _reply(self, kind, seq, *fields):
        self._handle_line(encode(kind, seq, *fields))

    def _write(self, line: str):
        kind, seq, fields = decode(line)
        nfields = 2 + len(fields)               # the firmware counts TYPE and seq too
        st = self._fw_state
        if kind == "C":                         # handle_c
            if nfields != 2 + 5:
                return self._reply("E", seq, 2)
            if st not in ("ARMED", "HOLD"):
                return self._reply("E", seq, 4)
            if not all(f.isdigit() for f in fields):
                return self._reply("E", seq, 2)
            p = [int(f) for f in fields]
            if any(not lo <= v <= hi for v, lo, hi in zip(p, self.pulse_min, self.pulse_max)):
                return self._reply("E", seq, 3)
            self.pulses, self._fw_state, self._last_c = p, "ARMED", time.monotonic()
        elif kind in ("A", "D", "H", "P") and nfields != 2:
            return self._reply("E", seq, 2)     # every other type takes no fields
        elif kind == "A":                       # handle_a
            if st != "DISARMED":
                return self._reply("E", seq, 7)
            self._fw_state, self._last_c = "ARMED", time.monotonic()
        elif kind == "D":                       # handle_d: FAULT only clears on reset
            self.pulses = None
            if st != "FAULT":
                self._fw_state = "DISARMED"
        elif kind == "H":                       # handle_h: v0 acks but does not move
            if st != "ARMED":
                return self._reply("E", seq, 4)
        elif kind != "P":                       # handle_p: ping, touches nothing
            return self._reply("E", seq, 5)
        self._reply("K", seq, self._fw_state)

    def _watchdog_forever(self):
        while self.connected:
            time.sleep(0.01)
            if (self._fw_state == "ARMED" and self._last_c is not None
                    and time.monotonic() - self._last_c >= self.watchdog_s):
                self._fw_state = "HOLD"
                self._reply("E", 0, 6)


def open_link(port: str | None, baud: int, banner_timeout_s: float, fake: bool) -> Link:
    link = FakeNano() if fake or not port else SerialLink(port, baud)
    link.wait_for_banner(banner_timeout_s)
    return link
