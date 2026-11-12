"""Build the RoboArm gripper in SolidWorks from Python (Vyom + Claude, 2026-11-09).

Two-jaw parallel gripper: one pinion on the MG90S horn drives two identical racks in
opposite directions, so the jaws stay parallel and centred (CLAUDE.md 4.1, D17).

Run with SolidWorks installed (it opens SolidWorks):   py tools/cad/build_gripper.py
Output: SolidWorks Parts/Gripper/ (Body, Pinion, Rack, Fingers, Thumb + Gripper.SLDASM)

World frame (all parts are modelled in place, so the assembly needs no mates):
  origin = servo shaft axis at the deck's top face (where the MG90S tabs sit)
  +Z     = towards the fingertips (approach direction)
  X      = jaw travel direction, Y = across the jaws
All numbers below are mm. The SolidWorks API wants metres; MM converts.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pythoncom
import win32com.client as w

# ----------------------------------------------------------------------------- parameters
OUT = Path(__file__).resolve().parents[2] / "SolidWorks Parts"
GRIPPER_DIR = OUT / "Gripper"              # one folder per assembly (Nov 12)

# Gear (D17): module 1.5 prints cleanly on a 0.4 mm nozzle; 16 teeth -> 24 mm pitch dia.
# The tooth count MUST be even: the second jaw is the same part turned 180 deg, so 180 deg
# has to be a whole number of teeth (15 teeth collided in the interference check).
M = 1.5
Z_TEETH = 16
PA = math.radians(20)            # pressure angle
BACKLASH = 0.10                  # mm taken off EACH tooth's thickness (printing slop)
R = M * Z_TEETH / 2              # pitch radius 11.25
RB = R * math.cos(PA)            # base circle
RA = R + M                       # pinion tip
RF = R - 1.25 * M                # pinion root
P = math.pi * M                  # circular pitch 4.712
RACK_ADD = 1.25                  # rack addendum, shortened from 1.5 to avoid undercut
RACK_DED = 1.25 * M              # rack dedendum
CENTRE_GAP = 0.10                # extra pinion-to-rack distance (printing slop)

# Travel: opening 0..40 mm (config/arm.yaml gripper.open_mm) -> 20 mm per jaw.
OPEN_MAX = 40.0
X_E_MID = 13.0                   # rack end position in the saved assembly (20 mm open)
RACK_LEN = 36.0
FINGER_T = 3.0                   # jaw plate thickness (X)
FINGER_H = 30.0                  # jaw plate height (Z)
FINGER_Y = (-12.0, None)         # jaw plate spans from y=-12 to the rack's back edge
RACK_BACK = 6.0                  # rack body thickness behind the tooth roots

# Heights (Z). ESTIMATES until the MG90S horn is measured: shaft tip ~12.5 above the
# tab underside (28.5 - 16.0), horn hub ~1.5 on top of that.
Z_P0 = 14.0                      # pinion bottom = top of the horn arm (MEASURED 14.0, Nov 10)
PINION_W = 6.0                   # pinion face width
RACK_W = 7.0                     # rack face width (0.5 proud of the pinion top and bottom)
Z_R0 = Z_P0 - 0.5
Z_R1 = Z_R0 + RACK_W

# MG90S (D15): pocket 11.9 x 22.8 (+0.00), shaft 5.6 from one end, tab holes 27.5 apart.
SERVO_W, SERVO_L, SHAFT_FROM_END = 11.9, 22.8, 5.6
TAB_PITCH = 27.5
M2_PILOT = 1.8                   # self-tapping M2 into plastic (D15)
M3_CLEAR, M3_NUT_AF, M3_NUT_DEPTH = 3.45, 5.6, 4.2   # D15: depth = nut 3.87 + 0.3 (2.6 was the TEST depth; nuts stuck up)

DECK_T = 2.5
DECK_X = (-35.0, 35.0)
RAIL_W = 2.6                     # thin rail; a round boss carries the hold-down screw
BOSS_D = 5.5
SCREW_X = 8.0                    # rack hold-down screws at (-8, +y) and (+8, -y)

# MG90S horn, measured by Vyom 2026-11-10: hub OD 7.0 (sticks up 3.5 above the arm), arm 2.0
# thick at the tips, holes Ø2.0 at r = 6 and r = 17. The arms get TRIMMED to ~8.5 mm radius
# (just past the first holes) so they fit under the pinion and clear the racks and rails.
HORN_HUB_D, HORN_HUB_DEPTH = 7.6, 3.8   # recess: hub Ø7.0 + 0.6, 3.5 tall + 0.3
HORN_ACCESS_D = 5.5              # screwdriver access to the horn's own centre screw (head Ø ~4.5)
HORN_PILOT_R = 6.0               # first horn holes (measured)
HORN_PILOT_D = 1.6               # small self-tapping screws up through the horn into the pinion

# ---- Tilting fingers (D17 update, Nov 11: mitten, 15 deg flare open, tips ~5 deg IN at 30 mm).
# Each finger pivots on its rack at P; a follower pin F, H_F below P, rides in a VERTICAL slot
# fixed to the body at x = CAM_X. The rack moves P sideways but F can't, so the finger tilts:
#     sin(tilt) = (x_P - CAM_X) / H_F        (positive tilt = fingertip OUTWARD)
# 4 deg per mm of jaw travel: +15.0 at 40 mm open, -5.2 at 30 mm (tips in, option b),
# -17.5 at 24 mm. Below ~24 mm the fingertips would collide, so the racks stop at 24-40 mm.
H_F = 14.3
CAM_X = 17.8
X_CLOSED, X_OPEN = 16.0, 23.0          # rack end positions: opening 2*(x_e - 3) = 26 .. 40
                                       # (26, not 24: the curled tips would pass only 1.3 mm apart)
X_E0 = CAM_X + 1.5                     # parts are modelled with zero tilt (x_e = 19.3)
XP0 = X_E0 - 1.5                       # pivot x (middle of the 3 mm finger plate)
Z_PIV = 24.5                           # pivot height: inside the rack's connector block
Z_FOL = Z_PIV - H_F                    # follower height (10.2)
PLATE_Z0 = Z_PIV + 4.0                 # finger plate starts above the block, clear at any tilt
FINGERS_TOP, THUMB_TOP = 50.0, 46.0   # (straight-finger heights, kept for reference)
# Curled fingers (Vyom chose option A, Nov 12): segments (length, angle from the finger's own
# vertical; negative = curls INWARD), a 3 mm strip with a rounded tip. Palm / middle / tip.
# At rest (15 deg flare) they look like a relaxed hand; gripping, the FINGERTIPS take the load.
FINGER_SEGS = [(9, 0), (7, -20), (6, -40)]
THUMB_SEGS = [(8, 0), (8, -30)]
TAB_Y = (None, None)                   # set below from Y_BACK
M2_CLEAR = 2.4


def tilt_deg(x_e):
    return math.degrees(math.asin((x_e - 1.5 - CAM_X) / H_F))


def opening_mm(x_e):
    return 2 * (x_e - 3.0)


def finger_strip(segs):
    """Bent 3 mm strip with a rounded tip, for the rack-A finger at zero tilt, in model (x, z).
    Returns (outline, centreline points). Starts 1 mm down inside the tab so they fuse."""
    pts = [(XP0, PLATE_Z0 - 1.0), (XP0, PLATE_Z0)]
    x, z = XP0, PLATE_Z0
    for L, a in segs:
        r = math.radians(a)
        x, z = x + L * math.sin(r), z + L * math.cos(r)
        pts.append((x, z))
    angs = [segs[0][1]] + [a for _, a in segs]
    inner, outer = [], []
    for i, (px, pz) in enumerate(pts):
        if i in (0, len(pts) - 1):
            r = math.radians(angs[min(i, len(angs) - 1)])
            n, t = (-math.cos(r), math.sin(r)), 1.5
        else:                                   # mitre at each knuckle
            r1, r2 = math.radians(angs[i]), math.radians(angs[min(i + 1, len(angs) - 1)])
            n1, n2 = (-math.cos(r1), math.sin(r1)), (-math.cos(r2), math.sin(r2))
            n = ((n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2)
            m = math.hypot(*n)
            n = (n[0] / m, n[1] / m)
            t = 1.5 / max(0.5, n[0] * n1[0] + n[1] * n1[1])
        inner.append((px + t * n[0], pz + t * n[1]))
        outer.append((px - t * n[0], pz - t * n[1]))
    r = math.radians(angs[-1])
    u, n = (math.sin(r), math.cos(r)), (-math.cos(r), math.sin(r))
    tx, tz = pts[-1]
    arc = [(tx + 1.5 * (math.cos(q) * n[0] + math.sin(q) * u[0]),
            tz + 1.5 * (math.cos(q) * n[1] + math.sin(q) * u[1]))
           for q in [k * math.pi / 8 for k in range(1, 8)]]
    return inner + arc + list(reversed(outer)), pts


# Derived rack geometry (rack A, on the +Y side; jaw B is the same part turned 180 deg).
Y_PITCH = R + CENTRE_GAP
Y_TIP = Y_PITCH - RACK_ADD
Y_ROOT = Y_PITCH + RACK_DED
Y_BACK = Y_ROOT + RACK_BACK
Y_SCREW = (Y_ROOT + Y_BACK) / 2
TAB_Y = (Y_BACK + 0.5, Y_BACK + 3.5)          # finger tab, beside the rack's block
CAM_Y = (Y_BACK + 4.0, Y_BACK + 7.0)          # body plate carrying the follower slot

MM = 0.001


# ----------------------------------------------------------------------------- SolidWorks helpers
NOTHING = w.VARIANT(pythoncom.VT_DISPATCH, None)


class Part:
    def __init__(self, sw, name, folder=None):
        self.sw, self.name = sw, name
        self.folder = folder or GRIPPER_DIR
        self.doc = sw.NewDocument(sw.GetUserPreferenceStringValue(8), 0, 0, 0)
        self.skm = self.doc.SketchManager
        self.fm = self.doc.FeatureManager

    # --- sketches on the Front Plane (world XY), entities given in mm
    def sketch(self, draw):
        self.doc.ClearSelection2(True)
        self.doc.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        self.skm.InsertSketch(True)
        self.skm.AddToDB = True
        draw(self)
        self.skm.AddToDB = False
        self.skm.InsertSketch(True)
        name = self.doc.FeatureByPositionReverse(0).Name
        self.doc.ClearSelection2(True)
        self.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, NOTHING, 0)
        return name

    def poly(self, pts):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            self.skm.CreateLine(x1 * MM, y1 * MM, 0, x2 * MM, y2 * MM, 0)

    def rect(self, x1, y1, x2, y2):
        self.poly([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])

    def circle(self, x, y, d):
        self.skm.CreateCircleByRadius(x * MM, y * MM, 0, d / 2 * MM)

    def hexagon(self, x, y, af):
        r = af / math.sqrt(3)  # corner radius from across-flats
        self.poly([(x + r * math.cos(a), y + r * math.sin(a))
                   for a in (math.radians(30 + 60 * i) for i in range(6))])

    # --- sketches on the Right Plane (model YZ) or Top Plane (model XZ). `pm` is a PlaneMap
    #     from probe_plane(): it converts model coordinates into that plane's sketch axes.
    def side_cut(self, pm, shapes, mid=None, depth=None):
        """shapes: list of ("circle", a, b, d) / ("rect", a0, b0, a1, b1) in the plane's two
        MODEL axes. Through everything, or mid-plane `depth` centred at model normal = mid."""
        self.doc.ClearSelection2(True)
        self.doc.Extension.SelectByID2(pm.plane, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        self.skm.InsertSketch(True)
        self.skm.AddToDB = True
        for sh in shapes:
            if sh[0] == "circle":
                u, v = pm.uv(sh[1], sh[2])
                self.skm.CreateCircleByRadius(u * MM, v * MM, 0, sh[3] / 2 * MM)
            else:
                corners = [pm.uv(a, b) for a, b in ((sh[1], sh[2]), (sh[3], sh[2]),
                                                    (sh[3], sh[4]), (sh[1], sh[4]))]
                for (u1, v1), (u2, v2) in zip(corners, corners[1:] + corners[:1]):
                    self.skm.CreateLine(u1 * MM, v1 * MM, 0, u2 * MM, v2 * MM, 0)
        self.skm.AddToDB = False
        self.skm.InsertSketch(True)
        name = self.doc.FeatureByPositionReverse(0).Name
        self.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, NOTHING, 0)
        if mid is None:
            args, start = (False, False, False, 1, 1, 0, 0), (0, 0, False)
        else:
            off = mid * pm.normal_sign                     # offset along the plane's normal
            args = (True, False, False, 6, 0, depth * MM, 0)  # 6 = mid-plane
            start = (3, abs(off) * MM, off < 0)
        f = self.fm.FeatureCut4(*args, False, False, False, False, 0, 0, False, False,
                                False, False, False, True, True, True, True, False,
                                *start, False)
        if f is None:
            raise RuntimeError(f"{self.name}: side cut on {pm.plane} failed")
        return f

    def side_boss(self, pm, outline, a0, a1):
        """Extrude an outline drawn in a side plane's model axes (e.g. x, z on the Top Plane)
        from normal coordinate a0 to a1 (e.g. y from -12 to 23.5)."""
        self.doc.ClearSelection2(True)
        self.doc.Extension.SelectByID2(pm.plane, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        self.skm.InsertSketch(True)
        self.skm.AddToDB = True
        uv = [pm.uv(a, b) for a, b in outline]
        for (u1, v1), (u2, v2) in zip(uv, uv[1:] + uv[:1]):
            self.skm.CreateLine(u1 * MM, v1 * MM, 0, u2 * MM, v2 * MM, 0)
        self.skm.AddToDB = False
        self.skm.InsertSketch(True)
        name = self.doc.FeatureByPositionReverse(0).Name
        self.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, NOTHING, 0)
        off = a0 * pm.normal_sign
        f = self.fm.FeatureExtrusion3(True, False, pm.normal_sign < 0, 0, 0, (a1 - a0) * MM, 0,
                                      False, False, False, False, 0, 0, False, False, False, False,
                                      True, True, True, 3, abs(off) * MM, off < 0)
        if f is None:
            raise RuntimeError(f"{self.name}: side boss on {pm.plane} failed")
        return f

    def volume(self):
        mp = self.doc.GetMassProperties
        mp = mp() if callable(mp) else mp
        return mp[3] * 1e9                                    # mm3

    # --- features. z0 = start height, depth = along +Z.
    def boss(self, draw, z0, depth):
        self.sketch(draw)
        f = self.fm.FeatureExtrusion3(
            True, False, False, 0, 0, depth * MM, 0, False, False, False, False, 0, 0,
            False, False, False, False, True, True, True,
            3 if z0 else 0, abs(z0) * MM, z0 < 0)
        if f is None:
            raise RuntimeError(f"{self.name}: boss at z={z0} failed")
        return f

    def cut(self, draw, z0=None, depth=None):
        """Through everything (default) or a blind pocket from z0 going +Z by depth."""
        self.sketch(draw)
        if z0 is None:
            args = (False, False, False, 1, 1, 0, 0)
            start = (0, 0, False)
        else:
            args = (True, False, True, 0, 0, depth * MM, 0)  # Dir=True: cut towards +Z
            start = (3 if z0 else 0, abs(z0) * MM, z0 < 0)
        f = self.fm.FeatureCut4(*args, False, False, False, False, 0, 0, False, False,
                                False, False, False, True, True, True, True, False,
                                *start, False)
        if f is None:
            raise RuntimeError(f"{self.name}: cut failed")
        return f

    def finish(self):
        self.doc.SetMaterialPropertyName2("Default", "SOLIDWORKS Materials", "PLA")
        self.doc.ForceRebuild3(False)
        self.doc.ShowNamedView2("*Isometric", 7)
        self.doc.ViewZoomtofit2()
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{self.name}.SLDPRT"
        if not self.doc.SaveAs(str(path)):
            raise RuntimeError(f"could not save {path}")
        mp = self.doc.GetMassProperties  # [cx, cy, cz, volume, area, mass, ...] in SI
        mp = mp() if callable(mp) else mp
        vol_cm3 = mp[3] * 1e6
        return path, vol_cm3


class PlaneMap:
    """How a plane's sketch (u, v) axes and normal map onto model axes, found by probing."""
    AX = {"x": 0, "y": 1, "z": 2}

    def __init__(self, plane, centre):
        # The probe drew a circle at sketch (10, 20) and extruded it 1 mm along the normal.
        self.plane = plane
        self.u = self.v = None
        for name, i in self.AX.items():
            if abs(round(centre[i])) == 10:
                self.u = (name, 1 if centre[i] > 0 else -1)
            elif abs(round(centre[i])) == 20:
                self.v = (name, 1 if centre[i] > 0 else -1)
        n = ({"x", "y", "z"} - {self.u[0], self.v[0]}).pop()
        self.normal = n
        self.normal_sign = 1 if centre[self.AX[n]] > 0 else -1
        self.axes = sorted({self.u[0], self.v[0]}, key=lambda k: self.AX[k])   # model order

    def uv(self, a, b):
        """Model coordinates along self.axes (e.g. (y, z) for the Right Plane) -> sketch."""
        model = dict(zip(self.axes, (a, b)))
        return model[self.u[0]] * self.u[1], model[self.v[0]] * self.v[1]


