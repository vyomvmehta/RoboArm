"""Pack every unprinted part onto as few S5 plates as possible.

make_plates.plate() lays parts out in simple rows, which wastes the strip beside a big square
part - the 200 mm base plate leaves a 105 x 230 column that rows cannot reach. This uses a
free-rectangle guillotine packer with 90-degree rotation instead, and first-fit-decreasing
across plates, so a part only opens a new plate when it fits in no existing one.

Gaps: each part's footprint is inflated by GAP and the bed by GAP, so every part keeps a GAP
margin from its neighbours on the right and above, and from the bed edge.
"""
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = ["make_plates.py", ".", "."]
import make_plates as mp  # noqa: E402

BED_X, BED_Y, GAP = mp.BED_X, mp.BED_Y, mp.GAP
HERE = Path(__file__).resolve().parent              # SolidWorks Parts/Print Nov 18
REPO = HERE.parent                                  # SolidWorks Parts
STL, HUM = REPO / "STL", REPO / "STL/Arm Human"


def rot90(t):
    return [[(-v[1], v[0], v[2]) for v in tri] for tri in t]


def bbox(t):
    xs = [v[0] for tri in t for v in tri]
    ys = [v[1] for tri in t for v in tri]
    zs = [v[2] for tri in t for v in tri]
    return min(xs), min(ys), min(zs), max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


class Plate:
    def __init__(self):
        self.free = [(0.0, 0.0, BED_X + GAP, BED_Y + GAP)]
        self.placed = []

    def put(self, name, t):
        _, _, _, w, h, _ = bbox(t)
        best = None
        for cand, (cw, ch) in ((t, (w, h)), (rot90(t), (h, w))):
            iw, ih = cw + GAP, ch + GAP
            for i, (rx, ry, rw, rh) in enumerate(self.free):
                if iw <= rw + 1e-9 and ih <= rh + 1e-9:
                    waste = rw * rh - iw * ih
                    if best is None or waste < best[0]:
                        best = (waste, i, rx, ry, iw, ih, cand)
        if best is None:
            return False
        _, i, rx, ry, iw, ih, cand = best
        rx0, ry0, rw, rh = self.free.pop(i)
        for r in ((rx0 + iw, ry0, rw - iw, ih), (rx0, ry0 + ih, rw, rh - ih)):
            if r[2] > 1e-6 and r[3] > 1e-6:
                self.free.append(r)
        mnx, mny, mnz, w2, h2, z2 = bbox(cand)
        self.placed.append((name, [[(v[0] - mnx + rx, v[1] - mny + ry, v[2] - mnz) for v in tri]
                                   for tri in cand], w2, h2, z2))
        return True

    def extent(self):
        xs = [v[0] for _, t, *_ in self.placed for tri in t for v in tri]
        ys = [v[1] for _, t, *_ in self.placed for tri in t for v in tri]
        zs = [v[2] for _, t, *_ in self.placed for tri in t for v in tri]
        return max(xs), max(ys), max(zs)


def write_3mf(out, placed):
    allx = [v[0] for _, t, *_ in placed for tri in t for v in tri]
    ally = [v[1] for _, t, *_ in placed for tri in t for v in tri]
    cx, cy = -max(allx) / 2, -max(ally) / 2
    model = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">', '<resources>']
    places = []
    for i, (name, t, *_) in enumerate(placed, 1):
        xs = [v[0] for tri in t for v in tri]
        ys = [v[1] for tri in t for v in tri]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        places.append((mx + cx, my + cy))
        verts, rows = {}, []
        for tri in t:
            ids = []
            for v in tri:
                key = (round(v[0] - mx, 4), round(v[1] - my, 4), round(v[2], 4))
                if key not in verts:
                    verts[key] = len(verts)
                ids.append(verts[key])
            if len(set(ids)) == 3:
                rows.append(ids)
        model.append(f'<object id="{i}" name="{name}" type="model"><mesh><vertices>')
        model += [f'<vertex x="{a}" y="{b}" z="{c}"/>' for (a, b, c) in verts]
        model.append('</vertices><triangles>')
        model += [f'<triangle v1="{p}" v2="{q}" v3="{r}"/>' for p, q, r in rows]
        model.append('</triangles></mesh></object>')
    model.append('</resources><build>')
    model += [f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {px:.4f} {py:.4f} 0"/>'
              for i, (px, py) in enumerate(places, 1)]
    model.append('</build></model>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", "\n".join(model))


def write_stl(out, placed):
    tris = [tri for _, t, *_ in placed for tri in t]
    with open(out, "wb") as f:
        f.write(b"RoboArm plate".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for tri in tris:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for v in tri:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))
    return len(tris)


