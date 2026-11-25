r"""Move the box's four servo-bridge floor pilots 2.0 mm to +x, so they land where the bridge is.

D29: Enclosure.STL carries all twelve floor pilots, but the four for the servo bridge sit at
servo_cx -22.2 - the pre-D26 SERVO_SHAFT_OFFSET 10.0 position - and the bridge now wants -20.2.
In box coordinates that is x 38.8 / 86.8 where it should be 40.8 / 88.8. The eight wheel-fork
pilots, radius 55.5 and +-13.5 from the axis, are correct and are not touched.

This matters because the bridge CANNOT be moved to suit the box instead. The servo shaft has to
sit at -centre_dist = -32.5 from the box axis for the 16T sun and 36T planet to mesh at all, and
the bridge's pocket is what puts it there; shifting the bridge 2 mm shifts the shaft 2 mm, against
a designed backlash of 0.2 mm. So the box is the part that has to change.

Method: translate every vertex within r < 1.3 mm of each of the four pilot axes by +2.0 mm in x.
Each pilot is exactly 73 vertices - 36 on the rim at y 0.5 plus that cap's fan centre, and 36 on
the rim at y 5.0 where it opens into the floor - so the cylinder and its blind cap move rigidly
and only the floor's top face stretches around them. No triangle is added or removed, so the mesh
stays watertight by construction. The nearest vertex outside any pilot is 5.77 mm away and the
nearest in the +x direction 6.07 mm, against the 2.0 + 1.25 = 3.25 mm that would be needed to
invert a triangle, so nothing folds. Facet normals are recomputed from the winding afterwards,
because the stretched floor triangles change plane slightly.

THIS DOES NOT FIX THE SOURCE PART. Enclosure.SLDPRT still has the pilots in the old place, so
re-exporting the STL from it brings the error straight back. Siddharth owns the enclosure and
needs to move those four holes in SolidWorks; until then, print from the corrected STL this
writes, and keep this script so the correction can be reapplied to a fresh export.

Run with plain python, no cadquery:  python fix_enclosure_pilots.py
"""
import math
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "STL" / "Enclosure.STL"
DST = HERE.parent / "STL" / "Enclosure corrected (bridge pilots +2mm, D29).STL"

BOX_CENTRE = 85.0          # 170 mm box, axis at (85, 85) in the STL's frame
SERVO_CX_OLD = -22.2       # what the STL was drilled against
SERVO_CX_NEW = -20.2       # SERVO_SHAFT_OFFSET 8.0, measured Nov 22 (D26)
FOOT_DX, FOOT_DZ = 24.0, 45.0      # floor_pilots(): servo_cx +- 24, +-45
SHIFT = SERVO_CX_NEW - SERVO_CX_OLD                       # +2.0
CATCH_R = 1.3                                             # pilot is r 1.25


def axes():
    return [(BOX_CENTRE + SERVO_CX_OLD + sx * FOOT_DX, BOX_CENTRE + sz * FOOT_DZ)
            for sx in (-1, 1) for sz in (-1, 1)]


def read_binary_stl(path):
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 80)[0]
    return [[struct.unpack_from("<3f", b, 84 + i * 50 + 12 + k * 12) for k in range(3)]
            for i in range(n)]


def write_binary_stl(path, tris, header=b"RoboArm Enclosure, bridge pilots corrected (D29)"):
    out = bytearray(header[:80].ljust(80, b"\0"))
    out += struct.pack("<I", len(tris))
    for a, b, c in tris:
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        nx, ny, nz = (u[1] * v[2] - u[2] * v[1],
                      u[2] * v[0] - u[0] * v[2],
                      u[0] * v[1] - u[1] * v[0])
        L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        out += struct.pack("<3f", nx / L, ny / L, nz / L)
        for p in (a, b, c):
            out += struct.pack("<3f", *p)
        out += b"\0\0"
    Path(path).write_bytes(bytes(out))


def move(tris):
    AX = axes()
    moved = set()

    def fix(v):
        for ax, az in AX:
            if math.hypot(v[0] - ax, v[2] - az) < CATCH_R:
                moved.add((round(v[0], 3), round(v[1], 3), round(v[2], 3)))
                return (v[0] + SHIFT, v[1], v[2])
        return v

    return [[fix(v) for v in t] for t in tris], moved


def main():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    tris = read_binary_stl(SRC)
    out, moved = move(tris)
    print(f"{SRC.name}: {len(tris)} triangles")
    print(f"pilot axes, old -> new:")
    for ax, az in axes():
        print(f"   ({ax:6.1f}, {az:5.1f})  ->  ({ax + SHIFT:6.1f}, {az:5.1f})")
    print(f"moved {len(moved)} distinct vertices by {SHIFT:+.1f} mm in x "
          f"(expect 4 x 73 = 292)")
    write_binary_stl(DST, out)
    print(f"-> {DST.name}  ({DST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
