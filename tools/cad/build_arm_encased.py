"""Encased arm: the same four-bar arm wearing thin shells that hide every servo and wire
(Vyom asked 2026-11-13; Claude built by script). Output: SolidWorks Parts/Arm Encased/

Run with SolidWorks free:   py tools/cad/build_arm_encased.py
Needs build_arm.py's parts to exist first (it reuses Rod, Elbow Spacer, Wrist Bracket and the
gripper from ../Arm and ../Gripper, and regenerates Upper Arm / Crank / Forearm from build_arm's
own functions with a few extra features, so the mechanism stays defined in ONE place).

WHAT CHANGES vs Arm/ (the mechanism, IK and calibration are untouched)
  Shoulder Bracket  copy of Vyom's part + one Ø6 cable hole through the shoulder-side tower
  Upper Arm         + 2 heat-set insert holes (Ø4.0 x 4) in the top face for the shell
  Crank             + a Ø84 drum ring and 2 spokes: rotates with the crank, hides the elbow servo
  Forearm           + 2 heat-set insert holes in the bottom face for the shell
  Shoulder Cap (x2) fixed covers over each tower + MG996R body (open underneath for cables)
  Upper Arm Shell   sleeve over the upper arm AND the rod's whole sweep, with a Ø84 drum that
                    hides the shoulder servo, and a dome over the elbow bolt
  Forearm Shell     trough under the forearm (cables) + housing over the wrist MG90S
  Hand Shell        box round the gripper's servo, plus a hood that reaches back over the
                    wrist axis so the gripper cable crosses the wrist ON the axis (twist only)

CABLE PATH (wrist + gripper servo leads)
  gripper servo -> Hand Shell -> hood -> down the wrist axis into the Forearm Shell
  wrist servo -> Forearm Shell; both run back in the trough under the forearm
  elbow: through a HOLLOW M8 bolt (Ø4.5-5 bore) in place of the plain M8 (pure twist)
  upper arm: inside the Upper Arm Shell, into its drum, a U-turn loop around the shoulder servo
  (the "clock spring": inner side fixed, outer side turns with the arm), out through the tower
  hole into the Shoulder Cap, down into the base. MG996R leads drop straight down inside the caps.

Z LAYERS added (see build_arm.py for the links' own layers; z = shoulder axis direction):
  +22.3..+53.2  Shoulder Cap (fixed, outside the tower)
   -3 .. +21    Upper Arm Shell walls/skin (top skin 19.8..21; elbow dome to 27.2)
  -21 .. -4     Crank drum ring (spokes -7..-4)
  -22.2..+10.2  Forearm Shell (top skin 9..10.2 near the wrist only; walls stop at -4.5 near
                the elbow, under the rod layer)
  world z 12.4..16.2 over the wrist: the Hand Shell's hood
All shells 1.2 mm walls. Masses printed for solid PLA; torque_encased.py also does LW-PLA.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import pythoncom
import win32com.client as w

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_arm as a  # noqa: E402
import build_gripper as g  # noqa: E402

ENC_DIR = g.OUT / "Arm Encased"
T = 1.2                          # wall thickness



# ----------------------------------------------------------------------------- 2D helpers
def circle_pts(cx, cy, r, n=40):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def hull(circles, extra=()):
    """Convex hull of circles [(cx, cy, r)] + extra points, as a CCW polygon."""
    pts = sorted({(round(x, 4), round(y, 4)) for c in circles for x, y in circle_pts(*c)}
                 | {(round(x, 4), round(y, 4)) for x, y in extra})

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-9:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-9:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def shrink(circles, t):
    return [(cx, cy, r - t) for cx, cy, r in circles]


def rrect(x0, y0, x1, y1, r):
    return hull([(x0 + r, y0 + r, r), (x1 - r, y0 + r, r), (x1 - r, y1 - r, r), (x0 + r, y1 - r, r)])


def spoke(angle_deg, r0, r1, width):
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    h = width / 2
    return [(r0 * c - h * -s, r0 * s - h * c), (r1 * c - h * -s, r1 * s - h * c),
            (r1 * c + h * -s, r1 * s + h * c), (r0 * c + h * -s, r0 * s + h * c)]


def side_cut_poly(p, pm, outline, mid, depth):
    """Mid-plane cut of a polygon drawn in a side plane's model axes (like g.Part.side_cut)."""
    p.doc.ClearSelection2(True)
    p.doc.Extension.SelectByID2(pm.plane, "PLANE", 0, 0, 0, False, 0, g.NOTHING, 0)
    p.skm.InsertSketch(True)
    p.skm.AddToDB = True
    uv = [pm.uv(x, y) for x, y in outline]
    for (u1, v1), (u2, v2) in zip(uv, uv[1:] + uv[:1]):
        p.skm.CreateLine(u1 * g.MM, v1 * g.MM, 0, u2 * g.MM, v2 * g.MM, 0)
    p.skm.AddToDB = False
    p.skm.InsertSketch(True)
    name = p.doc.FeatureByPositionReverse(0).Name
    p.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, g.NOTHING, 0)
    off = mid * pm.normal_sign
    f = p.fm.FeatureCut4(True, False, False, 6, 0, depth * g.MM, 0, False, False, False, False,
                         0, 0, False, False, False, False, False, True, True, True, True, False,
                         3, abs(off) * g.MM, off < 0, False)
    if f is None:
        raise RuntimeError(f"{p.name}: side poly cut failed")


