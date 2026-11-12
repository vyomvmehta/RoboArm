"""Build the four-bar arm links in SolidWorks from Python (D19, 2026-11-11, Vyom + Claude).

Parts (SolidWorks Parts/):  Upper Arm, Crank, Rod, Forearm, Wrist Bracket  (+ Arm.SLDASM)
Run with SolidWorks free (it opens parts in SolidWorks):   py tools/cad/build_arm.py

HOW THE FOUR-BAR WORKS (D14)
  Both MG996Rs sit in the shoulder bracket on ONE axis O. The shoulder servo turns the upper
  arm O->E. The elbow servo turns a short CRANK O->C. A ROD C->L, as long as the upper arm, runs
  to a LEVER E->L on the forearm, as long as the crank. O-E-L-C is a parallelogram, so the lever
  stays parallel to the crank: the elbow servo sets the forearm's angle RELATIVE TO THE TABLE.
  The lever points backwards from E, so  forearm angle = crank angle + 180 deg.

FRAMES
  Each link is modelled lying along +X in its own frame, pivots on the X axis, so the assembly
  only has to rotate it about Z and move it. Z is the shoulder axis direction; Z = 0 is the
  middle of the shoulder bracket. Every link lives in its own Z LAYER, so links can never hit
  each other however the arm moves (they only meet at the pins):

     z  +22 ........ inner face of the shoulder servo's tower
        +9  ........ top face of the shoulder servo's aluminium horn (13 below the tab face)
     +3 .. +9        UPPER ARM   (6)   bolted to the shoulder horn; elbow boss 1..9 for the 608
     -3 .. +2        ROD         (5)
     -9 .. -4        CRANK       (5)   bolted to the elbow horn
     -9 .. -4        FOREARM     (5)   same layer as the crank: they never get near each other
        -9  ........ top face of the elbow servo's horn
        -22 ........ inner face of the elbow servo's tower
  => the tower inner faces must be 44 apart (was 39 before the rod layer was counted): the
     shoulder bracket's Plane1 offset goes 19.5 -> 22.

All numbers mm. D15 clearances: M3 hole 3.45, M3 nut 5.6 AF x 4.2 deep, 608 seat 22.0 (press),
MG90S pocket 11.9 x 22.8, MG90S tab holes 27.5 apart (Ø1.8 self-tapping M2).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pythoncom
import win32com.client as w

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_gripper as g  # noqa: E402  (Part helpers, OUT, MM, NOTHING)

# ----------------------------------------------------------------------------- parameters
L1 = 130.0          # upper arm, shoulder axis O -> elbow axis E      (arm.yaml l1, D14)
L2 = 120.0          # forearm, elbow axis E -> wrist axis W            (arm.yaml l2)
CRANK = 30.0        # crank O->C = lever E->L (parallelogram). 30 so the pin clears the horn
                    # screw at 20 mm (25 left only 1.5 mm of plastic between the holes)
M3, M3_HEAD_D, M3_HEAD_H = 3.45, 5.8, 2.2   # clearance hole, counterbore for the screw head
M8 = 8.0            # elbow bolt hole in the forearm boss (prints ~7.8, bolt threads in snug)
B608_D, B608_H = 22.0, 7.0                  # 608 bearing: seat (D15 press fit) and width
LIP_D = 16.0        # lip under the bearing: supports the outer race, clears the inner race
HORN_SCREWS = (8.0, 20.0)                   # aluminium horn holes used (D15: 8 / 20 / 29)
HORN_CENTRE = 6.5   # access hole for the horn's own centre screw

# Z layers (see the docstring)
UA_Z = (3.0, 9.0)
UA_BOSS_Z = (1.0, 9.0)
ROD_Z = (-3.0, 2.0)
LOW_Z = (-9.0, -4.0)                 # crank and forearm
FA_BOSS_Z = (-9.0, 2.0)              # forearm boss reaches up through the UA lip to the 608

# Wrist: MG90S in the forearm end, shaft pointing -Z; tabs on the forearm's bottom face.
MG90S_W, MG90S_L, MG90S_SHAFT = 11.9, 22.8, 5.6
MG90S_TABS, M2_PILOT = 27.5, 1.8
WRIST_HORN_TOP = LOW_Z[0] - 14.0     # tab underside -> top of the fitted horn = 14 (measured)
HORN_PILOT_R = (6.0, 17.0)           # MG90S horn holes (measured)
BRACKET_REACH = 20.0                 # wrist axis -> back face of the gripper's mount posts
GRIPPER_POSTS = (-31.0, 6.0)         # gripper frame: posts at x = -31, y = +-6 (build_gripper)
GRIPPER_MOUNT_Z = -19.0              # gripper frame: underside of the posts
# Wrist axis -> gripper origin (its servo shaft at its deck) = 20 + 19 = 39; grasp point is
# ~36.5 further (middle of the jaws) -> L3 = 75.5 => arm.yaml l3 70 -> 75.
GRIPPER_ORIGIN = BRACKET_REACH - GRIPPER_MOUNT_Z


# ----------------------------------------------------------------------------- shapes
def link(p: g.Part, x0, x1, width, r0, r1, z):
    """A straight link from x0 to x1 with round ends of radius r0 / r1, layer z=(lo, hi)."""
    p.boss(lambda s: s.rect(x0, -width / 2, x1, width / 2), z[0], z[1] - z[0])
    p.boss(lambda s: s.circle(x0, 0, 2 * r0), z[0], z[1] - z[0])
    p.boss(lambda s: s.circle(x1, 0, 2 * r1), z[0], z[1] - z[0])


def counterbore(p: g.Part, x, y, face_z, from_top: bool):
    """Recess for an M3 screw head so it sits flush (keeps heads out of the next layer)."""
    z0 = face_z - M3_HEAD_H if from_top else face_z
    p.cut(lambda s: s.circle(x, y, M3_HEAD_D), z0, M3_HEAD_H)


# ----------------------------------------------------------------------------- parts
def build_upper_arm(sw):
    """O at x=0 on the shoulder horn, E at x=L1 with a 608 bearing."""
    p = g.Part(sw, "Upper Arm")
    link(p, 0, L1, 16, 12, 14, UA_Z)
    p.boss(lambda s: s.circle(L1, 0, 28), UA_BOSS_Z[0], UA_BOSS_Z[1] - UA_BOSS_Z[0])
    # Shoulder end: horn screws along the arm (the horn's arm points at the elbow).
    p.cut(lambda s: s.circle(0, 0, HORN_CENTRE))
    p.cut(lambda s: [s.circle(r, 0, M3) for r in HORN_SCREWS])
    for r in HORN_SCREWS:                        # heads on the rod side, recessed
        counterbore(p, r, 0, UA_Z[0], from_top=False)
    # Elbow: 608 pressed in from the top (z 2..9), 1 mm lip below supports the outer race.
    p.cut(lambda s: s.circle(L1, 0, B608_D), UA_BOSS_Z[1] - B608_H, B608_H)
    p.cut(lambda s: s.circle(L1, 0, LIP_D))
    return p.finish()


def build_crank(sw):
    """O at x=0 on the elbow horn, C at x=CRANK: the rod's pin."""
    p = g.Part(sw, "Crank")
    link(p, 0, CRANK, 12, 9, 6.5, LOW_Z)
    p.cut(lambda s: s.circle(0, 0, HORN_CENTRE))
    p.cut(lambda s: [s.circle(r, 0, M3) for r in HORN_SCREWS] + [s.circle(CRANK, 0, M3)])
    for r in HORN_SCREWS:                        # horn screws: heads on top, recessed
        counterbore(p, r, 0, LOW_Z[1], from_top=True)
    counterbore(p, CRANK, 0, LOW_Z[0], from_top=False)  # pin screw head underneath (on the horn)
    return p.finish()