# Everything not yet printed. Orientation from the measured flat-face areas (see D25 / README).
ITEMS = [
    ("Base plate",   STL / "grap_base.stl",         1, None),
    ("Lid",          STL / "grap_lid.stl",          1, mp.flip),
    ("Servo bridge", STL / "grap_servo_bridge.stl", 1, mp.flip),
    ("Planet gear",  STL / "grap_planet_gear.stl",  1, None),
    ("Wheel fork",   STL / "grap_wheel_fork.stl",   4, mp.flip),
    ("Sun gear",     STL / "grap_sun_gear.stl",     1, mp.flip),
    ("Elbow spacer", HUM / "Elbow Spacer.STL",      3, None),
]

parts = []
for name, path, copies, fix in ITEMS:
    t = mp.read(path)
    if fix:
        t = fix(t)
    for k in range(copies):
        parts.append((name if copies == 1 else f"{name} {k+1}", t))

# first-fit-decreasing: biggest footprint first, so the big squares define the plates
parts.sort(key=lambda p: -(bbox(p[1])[3] * bbox(p[1])[4]))
plates = []
for name, t in parts:
    if not any(pl.put(name, t) for pl in plates):
        pl = Plate()
        if not pl.put(name, t):
            raise SystemExit(f"{name} does not fit an empty bed")
        plates.append(pl)

print(f"{len(parts)} parts -> {len(plates)} plate(s)\n")
for n, pl in enumerate(plates, 1):
    ex, ey, ez = pl.extent()
    print(f"PLATE {n}: {len(pl.placed)} parts, layout {ex:.0f} x {ey:.0f} mm, tallest {ez:.1f} mm"
          f"   (bed {BED_X:.0f} x {BED_Y:.0f})")
    assert ex <= BED_X + 1e-6 and ey <= BED_Y + 1e-6, "off the bed"
    for name, t, w, h, z in pl.placed:
        xs = [v[0] for tri in t for v in tri]
        ys = [v[1] for tri in t for v in tri]
        print(f"    {name:16s} {w:6.1f} x {h:6.1f} x {z:5.1f}   at ({min(xs):6.1f}, {min(ys):6.1f})")
    print()

OUT = HERE / "UltiMaker plates (open in Cura)"
NAMES = ["Plate 11 - base plate + bridge + planet + fork + spacers (packed, Nov 22)",
         "Plate 12 - lid + 3 forks + sun gear (packed, Nov 22)"]
assert len(plates) == len(NAMES), f"{len(plates)} plates but {len(NAMES)} names"
for pl, nm in zip(plates, NAMES):
    write_3mf(OUT / f"{nm}.3mf", pl.placed)
    n = write_stl(OUT / f"{nm}.stl", pl.placed)
    a = (OUT / f"{nm}.3mf").stat().st_size // 1024
    b = (OUT / f"{nm}.stl").stat().st_size // 1024
    print(f"-> {nm}\n     .3mf {a} KB   .stl {b} KB ({n} triangles)")

# Volume of each plate, by the divergence theorem, so we can report print size honestly.
def vol(t):
    s = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in t:
        s += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
    return abs(s) / 1000.0
print()
for pl, nm in zip(plates, NAMES):
    v = sum(vol(t) for _, t, *_ in pl.placed)
    print(f"{nm.split(' - ')[0]}: {v:7.1f} cm3 of plastic, tallest {pl.extent()[2]:.1f} mm")
