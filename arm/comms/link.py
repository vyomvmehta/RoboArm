"""The laptop's side of the serial link.

FakeLink prints every frame instead of sending it, so the whole laptop side runs without a
Nano. Step 5 adds SerialLink (pyserial) with the same send() method, so the server never
needs to know which one it has.
"""
from __future__ import annotations

from arm.comms.protocol import encode


class FakeLink:
    def __init__(self):
        self.seq = 0

    def send(self, kind: str, *fields) -> str:
        self.seq = (self.seq + 1) % 65536
        line = encode(kind, self.seq, *fields)
        print("serial >>", line.strip())
        return line
