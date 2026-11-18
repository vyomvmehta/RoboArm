#!/usr/bin/env python3
"""
roboarm_bench.py  --  drive the RoboArm v0 firmware from the laptop over USB.

BENCH ONLY. On arming it streams the centre pose to every joint, which is fine for loose
servos on a desk and wrong for an assembled arm: PROTOCOL.md s6 requires the arm to be
resting in the park pose when you arm, and the first C frame after arming must be that
park pose. Use arm/control.py for the real arm; it does this properly.

Speaks docs/PROTOCOL.md to firmware/arm_controller. Opens the port, waits for the
boot banner, arms, then streams C frames at 30 Hz so the 300 ms watchdog never
fires. Type commands to move joints.

    pip install pyserial
    python roboarm_bench.py              # auto-detect the Nano
    python roboarm_bench.py --port COM5  # or name the port

Close the Arduino IDE Serial Monitor first: it holds the port and this will fail.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import serial
import serial.tools.list_ports

BAUD = 115200
NJOINTS = 5
JOINT_NAMES = ["j0_base", "j1_shoulder", "j2_elbow", "j3_wrist", "j4_gripper"]
CENTRE_US = 1500        # override with --centre (MG996R measure at 1425, MG90S at 1625)
SPAN_US = 300           # how far either side of centre to allow


def firmware_hard_limits():
    """Read PULSE_MIN/PULSE_MAX out of the .ino, the same way arm/comms/link.py does, so
    this script can never disagree with the firmware it is driving. Needs to run from the
    repo root."""
    try:
        from arm.comms.link import firmware_limits
        return firmware_limits()
    except Exception as e:
        sys.exit(f"could not read the firmware limits ({e}).\n"
                 f"Run this from the repo root: python tools/roboarm_bench.py")
STREAM_HZ = 30                          # must stay well inside the 300 ms watchdog
BANNER_TIMEOUT_S = 5.0                  # PROTOCOL.md s7 says wait up to 3 s; be generous

ERRORS = {
    1: "bad checksum",
    2: "malformed frame (field count, non-number, or line > 64 chars)",
    3: "pulse outside the firmware's hard limit, whole frame rejected",
    4: "C received while not ARMED",
    5: "unknown message type",
    6: "watchdog fired: no valid C for 300 ms, now HOLD",
    7: "A refused: not in DISARMED",
    8: "PCA9685 not found on I2C at boot, now FAULT",
}


# ---------------------------------------------------------------- protocol

def checksum(body: str) -> str:
    cs = 0
    for byte in body.encode("ascii"):
        cs ^= byte
    return f"{cs:02X}"


def encode(kind: str, seq: int, *fields) -> str:
    body = ",".join([kind, str(seq % 65536), *(str(f) for f in fields)])
    return f"{body}*{checksum(body)}\n"


def decode(line: str) -> tuple[str, int, list[str]]:
    """'K,2,ARMED*26' -> ('K', 2, ['ARMED']). ValueError on anything malformed."""
    line = line.strip()
    body, star, cs = line.rpartition("*")
    if not star:
        raise ValueError(f"no checksum: {line!r}")
    try:
        if checksum(body) != cs.upper():
            raise ValueError(f"bad checksum: {line!r}")
    except UnicodeEncodeError:
        # Line noise on the serial link. Treat as a bad frame, never crash the reader.
        raise ValueError(f"non-ascii bytes: {line!r}") from None
    parts = body.split(",")
    if len(parts) < 2:
        raise ValueError(f"too few fields: {line!r}")
    kind, seq = parts[0], parts[1]
    if not seq.isdigit():
        raise ValueError(f"bad seq: {line!r}")
    return kind, int(seq), parts[2:]


# ---------------------------------------------------------------- link

def open_port(port: str | None, baud: int = BAUD) -> serial.Serial:
    if port is None:
        port = autodetect()
    print(f"opening {port} at {baud}")
    return serial.Serial(port, baud, timeout=0.1)


# Windows names the Nano's USB-serial chip differently depending on which one the
# clone uses: CH340, CP210x, FTDI, or just the generic "USB Serial Port".
USB_SERIAL_HINTS = ("ch340", "ch9102", "arduino", "ftdi", "cp210",
                    "usb serial", "usb-serial", "wch", "silicon labs")


def autodetect() -> str:
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        sys.exit("no serial ports found. Is the Nano plugged in?")
    candidates = []
    for p in ports:
        blob = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
        if "bluetooth" in blob:
            continue                       # virtual COM ports, never the Nano
        if any(k in blob for k in USB_SERIAL_HINTS):
            candidates.append(p.device)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"more than one USB serial port: {', '.join(candidates)}")
    else:
        print("could not identify the Nano. Ports seen:")
        for p in ports:
            print(f"  {p.device}  {p.description}")
    sys.exit("pass one with --port")


class Arm:
    def __init__(self, ser, centre=CENTRE_US, span=SPAN_US, limits=None):
        self.ser = ser
        self.centre = centre
        fw_min, fw_max = limits if limits else firmware_hard_limits()
        # Per joint, and never past the firmware's own limits: it rejects those (error 3).
        self.lo = [max(fw_min[j], centre - span) for j in range(NJOINTS)]
        self.hi = [min(fw_max[j], centre + span) for j in range(NJOINTS)]
        self.seq = 0
        self.state = "?"
        self.target = [centre] * NJOINTS
        self.streaming = False
        self.alive = True
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._streamer = threading.Thread(target=self._stream_loop, daemon=True)

    # -- plumbing ------------------------------------------------

    def start(self):
        self._reader.start()
        self._streamer.start()

    def close(self):
        self.alive = False
        time.sleep(0.1)
        try:
            self.ser.close()
        except Exception:
            pass

    def send(self, kind: str, *fields) -> None:
        with self._lock:
            self.seq = (self.seq + 1) % 65536
            line = encode(kind, self.seq, *fields)
        self.ser.write(line.encode("ascii"))

    def _read_loop(self):
        while self.alive:
            try:
                raw = self.ser.readline()
            except Exception:
                break
            if not raw:
                continue
            text = raw.decode("ascii", errors="replace")
            try:
                kind, seq, fields = decode(text)
            except ValueError as e:
                print(f"\n  [junk] {e}")
                continue
            if kind == "R":
                self.state = fields[1] if len(fields) > 1 else "?"
                print(f"\n  [banner] firmware {fields[0]}, state {self.state}")
            elif kind == "K":
                self.state = fields[0] if fields else "?"
            elif kind == "E":
                code = int(fields[0]) if fields and fields[0].isdigit() else 0
                print(f"\n  [error {code}] {ERRORS.get(code, 'unknown')}")
                if code == 6:
                    self.state = "HOLD"
                elif code == 8:
                    self.state = "FAULT"

    def _stream_loop(self):
        """Keep C frames flowing so the watchdog never fires."""
        period = 1.0 / STREAM_HZ
        while self.alive:
            if self.streaming:
                with self._lock:
                    pose = list(self.target)
                self.send("C", *pose)
            time.sleep(period)

    # -- protocol steps ------------------------------------------

    def wait_for_banner(self, timeout: float = BANNER_TIMEOUT_S) -> bool:
        """Opening the port resets the Nano. Wait for R before sending anything."""
        print("waiting for the boot banner (the Nano resets when the port opens)...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.state in ("DISARMED", "FAULT"):
                return self.state == "DISARMED"
            time.sleep(0.05)
        print("  no banner. Wrong port, or the firmware is not running.")
        return False

    def arm(self):
        self.send("A")
        time.sleep(0.2)
        if self.state == "ARMED":
            self.streaming = True          # start the keepalive only once armed
            print(f"  armed, streaming C at {STREAM_HZ} Hz")
        else:
            print(f"  arm failed, state is {self.state}")

    def disarm(self):
        self.streaming = False
        time.sleep(0.1)
        self.send("D")
        time.sleep(0.2)
        print(f"  state {self.state} (servos are limp)")

    def set_joint(self, idx: int, us: int):
        if not 0 <= idx < NJOINTS:
            print(f"  joint must be 0-{NJOINTS - 1}")
            return
        if not self.lo[idx] <= us <= self.hi[idx]:
            print(f"  {us} us is outside ch{idx}'s band {self.lo[idx]}-{self.hi[idx]}")
            return
        with self._lock:
            self.target[idx] = us
        print(f"  {JOINT_NAMES[idx]} -> {us} us")

    def set_all(self, us: int):
        bad = [j for j in range(NJOINTS) if not self.lo[j] <= us <= self.hi[j]]
        if bad:
            print(f"  {us} us is outside the band on joint(s) {bad}")
            return
        with self._lock:
            self.target = [us] * NJOINTS
        print(f"  all joints -> {us} us")


# ---------------------------------------------------------------- shell

HELP = """
commands
  j <0-4> <us>   move one joint        e.g.  j 4 1700
  all <us>       move every joint      e.g.  all 1500
  centre         every joint to 1500
  pose <5 us>    full pose             e.g.  pose 1500 1500 1500 1500 1200
  a              arm
  d              disarm (servos go limp)
  p              ping
  s              show state and target
  q              disarm and quit