def probe_plane(sw, plane):
    p = Part(sw, "_probe")
    p.doc.Extension.SelectByID2(plane, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
    p.skm.InsertSketch(True)
    p.skm.AddToDB = True
    p.skm.CreateCircleByRadius(0.010, 0.020, 0, 0.001)
    p.skm.AddToDB = False
    p.skm.InsertSketch(True)
    name = p.doc.FeatureByPositionReverse(0).Name
    p.doc.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, NOTHING, 0)
    p.fm.FeatureExtrusion3(True, False, False, 0, 0, 0.001, 0, False, False, False, False, 0, 0,
                           False, False, False, False, True, True, True, 0, 0, False)
    box = p.doc.GetBodies2(0, True)[0].GetBodyBox
    box = box() if callable(box) else box
    centre = [(box[i] + box[i + 3]) / 2 * 1000 for i in range(3)]
    sw.CloseDoc(p.doc.GetTitle)
    pm = PlaneMap(plane, centre)
    print(f"{plane}: sketch u -> {pm.u}, v -> {pm.v}, normal {pm.normal}{'+' if pm.normal_sign > 0 else '-'}")
    return pm


# ----------------------------------------------------------------------------- geometry
def involute(alpha):
    return math.tan(alpha) - alpha


def pinion_outline():
    s = P / 2 - BACKLASH                       # tooth thickness at the pitch circle
    psi = s / 2 / R
    inv_p = involute(PA)

    def half(rho):  # half tooth angle at radius rho (radial flank below the base circle)
        rho = max(rho, RB)
        return psi + inv_p - involute(math.acos(RB / rho))

    radii = [RB + (RA - RB) * i / 6 for i in range(7)]
    pts = []
    # Phase: rack A has a tooth centred at x = P/4, so the pinion needs a SPACE at the top
    # rotated back by (P/4)/R; teeth sit half a tooth further on. With an even tooth count
    # the bottom of the pinion then lines up with rack B (rack A turned 180 deg).
    first_tooth = math.pi / 2 - (P / 4) / R + math.pi / Z_TEETH
    for k in range(Z_TEETH):
        c = first_tooth + k * 2 * math.pi / Z_TEETH
        pol = lambda r, a: (r * math.cos(a), r * math.sin(a))
        pts.append(pol(RF, c - half(RB)))
        pts += [pol(r, c - half(r)) for r in radii]
        pts.append(pol(RA, c))
        pts += [pol(r, c + half(r)) for r in reversed(radii)]
        pts.append(pol(RF, c + half(RB)))
        nxt = c + 2 * math.pi / Z_TEETH - half(RB)
        mid = (c + half(RB) + nxt) / 2
        pts.append(pol(RF, mid))
    return pts


