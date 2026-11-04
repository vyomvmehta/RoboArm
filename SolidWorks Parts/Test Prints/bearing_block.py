"""Bearing block for the test print (batch A): three 608 bearing seats at 22.0 / 22.2 / 22.4 mm.

Generates bearing_block.stl next to this file. Units: mm. The part sits on the print bed at z = 0.

    py "SolidWorks Parts/Test Prints/bearing_block.py"

Needs: pip install manifold3d (plus numpy + matplotlib from requirements.txt).
"""
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

# Block
LENGTH, WIDTH, HEIGHT = 82.0, 28.0, 7.0  # HEIGHT = 608 bearing thickness

# Seats: (x centre, diameter). All centred at y = WIDTH / 2, through the block.
SEATS = [(14.0, 22.0), (41.0, 22.2), (68.0, 22.4)]
CHAMFER = 0.4  # bottom edge of each seat, against elephant's foot on the first layers

# Labels engraved into the long side face at y = 0, under each seat
LABEL_HEIGHT = 3.5  # mm, digit height
LABEL_DEPTH = 0.5   # mm
LABEL_FONT = FontProperties(family="DejaVu Sans", weight="bold")

SEGMENTS = 256  # facets per circle: keeps the STL's polygon error under 0.001 mm on a 22 mm seat
EPS = 0.01      # overshoot so cuts don't leave zero-thickness skins


def seat_cutter(x: float, d: float) -> Manifold:
    r = d / 2
    bore = Manifold.cylinder(HEIGHT + 2 * EPS, r, r, SEGMENTS).translate((x, WIDTH / 2, -EPS))
    # Cone from r + CHAMFER at the bed to r at z = CHAMFER: a 45° chamfer on the bottom edge
    cone = Manifold.cylinder(CHAMFER + EPS, r + CHAMFER + EPS, r, SEGMENTS).translate((x, WIDTH / 2, -EPS))
    return bore + cone


def label_cutter(text: str, x_centre: float) -> Manifold:
    path = TextPath((0, 0), text, size=10, prop=LABEL_FONT)
    polys = [p[:-1] for p in path.to_polygons()]  # drop each polygon's repeated closing point
    pts = np.vstack(polys)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    scale = LABEL_HEIGHT / (hi[1] - lo[1])
    # Centre the text on (x_centre, HEIGHT / 2) in the face's own (u = x, v = z) coordinates
    polys = [((p - (lo + hi) / 2) * scale + (x_centre, HEIGHT / 2)).tolist() for p in polys]
    solid = Manifold.extrude(CrossSection(polys, FillRule.EvenOdd), LABEL_DEPTH + EPS)
    # Rotate +90° about x: (u, v, w) -> (u, -w, v), so the text reads correctly from outside the y = 0 face,
    # then shift it to span y = -EPS ... LABEL_DEPTH
    return solid.rotate((90, 0, 0)).translate((0, LABEL_DEPTH, 0))


def build() -> Manifold:
    part = Manifold.cube((LENGTH, WIDTH, HEIGHT))
    for x, d in SEATS:
        part -= seat_cutter(x, d)
        part -= label_cutter(f"{round(d * 10)}", x)
    return part


def write_stl(part: Manifold, path: Path) -> None:
    mesh = part.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3].astype(np.float32)
    tris = np.asarray(mesh.tri_verts)
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    record = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    record["n"], record["v"] = normals, np.stack([v0, v1, v2], axis=1)
    with open(path, "wb") as f:
        f.write(b"RoboArm bearing_block (mm)".ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(record.tobytes())


if __name__ == "__main__":
    part = build()
    out = Path(__file__).with_suffix(".stl")
    write_stl(part, out)
    volume_cm3 = part.volume() / 1000
    print(f"{out.name}: {volume_cm3:.2f} cm^3 solid, about {volume_cm3 * 1.24:.1f} g PLA if printed 100% solid")