def build_rod(sw):
    """C at x=0, L at x=L1 (same length as the upper arm: parallelogram)."""
    p = g.Part(sw, "Rod")
    link(p, 0, L1, 10, 6.5, 6.5, ROD_Z)
    p.cut(lambda s: (s.circle(0, 0, M3), s.circle(L1, 0, M3)))
    counterbore(p, L1, 0, ROD_Z[1], from_top=True)      # L pin: head on top, nut under the lever
    return p.finish()


def build_forearm(sw):
    """E at x=0 (elbow bolt), L at x=-CRANK (lever, behind the elbow), W at x=L2 (wrist)."""
    p = g.Part(sw, "Forearm")
    end = L2 + MG90S_SHAFT + 2.35 + 2.5          # past the far tab hole with 2.5 of wall
    link(p, -CRANK, end, 16, 6.5, 8, LOW_Z)
    p.boss(lambda s: s.circle(0, 0, 14), FA_BOSS_Z[0], FA_BOSS_Z[1] - FA_BOSS_Z[0])
    p.cut(lambda s: s.circle(0, 0, M8))
    p.cut(lambda s: s.circle(-CRANK, 0, M3))
    # MG90S: shaft on W, body running back along the forearm, inserted from below.
    x0, x1 = L2 - (MG90S_L - MG90S_SHAFT), L2 + MG90S_SHAFT
    xc = (x0 + x1) / 2
    p.cut(lambda s: s.rect(x0, -MG90S_W / 2, x1, MG90S_W / 2))
    p.cut(lambda s: (s.circle(xc - MG90S_TABS / 2, 0, M2_PILOT),
                     s.circle(xc + MG90S_TABS / 2, 0, M2_PILOT)))
    return p.finish()


