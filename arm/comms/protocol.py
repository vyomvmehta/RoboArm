"""Text frames for docs/PROTOCOL.md section 2:   <TYPE>,<seq>[,<field>...]*<CS>\\n

CS = XOR of every byte before the '*', as 2 upper-case hex digits (same scheme as NMEA GPS).
The firmware (Ishaan) must produce and accept exactly these bytes; the test vectors in
PROTOCOL.md are checked on both sides.
"""
from __future__ import annotations


def checksum(body: str) -> str:
    cs = 0
    for byte in body.encode("ascii"):
        cs ^= byte
    return f"{cs:02X}"


def encode(kind: str, seq: int, *fields) -> str:
    """encode("C", 1, 1500, ...) -> 'C,1,1500,...*76\\n'"""
    if not (len(kind) == 1 and kind.isupper()):
        raise ValueError(f"bad message type {kind!r}")
    body = ",".join([kind, str(seq % 65536), *(str(f) for f in fields)])
    return f"{body}*{checksum(body)}\n"


def decode(line: str) -> tuple[str, int, list[str]]:
    """'K,2,ARMED*26' -> ('K', 2, ['ARMED']). Raises ValueError on a bad checksum or format."""
    line = line.strip()
    body, star, cs = line.rpartition("*")
    if not star or checksum(body) != cs.upper():
        raise ValueError(f"bad checksum: {line!r}")
    kind, seq, *fields = body.split(",")
    return kind, int(seq), fields