# ----------------------------------------------------------------------------- shoulder
# World frame (the bracket's, moved so the shoulder axis O is the origin): x forward, y up.
TOWER = (-25.0, -45.0, 25.0, 21.0)        # tower footprint (x0, y0, x1, y1), z 22..29
TAB_HOLES = ((5.0, 14.35), (-5.0, -34.65))  # MG996R tab holes used to hold the cap (diagonal)
CABLE_HOLE = (-16.0, -33.4, 6.0)          # through the +z tower, inside the drum (r = 37)
CAP_Z = (22.3, 53.2)                      # servo body ends ~49 (tab at 22 + ~27)
CAP_R = 43.7                              # covers the drums (r 42) seen from the side


def shoulder_cap_outline(t=0.0):
    r, hw = CAP_R - t, 31.6 - t
    return hull([(0, 0, r)], extra=[(-hw, -50.0 - (2 if t else 0)), (hw, -50.0 - (2 if t else 0))])


def build_shoulder_cap(sw):
    p = g.Part(sw, "Shoulder Cap", folder=ENC_DIR)
    z0, z1 = CAP_Z
    p.boss(lambda s: s.poly(shoulder_cap_outline()), z0, z1 - z0)
    p.cut(lambda s: s.poly(shoulder_cap_outline(T)), z0, z1 - T - z0)       # open inner face + bottom
    # Inner flange covering the ring between the tower's sides and the cap wall.
    p.boss(lambda s: s.poly(shoulder_cap_outline(T)), z0, T)
    p.cut(lambda s: s.rect(TOWER[0] - 0.3, TOWER[1] - 8, TOWER[2] + 0.3, TOWER[3] + 0.3), z0 - 0.1, T + 0.2)
    p.cut(lambda s: s.rect(-30.3, -53.0, 30.3, -44.7), z0 - 0.1, T + 0.2)      # the base plate
    # Two bosses on tab-hole axes: the servo's own M3 (now x30) runs on through the cap to a nut.
    p.boss(lambda s: [s.circle(x, y, 7.0) for x, y in TAB_HOLES], 29.0, z1 - T - 29.0)
    p.cut(lambda s: [s.circle(x, y, g.M3_CLEAR) for x, y in TAB_HOLES])
    p.cut(lambda s: [s.hexagon(x, y, g.M3_NUT_AF) for x, y in TAB_HOLES], z1 - 6.0, 6.1)
    return p.finish()


def copy_shoulder_bracket(sw):
    """Vyom's bracket + a Ø6 cable hole through the shoulder-side tower (model y = world + 47.5)."""
    src, dst = a.ARM_DIR / "Shoulder Bracket.SLDPRT", ENC_DIR / "Shoulder Bracket.SLDPRT"
    ENC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    doc = sw.OpenDoc(str(dst), 1)
    p = g.Part.__new__(g.Part)
    p.sw, p.name, p.folder, p.doc = sw, "Shoulder Bracket", ENC_DIR, doc
    p.skm, p.fm = doc.SketchManager, doc.FeatureManager
    x, y, d = CABLE_HOLE
    p.cut(lambda s: s.circle(x, y + 47.5, d), 21.0, 9.0)
    doc.ForceRebuild3(False)
    doc.SaveAs(str(dst))
    mp = doc.GetMassProperties
    mp = mp() if callable(mp) else mp
    return dst, mp[3] * 1e6