def build_wrist_bracket(sw, side):
    """W at the origin. A disc screwed to the wrist servo's horn (below it, z -26..-23) and a
    plate across the approach direction (+X) that the gripper's two M3 posts bolt to."""
    p = g.Part(sw, "Wrist Bracket")
    z_top = WRIST_HORN_TOP                              # -23
    z_bot = z_top - 3.0
    plate_x0, plate_x1 = BRACKET_REACH - 3.0, BRACKET_REACH
    px, py = GRIPPER_POSTS                               # gripper frame
    # Disc on the horn, then a web out to the plate, then the plate up to the posts' height.
    p.boss(lambda s: s.circle(0, 0, 40), z_bot, 3.0)
    p.boss(lambda s: s.rect(0, px - 9, plate_x1, 9), z_bot, 3.0)
    p.boss(lambda s: s.rect(plate_x0, px - 9, plate_x1, 9), z_bot, (py + 6) - z_bot)
    # Horn: centre screw access + self-tapping pilots at the measured hole radii, horn arm
    # along the bracket's Y axis (clear of the plate).
    p.cut(lambda s: [s.circle(0, 0, 5.5)] +
          [s.circle(0, sgn * r, 1.6) for r in HORN_PILOT_R for sgn in (1, -1)])
    # Gripper posts: 2x M3 through the plate along X, at gripper (x=-31, y=+-6), which is
    # (bracket y = -31, z = +-6) because gripper Y lies along the wrist axis.
    side(p, [(px, +py), (px, -py)], M3)
    return p.finish()


# ----------------------------------------------------------------------------- side-plane holes
def probe_right_plane(sw):
    """Find how the Right Plane's sketch axes map onto the model axes (one tiny test part)."""
    p = g.Part(sw, "_probe")
    p.doc.Extension.SelectByID2("Right Plane", "PLANE", 0, 0, 0, False, 0, g.NOTHING, 0)
    p.skm.InsertSketch(True)
    p.skm.AddToDB = True
    p.skm.CreateCircleByRadius(0.010, 0.020, 0, 0.001)    # sketch (10, 20)
    p.skm.AddToDB = False
    p.skm.InsertSketch(True)
    name = p.doc.FeatureByPositionReverse(0).Name
    p.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, g.NOTHING, 0)
    p.fm.FeatureExtrusion3(True, False, False, 0, 0, 0.001, 0, False, False, False, False, 0, 0,
                           False, False, False, False, True, True, True, 0, 0, False)
    box = p.doc.GetBodies2(0, True)[0].GetBodyBox
    centre = [round((box[i] + box[i + 3]) / 2 * 1000) for i in range(3)]   # mm
    sw.CloseDoc(p.doc.GetTitle)
    sx = ("y" if abs(centre[1]) == 10 else "z", 1 if 10 in centre else -1)
    sy = ("y" if abs(centre[1]) == 20 else "z", 1 if 20 in centre else -1)
    print("Right Plane sketch axes ->", sx, sy, "(centre seen at", centre, ")")
    return centre