def rack_outline(x_e):
    """Rack A at end position x_e: back edge, then the toothed edge from +X to -X."""
    x0 = x_e - RACK_LEN
    wt = (P / 2 - BACKLASH) / 2 - RACK_ADD * math.tan(PA)   # half width at the tip
    wr = (P / 2 - BACKLASH) / 2 + RACK_DED * math.tan(PA)   # half width at the root
    pts = [(x0, Y_BACK), (x_e, Y_BACK), (x_e, Y_ROOT)]
    # Teeth only where they can mesh: within 1 mm of each end, 31 mm of toothed length.
    centres = [P / 4 + k * P for k in range(-20, 20)]
    for xc in sorted((c for c in centres if x_e - 31 <= c - wr and c + wr <= x_e - 1),
                     reverse=True):
        pts += [(xc + wr, Y_ROOT), (xc + wt, Y_TIP), (xc - wt, Y_TIP), (xc - wr, Y_ROOT)]
    pts.append((x0, Y_ROOT))
    return pts


# ----------------------------------------------------------------------------- parts
def build_pinion(sw):
    p = Part(sw, "Gripper Pinion")
    p.boss(lambda s: s.poly(pinion_outline()), Z_P0, PINION_W)
    p.cut(lambda s: s.circle(0, 0, HORN_ACCESS_D))
    p.cut(lambda s: s.circle(0, 0, HORN_HUB_D), Z_P0, HORN_HUB_DEPTH)
    p.cut(lambda s: (s.circle(HORN_PILOT_R, 0, HORN_PILOT_D),
                     s.circle(-HORN_PILOT_R, 0, HORN_PILOT_D)))
    return p.finish()


