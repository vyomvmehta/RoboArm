import pytest

from arm.comms.protocol import decode, encode

# Test vectors from docs/PROTOCOL.md section 2. The firmware must match these exactly.
VECTORS = [
    ("C,1,1500,1500,1500,1500,1500*76", ("C", 1, [1500] * 5)),
    ("C,2,1100,1620,1480,1500,2000*7F", ("C", 2, [1100, 1620, 1480, 1500, 2000])),
    ("A,3*5E", ("A", 3, [])),
    ("D,4*5C", ("D", 4, [])),
    ("H,5*51", ("H", 5, [])),
    ("K,2,ARMED*26", ("K", 2, ["ARMED"])),
    ("E,9,3*4F", ("E", 9, [3])),
    ("R,0,fw0.1,DISARMED*71", ("R", 0, ["fw0.1", "DISARMED"])),
]


@pytest.mark.parametrize("line,msg", VECTORS)
def test_encode_matches_protocol_md(line, msg):
    kind, seq, fields = msg
    assert encode(kind, seq, *fields) == line + "\n"


@pytest.mark.parametrize("line,msg", VECTORS)
def test_decode_round_trip(line, msg):
    kind, seq, fields = decode(line)
    assert (kind, seq, fields) == (msg[0], msg[1], [str(f) for f in msg[2]])


def test_corrupted_line_is_rejected():
    with pytest.raises(ValueError):
        decode("C,1,1500,1500,9500,1500,1500*76")  # one digit flipped in transit


def test_seq_wraps_at_65536():
    assert encode("A", 65536).startswith("A,0*")