def make_side_holes(centre):
    """Return side(p, [(y, z), ...], d): through-holes along X at model (y, z)."""
    def to_sketch(y, z):
        # Probe drew sketch (10, 20); centre tells where that landed in model (x, y, z).
        sx = sy = None
        for val, axis in ((centre[1], "y"), (centre[2], "z")):
            if abs(val) == 10:
                sx = (axis, val // 10)
            if abs(val) == 20:
                sy = (axis, val // 20)
        model = {"y": y, "z": z}
        return model[sx[0]] * sx[1], model[sy[0]] * sy[1]

    def side(p, pts, d):
        p.doc.ClearSelection2(True)
        p.doc.Extension.SelectByID2("Right Plane", "PLANE", 0, 0, 0, False, 0, g.NOTHING, 0)
        p.skm.InsertSketch(True)
        p.skm.AddToDB = True
        for y, z in pts:
            u, v = to_sketch(y, z)
            p.skm.CreateCircleByRadius(u * g.MM, v * g.MM, 0, d / 2 * g.MM)
        p.skm.AddToDB = False
        p.skm.InsertSketch(True)
        name = p.doc.FeatureByPositionReverse(0).Name
        p.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, g.NOTHING, 0)
        f = p.fm.FeatureCut4(False, False, False, 1, 1, 0, 0, False, False, False, False, 0, 0,
                             False, False, False, False, False, True, True, True, True, False,
                             0, 0, False, False)
        if f is None:
            raise RuntimeError("side holes failed")
    return side


# ----------------------------------------------------------------------------- assembly + poses
def pose_transforms(theta1, phi_f, theta3):
    """World poses (rotation about Z in degrees, x, y) of each link for joint angles:
    theta1 = upper arm, phi_f = forearm absolute angle, theta3 = wrist relative to forearm."""
    t1, pf = math.radians(theta1), math.radians(phi_f)
    psi = pf + math.pi                            # crank angle (lever points back from E)
    E = (L1 * math.cos(t1), L1 * math.sin(t1))
    C = (CRANK * math.cos(psi), CRANK * math.sin(psi))
    W = (E[0] + L2 * math.cos(pf), E[1] + L2 * math.sin(pf))
    return {
        "Upper Arm": (theta1, 0.0, 0.0),
        "Crank": (math.degrees(psi), 0.0, 0.0),
        "Rod": (theta1, *C),
        "Forearm": (phi_f, *E),
        "Wrist Bracket": (phi_f + theta3, *W),
    }


def gripper_transform(phi_f, theta3, W):
    """Gripper frame -> world: gripper Z = approach d, gripper Y = world Z (wrist axis),
    gripper X = world Z x d. Origin on the approach line, GRIPPER_ORIGIN from the wrist axis."""
    a = math.radians(phi_f + theta3)
    d = (math.cos(a), math.sin(a), 0.0)
    xg = (-d[1], d[0], 0.0)
    yg = (0.0, 0.0, 1.0)
    o = (W[0] + GRIPPER_ORIGIN * d[0], W[1] + GRIPPER_ORIGIN * d[1], 0.0)
    return xg, yg, d, o


def build_assembly(sw, parts, bracket_path, gripper_asm, poses):
    from win32com.client import gencache
    tlb = gencache.EnsureModule("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
    mu = tlb.ISldWorks(sw._oleobj_).GetMathUtility()
    mu = tlb.IMathUtility(getattr(mu, "_oleobj_", mu))
    arr = lambda a: w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in a])

    def xform(rx, ry, rz, o):
        # MathTransform array: 3 rows = where the part's X, Y, Z axes point in the assembly,
        # then the translation (m), then the scale. check_axes() proves it at run time.
        return mu.CreateTransform(arr([*rx, *ry, *rz, o[0] / 1000, o[1] / 1000, o[2] / 1000,
                                       1, 0, 0, 0]))

    def zrot(deg, x, y, z=0.0):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return xform((c, s, 0), (-s, c, 0), (0, 0, 1), (x, y, z))

    doc = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    asm = tlb.IAssemblyDoc(doc._oleobj_)
    comps = {}
    for name, path in [("Shoulder Bracket", bracket_path), *parts.items(),
                       ("Gripper", gripper_asm)]:
        c = doc.AddComponent5(str(path), 0, "", False, "", 0, 0, 0)
        if c is None:
            raise RuntimeError(f"could not insert {path}")
        comps[name] = tlb.IComponent2(c._oleobj_)

    # Bracket: its shaft axis is at (0, 47.5) in its own frame -> put it on the world origin.
    comps["Shoulder Bracket"].Transform2 = zrot(0, 0, -47.5)

    def set_pose(theta1, phi_f, theta3):
        tf = pose_transforms(theta1, phi_f, theta3)
        for name, (deg, x, y) in tf.items():
            comps[name].Transform2 = zrot(deg, x, y)
        W = tf["Wrist Bracket"][1:]
        xg, yg, zg, o = gripper_transform(phi_f, theta3, W)
        comps["Gripper"].Transform2 = xform(xg, yg, zg, o)
        doc.ForceRebuild3(False)

    def check_axes():
        """Upper arm at 90 deg must point along +Y: proves the transform convention."""
        set_pose(90, 0, 0)
        box = comps["Upper Arm"].GetBox(False, False)
        ymax, xmax = box[4] * 1000, box[3] * 1000
        if not (ymax > L1 and xmax < 20):
            raise RuntimeError(f"transform convention wrong: upper arm box {box}")

    def interference():
        idm = asm.InterferenceDetectionManager
        idm.TreatCoincidenceAsInterference = False
        found = []
        for r in idm.GetInterferences() or []:
            r = tlb.IInterference(r._oleobj_)
            names = sorted(tlb.IComponent2(c._oleobj_).Name2 for c in r.Components)
            found.append((names, round(r.Volume * 1e9, 1)))
        idm.Done()
        return found

    check_axes()
    report = []
    for label, (t1, pf, t3) in poses.items():
        set_pose(t1, pf, t3)
        report.append((label, (t1, pf, t3), interference()))
    first = next(iter(poses.values()))
    set_pose(*first)
    doc.ShowNamedView2("*Isometric", 7)
    doc.ViewZoomtofit2()
    path = g.OUT / "Arm.SLDASM"
    doc.SaveAs(str(path))
    return path, report