def build_rack(sw, top):
    """Rack + connector block (modelled at x_e = X_E0). The finger pivots on the block.
    Rack B is the same part turned 180 deg about Z."""
    x_e = X_E0
    j = Part(sw, "Gripper Rack")
    j.boss(lambda s: s.poly(rack_outline(x_e)), Z_R0, RACK_W)
    j.boss(lambda s: s.rect(x_e - 8, Y_ROOT, x_e, Y_BACK), Z_R1, 6.0)
    # Pivot: M2 self-tapping screw along Y, from the finger's tab into the block.
    j.side_cut(top, [("circle", XP0, Z_PIV, M2_PILOT)])
    # Hold-down slot: the body's screw at x = -SCREW_X, seen from this rack over its travel
    # X_CLOSED..X_OPEN. The slot ends are also the END STOPS (24 and 40 mm opening).
    s_lo, s_hi = -SCREW_X + (x_e - X_OPEN), -SCREW_X + (x_e - X_CLOSED)
    j.cut(lambda s: s.rect(s_lo, Y_SCREW - 1.2, s_hi, Y_SCREW + 1.2))
    j.cut(lambda s: (s.circle(s_lo, Y_SCREW, 2.4), s.circle(s_hi, Y_SCREW, 2.4)))
    return j.finish()