"""


def shell(arm: Arm):
    print(HELP)
    while True:
        try:
            raw = input("arm> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        parts = raw.split()
        cmd = parts[0].lower()
        try:
            if cmd == "q":
                break
            elif cmd == "a":
                arm.arm()
            elif cmd == "d":
                arm.disarm()
            elif cmd == "p":
                arm.send("P")
            elif cmd == "s":
                print(f"  state {arm.state}, target {arm.target}, streaming {arm.streaming}")
            elif cmd == "centre" or cmd == "center":
                arm.set_all(arm.centre)
            elif cmd == "all" and len(parts) == 2:
                arm.set_all(int(parts[1]))
            elif cmd == "j" and len(parts) == 3:
                arm.set_joint(int(parts[1]), int(parts[2]))
            elif cmd == "pose" and len(parts) == 1 + NJOINTS:
                vals = [int(v) for v in parts[1:]]
                if all(arm.lo[j] <= v <= arm.hi[j] for j, v in enumerate(vals)):
                    with arm._lock:
                        arm.target = vals
                    print(f"  pose -> {vals}")
                else:
                    print(f"  per-joint bands: {list(zip(arm.lo, arm.hi))}")
            else:
                print(HELP)
        except ValueError:
            print("  numbers only")
    arm.disarm()


def main():
    ap = argparse.ArgumentParser(description="Bench-drive the RoboArm v0 firmware.")
    ap.add_argument("--port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=BAUD)
    ap.add_argument("--centre", type=int, default=CENTRE_US,
                    help="measured midpoint of your servos in us (default 1500)")
    ap.add_argument("--span", type=int, default=SPAN_US,
                    help="how far either side of centre to allow (default 300)")
    args = ap.parse_args()

    ser = open_port(args.port, args.baud)
    arm = Arm(ser, centre=args.centre, span=args.span)
    print(f"centre {arm.centre} us; per-joint bands {list(zip(arm.lo, arm.hi))}")
    print("BENCH ONLY: arming streams the centre pose, not the park pose.")
    arm.start()

    try:
        if not arm.wait_for_banner():
            return
        shell(arm)
    finally:
        arm.close()
        print("port closed")


if __name__ == "__main__":
    main()