# ----------------------------------------------------------------------------- upper arm
# Upper-arm frame: O at 0, E at (L1, 0). With the elbow bent (theta2 in -140..0) the rod lies
# on the +y side: C = 30 at (theta2 + 180) from O, L = C + (L1, 0). The shell must contain the
# rod's whole sweep, because its walls share the rod's z layer.
DRUM_R = 42.0
UA_TOP = (19.8, 21.0)                     # top skin; tower inner face at 22, MG996R tab at 19.5..22
UA_BOT = -3.0                             # walls stop at the rod's underside; crank/forearm at <= -4
UA_INSERTS = (50.0, 90.0)


def ua_circles():
    """Sleeve only (the drum is added separately): narrow (-16) on the -y side so that with the
    shoulder at -20 deg it stays clear of the bracket's base plate; +y side holds the rod."""
    cs = [(30.0, 0.0, 16.0), (a.L1, 0.0, 24.0)]
    for ang in range(40, 181, 10):            # the rod's C and L ends (Ø13 round ends + clearance)
        r = math.radians(ang)
        cs.append((a.CRANK * math.cos(r), a.CRANK * math.sin(r), 8.5))
        cs.append((a.L1 + a.CRANK * math.cos(r), a.CRANK * math.sin(r), 8.5))
    return cs


def build_upper_arm_shell(sw):
    p = g.Part(sw, "Upper Arm Shell", folder=ENC_DIR)
    cs = ua_circles()
    p.boss(lambda s: s.circle(0, 0, 2 * DRUM_R), UA_BOT, UA_TOP[1] - UA_BOT)
    p.boss(lambda s: s.poly(hull(cs)), UA_BOT, UA_TOP[1] - UA_BOT)
    p.cut(lambda s: s.poly(hull(shrink(cs, T))), UA_BOT, UA_TOP[0] - UA_BOT)
    p.cut(lambda s: s.circle(0, 0, 2 * (DRUM_R - T)))         # drum = ring only: no skin over the servo
    # Elbow dome over the (hollow) M8 bolt head: cable comes up out of the bolt, turns into the sleeve
    p.boss(lambda s: s.circle(a.L1, 0, 32.0), UA_TOP[1], 6.2)
    p.cut(lambda s: s.circle(a.L1, 0, 32.0 - 2 * T), UA_TOP[0], 6.2)
    # Standoffs down to the upper arm's top face (z 9), M3 into heat-set inserts
    p.boss(lambda s: [s.circle(x, 0, 7.0) for x in UA_INSERTS], a.UA_Z[1], UA_TOP[0] - a.UA_Z[1])
    p.cut(lambda s: [s.circle(x, 0, g.M3_CLEAR) for x in UA_INSERTS])
    return p.finish()


def extra_upper_arm(p):
    p.cut(lambda s: [s.circle(x, 0, 4.0) for x in UA_INSERTS], a.UA_Z[1] - 4.0, 4.0)


def extra_crank(p):
    """Drum ring that turns with the crank and hides the elbow servo + its horn."""
    p.boss(lambda s: (s.circle(0, 0, 2 * DRUM_R), s.circle(0, 0, 2 * (DRUM_R - 1.5))), -21.0, 17.0)
    p.boss(lambda s: [s.poly(spoke(ang, 7.0, DRUM_R - 0.5, 5.0)) for ang in (120, 240)], -7.0, 3.0)


# ----------------------------------------------------------------------------- forearm
# Forearm frame: E at 0, L (lever) at (-30, 0), W (wrist) at (L2, 0).
FA_INSERTS = (40.0, 75.0)
FA_LOW = [(-a.CRANK, 0.0, 11.0), (0.0, 0.0, 17.0), (85.0, 0.0, 12.2)]        # trough
FA_HIGH = [(55.0, 0.0, 12.2), (105.0, 0.0, 12.2), (a.L2, 0.0, 15.0)]          # wrist housing
FA_BOTTOM = (-22.2, -21.0)
FA_LOW_TOP = -4.5                          # under the rod (z -3) and the upper arm shell (-3)
FA_HIGH_Z = (-20.5, 10.2)                  # wrist MG90S body up to ~+7; horn at -21..-23