def build_finger(sw, top, right, thumb: bool):
    """Curled mitten finger (rack A side) or thumb (rack B side), modelled upright (zero tilt)
    on the +Y side at x_e = X_E0. A tab beside the rack's block carries the pivot P and the
    follower F; the curled strip rises from the tab above the block, clear of it at any tilt."""
    j = Part(sw, "Gripper Thumb" if thumb else "Gripper Fingers")
    segs = THUMB_SEGS if thumb else FINGER_SEGS
    y_lo = -6.0 if thumb else -12.0
    j.boss(lambda s: s.rect(XP0 - 3, TAB_Y[0], XP0 + 3, TAB_Y[1]), Z_FOL - 3.0,
           (PLATE_Z0 + 3.0) - (Z_FOL - 3.0))
    outline, cl = finger_strip(segs)
    j.side_boss(top, outline, y_lo, TAB_Y[1])
    # Pivot (clearance: the finger turns on the screw) and follower (pilot: screw fixed in tab).
    j.side_cut(top, [("circle", XP0, Z_PIV, M2_CLEAR), ("circle", XP0, Z_FOL, M2_PILOT)])
    # Silhouette along X (Right Plane: model y, z). The band near the base joins the strip
    # to the tab; above it only the hand part (y -12..12 / thumb -6..6) carries on.
    band = PLATE_Z0 + 5.5
    knuckle = cl[2][1]                          # top of the palm segment
    if thumb:
        j.side_cut(right, [("rect", 6.0, band, TAB_Y[1] + 1, 80)])
    else:
        # Four fingers: three 1.2 mm gaps from the big knuckle up (the palm stays one piece).
        j.side_cut(right, [("rect", gy - 0.6, knuckle, gy + 0.6, 80) for gy in (-6.0, 0.0, 6.0)]
                   + [("rect", 12.0, band, TAB_Y[1] + 1, 80)])
    return j.finish()


