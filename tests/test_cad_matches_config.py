"""The CAD build script and config/arm.yaml must agree on the link lengths (PR #14 review).

build_arm.py runs only inside SolidWorks, but its constants are plain text, so this check
needs no SolidWorks. It would have caught the stale "l3 70 -> 75" drift.
"""
import re
from pathlib import Path

from arm.config import load_arm

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "cad" / "build_arm.py"


def _const(name):
    m = re.search(rf"^{name}\s*=\s*([0-9.]+)", SCRIPT.read_text(encoding="utf-8"), re.M)
    assert m, f"{name} not found in build_arm.py"
    return float(m.group(1))


def test_build_arm_link_lengths_match_arm_yaml():
    links = load_arm().raw["links"]
    assert _const("L1") == links["l1"]
    assert _const("L2") == links["l2"]
