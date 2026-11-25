r"""Build Plate 13: Siddharth's Enclosure, the box itself.

The box is the one part of the base that no other plate holds. make_plates.py and pack_plates.py
both pack only ..\STL\grap_*.stl - the parts grap_base_pivot.py generates - and the Enclosure is
Siddharth's own SolidWorks part, so it has never been in either script's scope. Plates 11 and 12
cover the twelve generated parts; this covers the thirteenth thing the base needs.

Run with plain python, no cadquery:  python make_plate13.py

Built from the CORRECTED box, not the raw export. D29 found four of the twelve floor pilots - the
servo bridge's - sitting 2.0 mm out, at the pre-D26 SERVO_SHAFT_OFFSET 10.0 position. Nothing had
been printed yet when that turned up, so fix_enclosure_pilots.py moves those four holes instead of
leaving someone to drill them out afterwards; this script runs it if the corrected STL is missing.
Enclosure.SLDPRT itself is still wrong and Siddharth still needs to move those holes at the
source - re-exporting from it would bring the error back.

Orientation: (x, -z, y), a proper +90 deg rotation about X, NOT a mirror - the box is asymmetric
(the bridge pilots are off-centre), so a reflection would put them on the wrong side. That lands
the 5 mm floor flat on the bed with the open side up: 254.6 cm2 of first-layer contact, no
overhangs, no supports. USE A BRIM - this is a 170 x 170 solid slab, the same warp risk as
Plate 11's base plate, and at 265 cm3 it is the single largest print in the project.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv = ["make_plates.py", ".", "."]          # make_plates.main() reads argv; we only want plate()
sys.path.insert(0, str(HERE))
import make_plates as mp                          # noqa: E402

import fix_enclosure_pilots as fix                 # noqa: E402

STL = fix.DST
OUT = HERE / "UltiMaker plates (open in Cura)"
NAME = "Plate 13 - box (Enclosure, pilots corrected - D29).3mf"


def standing_up(t):
    """Floor down, open side up. +90 deg about X: det = +1, so no mirroring."""
    return [[(v[0], -v[2], v[1]) for v in tri] for tri in t]


if __name__ == "__main__":
    if not STL.exists():
        print(f"{STL.name} not there yet, building it:")
        fix.main()
        print()
    OUT.mkdir(exist_ok=True)
    print(NAME)
    mp.plate(OUT / NAME, [("Box (Enclosure)", STL, 1, standing_up)])
    print("\nOne object, so there is no welded .stl fallback beside it: the fallback exists for"
          "\nplates where Cura re-centres several objects on top of each other.")