def build_body(sw, top):
    b = Part(sw, "Gripper Body")
    sx0, sx1 = -SHAFT_FROM_END, SERVO_L - SHAFT_FROM_END
    sc = (sx0 + sx1) / 2
    # Deck the servo tabs sit on, two thin rails the racks slide on (each with a round boss
    # for its hold-down screw), and two posts for the wrist bracket (PLACEHOLDER).
    b.boss(lambda s: s.rect(DECK_X[0], -Y_BACK, DECK_X[1], Y_BACK), -DECK_T, DECK_T)
    b.boss(lambda s: s.rect(-35, Y_SCREW - RAIL_W / 2, 25, Y_SCREW + RAIL_W / 2), 0.0, Z_R0)
    b.boss(lambda s: s.rect(-25, -Y_SCREW - RAIL_W / 2, 35, -Y_SCREW + RAIL_W / 2), 0.0, Z_R0)
    b.boss(lambda s: (s.circle(-SCREW_X, Y_SCREW, BOSS_D), s.circle(SCREW_X, -Y_SCREW, BOSS_D)),
           0.0, Z_R0)
    # Ø10 posts: the 5.6 hex nut is 6.5 across corners, so Ø7.5 left only 0.5 mm of wall.
    b.boss(lambda s: (s.circle(-31, 6, 10.0), s.circle(-31, -6, 10.0)), -19.0, 19.0 - DECK_T)
    # Servo opening and tab screw pilots.
    b.cut(lambda s: s.rect(sx0, -SERVO_W / 2, sx1, SERVO_W / 2))
    b.cut(lambda s: (s.circle(sc - TAB_PITCH / 2, 0, M2_PILOT),
                     s.circle(sc + TAB_PITCH / 2, 0, M2_PILOT)))
    # Rack hold-down screw pilots (M2 self-tapping, from the top of each rail).
    b.cut(lambda s: (s.circle(-SCREW_X, Y_SCREW, M2_PILOT),
                     s.circle(SCREW_X, -Y_SCREW, M2_PILOT)))
    # Follower plates (one per side) with the vertical slot the finger's follower pin rides in.
    for sgn in (1, -1):
        b.boss(lambda s, k=sgn: s.rect(k * (CAM_X - 5), k * Y_BACK, k * (CAM_X + 5), k * CAM_Y[1]),
               -DECK_T, DECK_T)
        b.boss(lambda s, k=sgn: s.rect(k * (CAM_X - 5), k * CAM_Y[0], k * (CAM_X + 5), k * CAM_Y[1]),
               0.0, Z_FOL + 4.0)
    # Wrist mount PLACEHOLDER: 2x M3 up through the block, captive nuts in the deck top.
    b.cut(lambda s: (s.circle(-31, 6, M3_CLEAR), s.circle(-31, -6, M3_CLEAR)))
    b.cut(lambda s: (s.hexagon(-31, 6, M3_NUT_AF), s.hexagon(-31, -6, M3_NUT_AF)),
          -M3_NUT_DEPTH, M3_NUT_DEPTH)
    # Follower slots: 2.4 wide, vertical, covering the follower's small rise (10.2-10.9).
    # Cut mid-plane in each follower plate only (a through-cut would notch the rails), and
    # checked by volume, since this is the one cut that depends on the plane's normal sign.
    before = b.volume()
    slot = (Z_FOL - 1.2 - 0.5, Z_FOL + 0.7 + 1.2)
    for sgn in (1, -1):
        b.side_cut(top, [("rect", sgn * CAM_X - 1.2, slot[0], sgn * CAM_X + 1.2, slot[1])],
                   mid=sgn * (CAM_Y[0] + CAM_Y[1]) / 2, depth=4.0)
    removed = before - b.volume()
    expect = 2 * 2.4 * (slot[1] - slot[0]) * 3.0
    if abs(removed - expect) > 0.5:
        raise RuntimeError(f"follower slots removed {removed:.1f} mm3, expected {expect:.1f}")
    return b.finish()


