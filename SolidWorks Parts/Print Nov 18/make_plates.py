"""Build UltiMaker S5 build plates as 3MF files (one object per part, laid flat at z = 0, arranged
inside the 330 x 240 bed with gaps). Open in Cura, Slice with the S5 profile, then print."""
import struct
import sys
import zipfile
from pathlib import Path

BED_X, BED_Y, GAP = 320.0, 230.0, 15.0          # S5 bed 330 x 240, keep a 5 mm edge


def read(p):
    b = Path(p).read_bytes()
    if b[:5].lower() == b"solid" and b"facet" in b[:400]:
        tris, vs = [], []
        for line in b.decode(errors="ignore").splitlines():
            t = line.split()
            if t[:1] == ["vertex"]:
                vs.append(tuple(map(float, t[1:4])))
                if len(vs) == 3:
                    tris.append(vs)
                    vs = []
        return tris
    n = struct.unpack_from("<I", b, 80)[0]
    return [[struct.unpack_from("<3f", b, 84 + i * 50 + 12 + k * 12) for k in range(3)] for i in range(n)]


def on_side(t):      # biggest flat face is at min x: put it on the bed (finger plates: back down, grooves up)
    return [[(-v[2], v[1], v[0]) for v in tri] for tri in t]


def flip(t):         # biggest flat face is at max z (lid / outer face): turn it over onto the bed
    return [[(v[0], -v[1], -v[2]) for v in tri] for tri in t]


def flat_screw_strip(t):
    return [[(v[0], v[2], -v[1]) for v in tri] for tri in t]


def plate(out, items):
    """items: list of (name, stl_path, copies, transform-or-None)."""
    parts = []
    for name, path, copies, fix in items:
        t = read(path)
        if fix:
            t = fix(t)
        for k in range(copies):
            parts.append((name if copies == 1 else f"{name} {k + 1}", t))
    x = y = row_h = 0.0
    objs = []
    for name, t in parts:
        xs = [v[0] for tri in t for v in tri]
        ys = [v[1] for tri in t for v in tri]
        zs = [v[2] for tri in t for v in tri]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if x > 0 and x + w > BED_X:
            x, y, row_h = 0.0, y + row_h + GAP, 0.0
        dx, dy, dz = x - min(xs), y - min(ys), -min(zs)
        objs.append((name, [[(v[0] + dx, v[1] + dy, v[2] + dz) for v in tri] for tri in t]))
        print(f"   {name:22s} {w:6.1f} x {h:6.1f} x {max(zs) - min(zs):5.1f} mm")
        x += w + GAP
        row_h = max(row_h, h)
    total_y = y + row_h
    if total_y > BED_Y:
        raise SystemExit(f"{out}: {total_y:.0f} mm deep, does not fit the bed")
    # centre the layout on the bed
    allx = [v[0] for _, t in objs for tri in t for v in tri]
    cx, cy = -max(allx) / 2, -total_y / 2          # Cura puts the 3MF origin at the bed centre
    model = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
             '<resources>']
    places = []
    for i, (name, t) in enumerate(objs, 1):
        # Mesh stored around its own centre; the position goes in the build item's transform
        # (Cura re-centres raw object meshes, which made parts overlap).
        xs = [v[0] for tri in t for v in tri]
        ys = [v[1] for tri in t for v in tri]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        places.append((mx + cx, my + cy))
        verts, idx, tri_rows = {}, [], []
        for tri in t:
            ids = []
            for v in tri:
                key = (round(v[0] - mx, 4), round(v[1] - my, 4), round(v[2], 4))
                if key not in verts:
                    verts[key] = len(verts)
                ids.append(verts[key])
            if len(set(ids)) == 3:
                tri_rows.append(ids)
        model.append(f'<object id="{i}" name="{name}" type="model"><mesh><vertices>')
        model += [f'<vertex x="{a}" y="{b}" z="{c}"/>' for (a, b, c) in verts]
        model.append('</vertices><triangles>')
        model += [f'<triangle v1="{p}" v2="{q}" v3="{r}"/>' for p, q, r in tri_rows]
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
    print(f"-> {Path(out).name}: {len(objs)} parts, layout {max(allx):.0f} x {total_y:.0f} mm")


def main():
  root = Path(sys.argv[1])          # Print Nov 18
  H = Path(sys.argv[2])             # STL/Arm Human
  TP = root / "0 - Prusa 2 fit test (print first)"
  out = root / "UltiMaker plates (open in Cura)"
  out.mkdir(exist_ok=True)
  plates = {
    "Plate 1 - fit test (print first).3mf": [
        ("MG996R frames", TP / "mg996r_frames.stl", 1, None), ("MG90S frames", TP / "mg90s_frames.stl", 1, None),
        ("Bearing block", TP / "bearing_block.stl", 1, None), ("Screw strip", TP / "Screw_Strip.STL", 1, flat_screw_strip)],
    "Plate 2 - loose-fit parts.3mf": [
        (n, H / f"{n}.STL", 1, on_side if n.startswith("Gripper") else None)
        for n in ("Rod", "Crank", "Elbow Spacer", "Gripper Fingers", "Gripper Thumb", "Wrist Cap")],
    "Plate 3 - covers.3mf": [
        ("Shoulder Cap", H / "Shoulder Cap.STL", 2, flip), ("Palm Cover", H / "Palm Cover.STL", 1, flip),
        ("Wrist Cuff", H / "Wrist Cuff.STL", 1, None)],
    "Plate 4 - skins.3mf": [
        ("Upper Arm Skin", H / "Upper Arm Skin.STL", 1, None), ("Forearm Skin", H / "Forearm Skin.STL", 1, None)],
  }
  for name, items in plates.items():
      print(name)
      plate(out / name, items)


if __name__ == "__main__":
    main()