def build_forearm_shell(sw):
    p = g.Part(sw, "Forearm Shell", folder=ENC_DIR)
    p.boss(lambda s: s.poly(hull(FA_LOW)), FA_BOTTOM[0], FA_LOW_TOP - FA_BOTTOM[0])
    p.cut(lambda s: s.poly(hull(shrink(FA_LOW, T))), FA_BOTTOM[1], FA_LOW_TOP - FA_BOTTOM[1] + 0.1)
    p.boss(lambda s: s.poly(hull(FA_HIGH)), FA_HIGH_Z[0], FA_HIGH_Z[1] - FA_HIGH_Z[0])
    p.cut(lambda s: s.poly(hull(shrink(FA_HIGH, T))), FA_HIGH_Z[0] - 0.1, FA_HIGH_Z[1] - T - FA_HIGH_Z[0] + 0.1)
    p.cut(lambda s: s.circle(a.L2, 0, 7.0), FA_HIGH_Z[1] - T - 0.1, T + 0.2)   # cable up into the hood
    # The housing's back wall must not cross the forearm link (z -9..-4): slot it (the trough's
    # wider walls hide the slot from the side)
    p.cut(lambda s: s.rect(40.0, -8.6, 57.0, 8.6), FA_HIGH_Z[0] - 0.1, -3.6 - FA_HIGH_Z[0] + 0.1)
    p.boss(lambda s: [s.circle(x, 0, 7.0) for x in FA_INSERTS], FA_BOTTOM[1], a.LOW_Z[0] - FA_BOTTOM[1])
    p.cut(lambda s: [s.circle(x, 0, g.M3_CLEAR) for x in FA_INSERTS], FA_BOTTOM[0] - 0.1, a.LOW_Z[0] - FA_BOTTOM[0] + 0.1)
    return p.finish()


def extra_forearm(p):
    p.cut(lambda s: [s.circle(x, 0, 4.0) for x in FA_INSERTS], a.LOW_Z[0], 4.0)


# ----------------------------------------------------------------------------- hand
# Gripper frame: Z = approach, Y = wrist axis (world z), X = jaw travel. Wrist axis W at
# (0, *, -39). The wrist bracket's plate covers x -40..9, y -26..12, z -22..-19.
PLATE = (-40.0, -26.0, 9.0, 12.0)
HAND = (-41.6, -29.6, 37.6, 29.6)
HAND_Z = (-23.4, 0.0)                     # deck top at 0 (racks and fingers stay above it)
HOOD_Y = (12.4, 16.2)                     # above the plate top (12) and the forearm skin (10.2)


def build_hand_shell(sw, top):
    p = g.Part(sw, "Hand Shell", folder=ENC_DIR)
    x0, y0, x1, y1 = HAND
    p.boss(lambda s: s.poly(rrect(x0, y0, x1, y1, 5.0)), HAND_Z[0], HAND_Z[1] - HAND_Z[0])
    p.cut(lambda s: s.poly(rrect(x0 + T, y0 + T, x1 - T, y1 - T, 3.8)))
    # Back face in front of the plate, open where the plate itself closes the hand
    p.boss(lambda s: s.poly(rrect(x0 + T, y0 + T, x1 - T, y1 - T, 3.8)), -19.0 - T, T)
    px0, py0, px1, py1 = PLATE
    p.cut(lambda s: s.rect(px0 - 0.4, py0 - 0.4, px1 + 0.4, py1 + 0.4), -19.0 - T - 0.1, T + 0.2)
    # Ears behind the plate, clamped under the gripper's two M3 screw heads
    p.boss(lambda s: s.rect(x0 + T, -11.0, -25.0, 11.0), HAND_Z[0], T)
    p.cut(lambda s: [s.circle(-31.0, sy, g.M3_CLEAR) for sy in (6.0, -6.0)])
    # Hood (outline in x, z on the Top Plane, extruded along y) back over the wrist axis
    w_z = -a.GRIPPER_ORIGIN
    hood_o = hull([(0.0, w_z, 17.0), (-13.0, -20.0, 2.0), (13.0, -20.0, 2.0)])
    hood_i = hull([(0.0, w_z, 17.0 - T), (-11.8, -19.0, 2.0), (11.8, -19.0, 2.0)])
    p.side_boss(top, hood_o, HOOD_Y[0], HOOD_Y[1])
    side_cut_poly(p, top, hood_i, (HOOD_Y[0] - 0.1 + HOOD_Y[1] - T) / 2, HOOD_Y[1] - T - HOOD_Y[0] + 0.1)
    return p.finish()