def build_assembly(sw, parts):
    """Body, pinion, 2 racks, fingers (rack A side) and thumb (rack B side), driven through
    the whole opening range; interference-checked at each step; saved fully open (at rest)."""
    for path in parts.values():
        if not sw.GetOpenDocumentByName(str(path)):
            sw.OpenDoc(str(path), 1)
    doc = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    order = ["body", "pinion", "rack", "rack", "fingers", "thumb"]
    comps = [doc.AddComponent5(str(parts[k]), 0, "", False, "", 0, 0, 0) for k in order]
    if any(c is None for c in comps):
        raise RuntimeError("a component failed to insert")
    # MathUtility needs early binding, and arrays must be explicit VT_R8 SAFEARRAYs.
    from win32com.client import gencache
    sw_tlb = gencache.EnsureModule("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
    mu = sw_tlb.ISldWorks(sw._oleobj_).GetMathUtility()
    mu = sw_tlb.IMathUtility(getattr(mu, "_oleobj_", mu))
    comps = [sw_tlb.IComponent2(c._oleobj_) for c in comps]

    def put(comp, rx, ry, rz, t):
        """rx/ry/rz = where the part's X/Y/Z axes point; t = translation (mm)."""
        a = [*rx, *ry, *rz, t[0] / 1000, t[1] / 1000, t[2] / 1000, 1, 0, 0, 0]
        comp.Transform2 = mu.CreateTransform(w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                                       [float(v) for v in a]))

    def set_opening(x_e):
        d = x_e - X_E0                       # rack A displacement from the modelled position
        th = -d / R                          # pinion turns with the racks (rolling, no slip)
        c, sn = math.cos(th), math.sin(th)
        b = math.radians(tilt_deg(x_e))
        cb, sb = math.cos(b), math.sin(b)
        # Finger: rotate about +Y through its pivot, which has moved by d.
        rp = (XP0 * cb + Z_PIV * sb, 0.0, -XP0 * sb + Z_PIV * cb)
        t = (XP0 + d - rp[0], 0.0, Z_PIV - rp[2])
        put(comps[0], (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0))
        put(comps[1], (c, sn, 0), (-sn, c, 0), (0, 0, 1), (0, 0, 0))
        put(comps[2], (1, 0, 0), (0, 1, 0), (0, 0, 1), (d, 0, 0))
        put(comps[3], (-1, 0, 0), (0, -1, 0), (0, 0, 1), (-d, 0, 0))
        put(comps[4], (cb, 0, -sb), (0, 1, 0), (sb, 0, cb), t)
        put(comps[5], (-cb, 0, -sb), (0, -1, 0), (-sb, 0, cb), (-t[0], 0.0, t[2]))
        doc.ForceRebuild3(False)

    results = []
    for x_e in (X_CLOSED, 17.0, 18.0, 20.0, 22.0, X_OPEN):
        set_opening(x_e)
        n = check_interference(sw_tlb, doc, quiet=True)
        results.append((opening_mm(x_e), tilt_deg(x_e), n))
    set_opening(X_OPEN)                       # save it at rest: fully open, fingers flared
    doc.ShowNamedView2("*Isometric", 7)
    doc.ViewZoomtofit2()
    path = GRIPPER_DIR / "Gripper.SLDASM"
    doc.SaveAs(str(path))
    return path, results


