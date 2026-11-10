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

import threading
import time
from collections import deque

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
                chunk = self._port.read(64)       # returns after 0.1 s even if nothing came
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


class FakeNano(Link):
    """A pretend Nano that follows firmware v0's rules, so the whole laptop side can be
    tested with no hardware. It does NOT move anything; it only answers like the firmware."""

    def __init__(self, watchdog_ms: float = 300):
        super().__init__()
        self.connected = True
        self.watchdog_s = watchdog_ms / 1000
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
        if kind == "A":
            if self._fw_state != "DISARMED":
                return self._reply("E", seq, 7)
            self._fw_state, self._last_c = "ARMED", time.monotonic()
        elif kind == "D":
            self._fw_state, self.pulses = "DISARMED", None
        elif kind == "C":
            if self._fw_state not in ("ARMED", "HOLD"):
                return self._reply("E", seq, 4)
            p = [int(f) for f in fields]
            if any(not 1000 <= v <= 2000 for v in p):   # firmware v0's hard limits
                return self._reply("E", seq, 3)
            self.pulses, self._fw_state, self._last_c = p, "ARMED", time.monotonic()
        elif kind != "P":
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