# ----------------------------------------------------------------------------- assembly
def build_assembly(sw, comps_spec, poses, name="Arm Encased"):
    from win32com.client import gencache
    tlb = gencache.EnsureModule("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
    mu = tlb.ISldWorks(sw._oleobj_).GetMathUtility()
    mu = tlb.IMathUtility(getattr(mu, "_oleobj_", mu))
    arr = lambda v: w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x) for x in v])

    def xform(rx, ry, rz, o):
        return mu.CreateTransform(arr([*rx, *ry, *rz, o[0] / 1000, o[1] / 1000, o[2] / 1000,
                                       1, 0, 0, 0]))

    def zrot(deg, x, y, z=0.0):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return xform((c, s, 0), (-s, c, 0), (0, 0, 1), (x, y, z))

    for _, path, _ in comps_spec:
        if not sw.GetOpenDocumentByName(str(path)):
            sw.OpenDoc(str(path), 2 if str(path).endswith(".SLDASM") else 1)
    doc = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    asm = tlb.IAssemblyDoc(doc._oleobj_)
    comps = {}
    for key, path, _ in comps_spec:
        c = doc.AddComponent5(str(path), 0, "", False, "", 0, 0, 0)
        if c is None:
            raise RuntimeError(f"could not insert {path}")
        comps[key] = tlb.IComponent2(c._oleobj_)

    comps["Shoulder Bracket"].Transform2 = zrot(0, 0, -47.5)
    comps["Shoulder Cap +z"].Transform2 = zrot(0, 0, 0)
    comps["Shoulder Cap -z"].Transform2 = xform((-1, 0, 0), (0, 1, 0), (0, 0, -1), (0, 0, 0))

    def set_pose(theta1, phi_f, theta3):
        tf = a.pose_transforms(theta1, phi_f, theta3)
        for key, _, follows in comps_spec:
            if follows in tf:
                deg, x, y = tf[follows]
                comps[key].Transform2 = zrot(deg, x, y)
        W = tf["Wrist Bracket"][1:]
        xg, yg, zg, o = a.gripper_transform(phi_f, theta3, W)
        for key, _, follows in comps_spec:
            if follows == "Gripper":
                comps[key].Transform2 = xform(xg, yg, zg, o)
        doc.ForceRebuild3(False)

    def interference():
        idm = asm.InterferenceDetectionManager
        idm.TreatCoincidenceAsInterference = False
        idm.IncludeMultibodyPartInterferences = False
        found = []
        for r in idm.GetInterferences() or []:
            r = tlb.IInterference(r._oleobj_)
            names = sorted(tlb.IComponent2(c._oleobj_).Name2 for c in r.Components)
            try:
                bb = r.GetInterferenceBody().GetBodyBox
                bb = [round(v * 1000) for v in (bb() if callable(bb) else bb)]
            except Exception:  # noqa: BLE001
                bb = None
            found.append((names, round(r.Volume * 1e9, 1), bb))
        idm.Done()
        return found

    report = []
    for label, (t1, pf, t3) in poses.items():
        set_pose(t1, pf, t3)
        report.append((label, (t1, pf, t3), interference()))
    set_pose(*next(iter(poses.values())))
    doc.ShowNamedView2("*Isometric", 7)
    doc.ViewZoomtofit2()
    path = ENC_DIR / f"{name}.SLDASM"
    doc.SaveAs(str(path))
    return path, report


def mass_props(sw, path):
    doc = sw.GetOpenDocumentByName(str(path)) or sw.OpenDoc(str(path), 2 if str(path).endswith(".SLDASM") else 1)
    mp = doc.GetMassProperties
    mp = mp() if callable(mp) else mp
    return {"mass_g": mp[5] * 1000, "com_mm": [v * 1000 for v in mp[:3]], "vol_cm3": mp[3] * 1e6}


def extra_poses():
    """build_arm's IK poses + the corners the shells could hit: shoulder at both ends, the elbow
    folded in steps (to find the new limit), the wrist at its ends with the arm flat."""
    poses = a.poses_from_ik()
    poses.pop("elbow folded")
    for t2 in (-130, -135):
        poses[f"elbow {t2}"] = (60.0, 60.0 + t2, -30.0)
    poses["shoulder low, elbow straight"] = (-20.0, -20.0, 0.0)
    poses["shoulder low, folded"] = (-20.0, -150.0, -40.0)
    poses["shoulder back"] = (140.0, 120.0, -30.0)
    poses["shoulder back, elbow -120"] = (140.0, 20.0, -30.0)
    poses["flat reach"] = (0.0, 0.0, 0.0)
    for t3 in (-85, -90, 50):
        poses[f"flat, wrist {t3}"] = (0.0, 0.0, float(t3))
    return poses