def check_interference(sw_tlb, doc, quiet=False):
    """Count overlapping parts (touching faces are allowed); print each overlap."""
    idm = sw_tlb.IAssemblyDoc(doc._oleobj_).InterferenceDetectionManager
    idm.TreatCoincidenceAsInterference = False
    found = idm.GetInterferences() or []
    for r in found:
        r = sw_tlb.IInterference(r._oleobj_)
        names = [sw_tlb.IComponent2(c._oleobj_).Name2 for c in r.Components]
        print(f"  INTERFERENCE {names}: {r.Volume * 1e9:.2f} mm3")
    idm.Done()
    print(f"interference check: {len(found)} overlap(s)")
    return len(found)


def main():
    sw = w.Dispatch("SldWorks.Application")
    sw.Visible = True
    names = ("Gripper Body", "Gripper Pinion", "Gripper Rack", "Gripper Fingers",
             "Gripper Thumb", "Gripper Jaw")
    ours = {str(f / f"{n}.SLDPRT").lower() for n in names for f in (OUT, GRIPPER_DIR)}
    ours |= {str(f / "Gripper.SLDASM").lower() for f in (OUT, GRIPPER_DIR)}
    d, titles = sw.GetFirstDocument, []
    while d:                                   # close only OUR files, never other open work
        if (d.GetPathName or "").lower() in ours:
            titles.append(d.GetTitle)
        d = d.GetNext
    for t in titles:
        sw.CloseDoc(t)
    top, right = probe_plane(sw, "Top Plane"), probe_plane(sw, "Right Plane")
    built = {}
    for key, fn in (("pinion", lambda: build_pinion(sw)), ("rack", lambda: build_rack(sw, top)),
                    ("fingers", lambda: build_finger(sw, top, right, thumb=False)),
                    ("thumb", lambda: build_finger(sw, top, right, thumb=True)),
                    ("body", lambda: build_body(sw, top))):
        path, vol = fn()
        built[key] = path
        print(f"{path.stem:16s} {vol * 1.24:5.1f} g solid PLA")
    asm, results = build_assembly(sw, built)
    for opening, tilt, n in results:
        print(f"opening {opening:4.1f} mm  finger tilt {tilt:+5.1f} deg  interferences: {n}")
    print("assembly:", asm)


if __name__ == "__main__":
    sys.exit(main())
