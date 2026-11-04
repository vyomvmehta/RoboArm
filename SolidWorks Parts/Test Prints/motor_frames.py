"""Motor pocket test frames (batch A, part 2): MG996R and MG90S body pockets at three clearances.

Generates mg996r_frames.stl and mg90s_frames.stl next to this file. Units: mm, part on the bed at z = 0.
Each plate has three through-pockets, labelled on the long side face: 10 / 25 / 40 = +0.10 / +0.25 / +0.40 mm.

    py "SolidWorks Parts/Test Prints/motor_frames.py"
"""
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

from bearing_block import EPS, write_stl

# Measured motor bodies (Siddharth's sheet, Nov 3): width x length, not counting the mounting tabs
MOTORS = {
    "mg996r": (19.8, 40.5),
    "mg90s": (11.9, 22.8),
}
CLEARANCES = [0.10, 0.25, 0.40]  # added to width and length. D15: big features shrank only about 0.05-0.1 mm
THICKNESS = 5.0  # plate thickness: enough to feel whether the body wobbles
WALL = 3.0       # around and between the pockets

LABEL_HEIGHT = 3.0
LABEL_DEPTH = 0.5
LABEL_FONT = FontProperties(family="DejaVu Sans", weight="bold")


def side_label(text: str, x_centre: float) -> Manifold:
    """Text cut LABEL_DEPTH into the y = 0 face, centred at (x_centre, THICKNESS / 2), readable from outside."""
    path = TextPath((0, 0), text, size=10, prop=LABEL_FONT)
    polys = [p[:-1] for p in path.to_polygons()]
    pts = np.vstack(polys)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    scale = LABEL_HEIGHT / (hi[1] - lo[1])
    polys = [((p - (lo + hi) / 2) * scale + (x_centre, THICKNESS / 2)).tolist() for p in polys]
    solid = Manifold.extrude(CrossSection(polys, FillRule.EvenOdd), LABEL_DEPTH + EPS)
    return solid.rotate((90, 0, 0)).translate((0, LABEL_DEPTH, 0))


def build(width: float, length: float) -> Manifold:
    pockets = [(width + c, length + c) for c in CLEARANCES]
    plate_x = sum(w for w, _ in pockets) + WALL * (len(pockets) + 1)
    plate_y = max(l for _, l in pockets) + 2 * WALL
    part = Manifold.cube((plate_x, plate_y, THICKNESS))
    x = WALL
    for (w, l), c in zip(pockets, CLEARANCES):
        cut = Manifold.cube((w, l, THICKNESS + 2 * EPS)).translate((x, (plate_y - l) / 2, -EPS))
        part -= cut
        part -= side_label(f"{round(c * 100)}", x + w / 2)
        x += w + WALL
    return part


if __name__ == "__main__":
    for name, (w, l) in MOTORS.items():
        part = build(w, l)
        out = Path(__file__).with_name(f"{name}_frames.stl")
        write_stl(part, out)
        print(f"{out.name}: {part.volume() / 1000:.2f} cm^3 solid, about {part.volume() / 1000 * 1.24:.1f} g if 100% solid")