def main():
    sw = w.Dispatch("SldWorks.Application")
    sw.Visible = True
    ENC_DIR.mkdir(parents=True, exist_ok=True)
    d, titles = sw.GetFirstDocument, []
    while d:
        pth = (d.GetPathName or "").lower()
        if str(g.OUT).lower() in pth or d.GetTitle.startswith("_probe"):
            titles.append(d.GetTitle)
        d = d.GetNext
    for t in titles:
        sw.CloseDoc(t)

    # Links with extra features: build_arm's own functions, saved into Arm Encased/.
    extras = {"Upper Arm": extra_upper_arm, "Crank": extra_crank, "Forearm": extra_forearm}

    def enc_part(sw_, name):
        p = g.Part(sw_, name, folder=ENC_DIR)
        orig = p.finish

        def finish():
            extras[name](p)
            return orig()
        p.finish = finish
        return p
    a.Part = enc_part

    top = g.probe_plane(sw, "Top Plane")
    built = {}
    built["Shoulder Bracket"] = copy_shoulder_bracket(sw)
    built["Upper Arm"] = a.build_upper_arm(sw)
    built["Crank"] = a.build_crank(sw)
    built["Forearm"] = a.build_forearm(sw)
    built["Shoulder Cap"] = build_shoulder_cap(sw)
    built["Upper Arm Shell"] = build_upper_arm_shell(sw)
    built["Forearm Shell"] = build_forearm_shell(sw)
    built["Hand Shell"] = build_hand_shell(sw, top)
    for n, (pth, vol) in built.items():
        print(f"{n:18s} {vol * 1.24:6.1f} g PLA   {vol:6.2f} cm3")

    P = lambda n: ENC_DIR / f"{n}.SLDPRT"
    O = lambda n: a.ARM_DIR / f"{n}.SLDPRT"
    spec = [  # (key, file, which pose it follows)
        ("Shoulder Bracket", P("Shoulder Bracket"), None),
        ("Shoulder Cap +z", P("Shoulder Cap"), None),
        ("Shoulder Cap -z", P("Shoulder Cap"), None),
        ("Upper Arm", P("Upper Arm"), "Upper Arm"),
        ("Upper Arm Shell", P("Upper Arm Shell"), "Upper Arm"),
        ("Crank", P("Crank"), "Crank"),
        ("Rod", O("Rod"), "Rod"),
        ("Forearm", P("Forearm"), "Forearm"),
        ("Forearm Shell", P("Forearm Shell"), "Forearm"),
        ("Elbow Spacer", O("Elbow Spacer"), "Elbow Spacer"),
        ("Wrist Bracket", O("Wrist Bracket"), "Wrist Bracket"),
        ("Gripper", g.GRIPPER_DIR / "Gripper.SLDASM", "Gripper"),
        ("Hand Shell", P("Hand Shell"), "Gripper"),
    ]
    asm, report = build_assembly(sw, spec, extra_poses())
    bad = 0
    for label, ang, found in report:
        bad += bool(found)
        print(f"pose {label:30s} {tuple(round(v) for v in ang)}: {len(found)} interference(s) {found}")
    print("assembly:", asm, "| poses with interference:", bad)

    # Mass + centre of mass of every moving part, in its own frame, for tools/torque_check.py
    props = {}
    for key, path, follows in spec:
        if key in props or key.startswith("Shoulder"):
            continue
        props[key] = {**mass_props(sw, path), "frame": follows}
    out = ENC_DIR / "mass_properties.json"
    out.write_text(json.dumps(props, indent=2))
    print("mass properties ->", out)
    # Close everything we opened WITHOUT saving: SolidWorks marks the referenced Arm/ and
    # Gripper/ files dirty and would otherwise rewrite them (they must stay byte-identical).
    d, titles = sw.GetFirstDocument, []
    while d:
        if str(g.OUT).lower() in (d.GetPathName or "").lower():
            titles.append(d.GetTitle)
        d = d.GetNext
    for t in titles:
        sw.QuitDoc(t)


if __name__ == "__main__":
    sys.exit(main())