def poses_from_ik():
    """Real poses from the project's own IK: home, reaching far, close in, picking low."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from arm.config import load_arm
    from arm.kinematics import ik
    cfg = load_arm()
    out = {}
    for label, (r, z, pitch) in {"home": (150, 80, -90), "far": (230, 15, -90),
                                 "near": (105, 15, -90), "high": (150, 200, 0)}.items():
        a = ik(cfg.geometry, r, 0, z, math.radians(pitch), limits=cfg.limits)
        t1, t2, t3 = (math.degrees(v) for v in (a.theta1, a.theta2, a.theta3))
        out[label] = (t1, t1 + t2, t3)            # forearm absolute = theta1 + theta2
    park = cfg.park
    out["park"] = tuple(math.degrees(v) for v in (park.theta1, park.theta1 + park.theta2,
                                                   park.theta3))
    return out


def widen_shoulder_bracket(sw, gap=44.0):
    """The rod needs its own layer, so the towers move from 39 to 44 mm apart (Plane1 22)."""
    path = str(g.OUT / "Shoulder Bracket.SLDPRT")
    doc = sw.GetOpenDocumentByName(path) or sw.OpenDoc(path, 1)
    if doc is None:
        raise RuntimeError("could not open the shoulder bracket")
    p = doc.Parameter("D1@Plane1")
    if abs(p.SystemValue * 1000 - gap / 2) > 1e-6:
        p.SystemValue = gap / 2 / 1000
        doc.ForceRebuild3(False)
        doc.SaveAs(doc.GetPathName)
    print(f"shoulder bracket: towers {gap} apart (Plane1 = {p.SystemValue * 1000:.1f})")


def main():
    sw = w.Dispatch("SldWorks.Application")
    sw.Visible = True
    for title in ("Arm", "Upper Arm", "Crank", "Rod", "Forearm", "Wrist Bracket", "_probe"):
        sw.CloseDoc(title)                         # only our own files, never other work
    side = make_side_holes(probe_right_plane(sw))
    parts, mass = {}, {}
    for name, build in (("Upper Arm", build_upper_arm), ("Crank", build_crank),
                        ("Rod", build_rod), ("Forearm", build_forearm)):
        path, vol = build(sw)
        parts[name], mass[name] = path, vol * 1.24
    path, vol = build_wrist_bracket(sw, side)
    parts["Wrist Bracket"], mass["Wrist Bracket"] = path, vol * 1.24
    for n, m in mass.items():
        print(f"{n:14s} {m:5.1f} g solid PLA")
    print(f"{'links total':14s} {sum(mass.values()):5.1f} g")
    widen_shoulder_bracket(sw)
    poses = poses_from_ik()
    asm, report = build_assembly(sw, parts, g.OUT / "Shoulder Bracket.SLDPRT",
                                 g.OUT / "Gripper.SLDASM", poses)
    for label, angles, found in report:
        print(f"pose {label:5s} (upper arm, forearm abs, wrist) = "
              f"{tuple(round(a) for a in angles)}: {len(found)} interference(s) {found}")
    print("assembly:", asm)


if __name__ == "__main__":
    sys.exit(main())
