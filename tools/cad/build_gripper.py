"""Build the RoboArm gripper in SolidWorks from Python (Vyom + Claude, 2026-11-09).

Two-jaw parallel gripper: one pinion on the MG90S horn drives two identical racks in
opposite directions, so the jaws stay parallel and centred (CLAUDE.md 4.1, D17).

Run with SolidWorks installed (it opens SolidWorks):   py tools/cad/build_gripper.py
Output: SolidWorks Parts/Gripper/ (Body, Pinion, Rack, Fingers, Thumb, Cover + Gripper.SLDASM)

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
RACK_LEN = 36.0
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

# ---- Flat straight fingers (D21, Nov 15-16, team): a hand's four fingers on rack A and a thumb
# on rack B, but FLAT and STRAIGHT (no tilt, no curl): every finger's face is in one plane, the
# two faces stay parallel at any opening, so the whole face grips and the opening is linear in
# servo angle. Each rack carries a STEM that rises through the cover's slot; the finger plate
# screws onto it from above with 2x M2, a tongue in a pocket takes the twist. The gear and racks
# live INSIDE a cover (Gripper Cover; Arm Human uses its own Palm Cover).
X_CLOSED, X_OPEN = 4.0, 23.0           # rack end positions: opening 2*(x_e - 3) = 2 .. 40
X_E0 = 13.0                            # parts are modelled at 20 mm open
JAW_T = 3.0                            # plate thickness (X); the grip face is at x_e - 3
JAW_Y = 20.0                           # fingers span y -20..20: the whole deck width
JAW_Z = (25.0, 65.0)                   # face from z 25 to the longest fingertip (grasp mid-face, l3 84)
BAND_Z = 33.0                          # solid "palm" band; the fingers are separate above it
FINGERS = [  # (y0, y1, tip z): index, middle, ring, little; 1.5 mm gaps
    (10.75, 20.0, 61.0), (0.75, 9.25, 65.0), (-9.25, -0.75, 63.0), (-20.0, -10.75, 57.0)]
THUMB = (-7.0, 7.0, 58.0)              # one wide, flat thumb opposite the fingers
TIP_CHAMFER = 2.0
FOOT_T = 3.0                           # the plate's foot on top of the stem
STEM_X = (-5.0, 8.0)                   # stem, relative to x_e: 5 mm over the rack, 8 mm past its end
STEM_IN = 1.5                          # stem starts 1.5 in from the tooth roots: the cover's slot
                                       # then stays 1 mm clear of the teeth (no gear in sight)
STEM_Z0 = 14.0                         # past the rack's end the stem rides 0.5 above the rail
JAW_SCREWS = (2.0, 5.5)                # the 2 M2, x relative to x_e (mid-stem in y)
TONGUE_Z = 22.0                        # the plate's tongue reaches down into the stem to here
GROOVE_W, GROOVE_D, GROOVE_PITCH = 1.0, 0.8, 2.5   # horizontal grip grooves on the face
COVER_POSTS = ((30.0, 0.0), (-30.0, 0.0))          # the cover's lid screws onto these posts
COVER_LID_Z = 22.6                     # underside of the lid (rack hold-down screw heads top ~22.1)
COVER_LID_T = 1.4
COVER_OUT = (40.0, 24.0, 8.0)          # Gripper Cover: half-x, half-y, corner radius (outside)
COVER_WALL = 1.6
M2_CLEAR = 2.4


def opening_mm(x_e):
    return 2 * (x_e - 3.0)


# Derived rack geometry (rack A, on the +Y side; jaw B is the same part turned 180 deg).
Y_PITCH = R + CENTRE_GAP
Y_TIP = Y_PITCH - RACK_ADD
Y_ROOT = Y_PITCH + RACK_DED
Y_BACK = Y_ROOT + RACK_BACK
Y_SCREW = (Y_ROOT + Y_BACK) / 2
STEM_Y = (Y_ROOT + STEM_IN, Y_BACK)           # stem (and the finger plate's foot) in y
JAW_SCREW_Y = (STEM_Y[0] + STEM_Y[1]) / 2


def lid_slots():
    """The cover lid's two slots (rack A's stem, rack B's stem) over the whole travel, 0.5 clear."""
    lo, hi = X_CLOSED + STEM_X[0] - 0.5, X_OPEN + STEM_X[1] + 0.5
    ya, yb = STEM_Y[0] - 0.5, STEM_Y[1] + 0.5
    return [(lo, ya, hi, yb), (-hi, -yb, -lo, -ya)]


def rrect_pts(hx, hy, r, n=8):
    pts = []
    for cx, cy, a0 in ((hx - r, hy - r, 0), (-hx + r, hy - r, 90), (-hx + r, -hy + r, 180), (hx - r, -hy + r, 270)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * k / n)), cy + r * math.sin(math.radians(a0 + 90 * k / n)))
                for k in range(n + 1)]
    return pts

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
        """shapes: list of ("circle", a, b, d) / ("rect", a0, b0, a1, b1) / ("poly", [(a, b), ..])
        in the plane's two
        MODEL axes. Through everything, or mid-plane `depth` centred at model normal = mid."""
        self.doc.ClearSelection2(True)
        self.doc.Extension.SelectByID2(pm.plane, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        self.skm.InsertSketch(True)
        self.skm.AddToDB = True
        for sh in shapes:
            if sh[0] == "circle":
                u, v = pm.uv(sh[1], sh[2])
                self.skm.CreateCircleByRadius(u * MM, v * MM, 0, sh[3] / 2 * MM)
            elif sh[0] == "poly":
                uv = [pm.uv(a, b) for a, b in sh[1]]
                for (u1, v1), (u2, v2) in zip(uv, uv[1:] + uv[:1]):
                    self.skm.CreateLine(u1 * MM, v1 * MM, 0, u2 * MM, v2 * MM, 0)
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


def build_rack(sw):
    """Rack + stem (modelled at x_e = X_E0). Rack B is the same part turned 180 deg about Z."""
    x_e = X_E0
    j = Part(sw, "Gripper Rack")
    j.boss(lambda s: s.poly(rack_outline(x_e)), Z_R0, RACK_W)
    # Stem over the rack's back strip and past its end, up to the jaw's foot
    j.boss(lambda s: s.rect(x_e + STEM_X[0], STEM_Y[0], x_e + STEM_X[1], STEM_Y[1]), STEM_Z0,
           JAW_Z[0] - STEM_Z0)
    # Pocket for the jaw's tongue (0.15 clearance) and the pilots for the jaw's 2 M2
    j.cut(lambda s: s.rect(x_e - JAW_T - 0.15, STEM_Y[0] + 0.15, x_e + 0.15, STEM_Y[1] - 0.15),
          TONGUE_Z - 0.3, JAW_Z[0] - TONGUE_Z + 0.4)
    j.cut(lambda s: [s.circle(x_e + dx, JAW_SCREW_Y, M2_PILOT) for dx in JAW_SCREWS],
          JAW_Z[0] - 9.0, 9.1)
    # Hold-down slot: the body's screw at x = -SCREW_X, seen from this rack over its travel
    # X_CLOSED..X_OPEN. The slot ends are also the END STOPS (2 and 40 mm opening).
    s_lo, s_hi = -SCREW_X + (x_e - X_OPEN), -SCREW_X + (x_e - X_CLOSED)
    j.cut(lambda s: s.rect(s_lo, Y_SCREW - 1.2, s_hi, Y_SCREW + 1.2))
    j.cut(lambda s: (s.circle(s_lo, Y_SCREW, 2.4), s.circle(s_hi, Y_SCREW, 2.4)))
    return j.finish()


def build_finger(sw, top, right, thumb: bool):
    """Flat straight fingers (rack A) or thumb (rack B), modelled for rack A at x_e = X_E0 (the
    thumb part is then turned 180 deg like its rack). Grip face at x = x_e - 3, grooved; a solid
    band up to BAND_Z joins the fingers and reaches the stem; a foot on the stem, a tongue into it."""
    x_e = X_E0
    j = Part(sw, "Gripper Thumb" if thumb else "Gripper Fingers")
    fingers = [THUMB] if thumb else FINGERS
    y_lo = THUMB[0] if thumb else -JAW_Y
    j.boss(lambda s: s.rect(x_e - JAW_T, y_lo, x_e, JAW_Y), JAW_Z[0], BAND_Z - JAW_Z[0])
    top_z = max(f[2] for f in fingers)
    j.boss(lambda s: [s.rect(x_e - JAW_T, y0, x_e, y1) for y0, y1, _ in fingers], BAND_Z - 0.5,
           top_z - BAND_Z + 0.5)
    j.boss(lambda s: s.rect(x_e, STEM_Y[0], x_e + STEM_X[1], STEM_Y[1]), JAW_Z[0], FOOT_T)
    j.boss(lambda s: s.rect(x_e - JAW_T, STEM_Y[0] + 0.3, x_e, STEM_Y[1] - 0.3), TONGUE_Z,
           JAW_Z[0] - TONGUE_Z)
    j.cut(lambda s: [s.circle(x_e + dx, JAW_SCREW_Y, M2_CLEAR) for dx in JAW_SCREWS])
    # Grip grooves across the face (Top Plane = model x, z; through all along y)
    face = x_e - JAW_T
    n = int((top_z - JAW_Z[0] - 7.0) / GROOVE_PITCH)
    zs = [JAW_Z[0] + 4.0 + k * GROOVE_PITCH for k in range(n)]
    j.side_cut(top, [("rect", face - 1.0, z, face + GROOVE_D, z + GROOVE_W) for z in zs])
    # Fingertips: each finger cut to its length, both tip corners chamfered (Right Plane = y, z)
    c, cuts = TIP_CHAMFER, []
    lengths = [("rect", y0 - 0.7, zt, y1 + 0.7, top_z + 5) for y0, y1, zt in fingers if zt < top_z]
    if lengths:                          # separate sketch: overlapping outlines fail the cut
        j.side_cut(right, lengths)
    for y0, y1, zt in fingers:
        cuts.append(("poly", [(y0 - 0.7, zt - c - 0.7), (y0 - 0.7, zt + 1), (y0 + c + 1, zt + 1)]))
        cuts.append(("poly", [(y1 + 0.7, zt - c - 0.7), (y1 - c - 1, zt + 1), (y1 + 0.7, zt + 1)]))
    if thumb:                            # soften the band's outer top corner beside the thumb
        cuts.append(("poly", [(JAW_Y + 1, BAND_Z - 5), (JAW_Y + 1, BAND_Z + 1), (JAW_Y - 5, BAND_Z + 1)]))
    j.side_cut(right, cuts)
    return j.finish()


def build_cover(sw):
    """Gripper Cover: a rounded box over the deck, pinion and racks; only the two finger stems
    come up through the lid. Drops on from above (before the finger plates) and screws to the
    body's two posts with 2x M2."""
    c = Part(sw, "Gripper Cover")
    hx, hy, r = COVER_OUT
    t = COVER_WALL
    z0, z1 = -DECK_T, COVER_LID_Z + COVER_LID_T
    c.boss(lambda s: s.poly(rrect_pts(hx, hy, r)), z0, z1 - z0)
    c.cut(lambda s: s.poly(rrect_pts(hx - t, hy - t, r - t)), z0 - 0.5, COVER_LID_Z - z0 + 0.5)
    c.cut(lambda s: [s.rect(*sl) for sl in lid_slots()])
    c.cut(lambda s: [s.circle(x, y, M2_CLEAR) for x, y in COVER_POSTS])
    return c.finish()


def build_body(sw, cover_posts=True):
    b = Part(sw, "Gripper Body")
    sx0, sx1 = -SHAFT_FROM_END, SERVO_L - SHAFT_FROM_END
    sc = (sx0 + sx1) / 2
    # Deck the servo tabs sit on, two thin rails the racks slide on (each with a round boss
    # for its hold-down screw), and two posts for the wrist bracket.
    b.boss(lambda s: s.rect(DECK_X[0], -Y_BACK, DECK_X[1], Y_BACK), -DECK_T, DECK_T)
    b.boss(lambda s: s.rect(-35, Y_SCREW - RAIL_W / 2, 25, Y_SCREW + RAIL_W / 2), 0.0, Z_R0)
    b.boss(lambda s: s.rect(-25, -Y_SCREW - RAIL_W / 2, 35, -Y_SCREW + RAIL_W / 2), 0.0, Z_R0)
    b.boss(lambda s: (s.circle(-SCREW_X, Y_SCREW, BOSS_D), s.circle(SCREW_X, -Y_SCREW, BOSS_D)),
           0.0, Z_R0)
    # Ø10 posts: the 5.6 hex nut is 6.5 across corners, so Ø7.5 left only 0.5 mm of wall.
    b.boss(lambda s: (s.circle(-31, 6, 10.0), s.circle(-31, -6, 10.0)), -19.0, 19.0 - DECK_T)
    if cover_posts:                      # the cover's lid screws down onto these
        b.boss(lambda s: [s.circle(x, y, 6.0) for x, y in COVER_POSTS], 0.0, COVER_LID_Z)
        b.cut(lambda s: [s.circle(x, y, M2_PILOT) for x, y in COVER_POSTS], COVER_LID_Z - 8.0, 8.1)
    # Servo opening and tab screw pilots.
    b.cut(lambda s: s.rect(sx0, -SERVO_W / 2, sx1, SERVO_W / 2))
    b.cut(lambda s: (s.circle(sc - TAB_PITCH / 2, 0, M2_PILOT),
                     s.circle(sc + TAB_PITCH / 2, 0, M2_PILOT)))
    # Rack hold-down screw pilots (M2 self-tapping, from the top of each rail).
    b.cut(lambda s: (s.circle(-SCREW_X, Y_SCREW, M2_PILOT),
                     s.circle(SCREW_X, -Y_SCREW, M2_PILOT)))
    # Wrist mount: 2x M3 up through the posts, captive nuts in the deck top.
    b.cut(lambda s: (s.circle(-31, 6, M3_CLEAR), s.circle(-31, -6, M3_CLEAR)))
    b.cut(lambda s: (s.hexagon(-31, 6, M3_NUT_AF), s.hexagon(-31, -6, M3_NUT_AF)),
          -M3_NUT_DEPTH, M3_NUT_DEPTH)
    return b.finish()


OPENINGS = (X_CLOSED, 6.0, 9.0, 13.0, 18.0, X_OPEN)        # rack positions the check visits


def jaw_poses(x_e):
    """(rx, ry, rz, t) for pinion, rack/jaw A and rack/jaw B at rack position x_e."""
    d = x_e - X_E0                       # rack A displacement from the modelled position
    th = -d / R                          # pinion turns with the racks (rolling, no slip)
    c, sn = math.cos(th), math.sin(th)
    return {"pinion": ((c, sn, 0), (-sn, c, 0), (0, 0, 1), (0, 0, 0)),
            "A": ((1, 0, 0), (0, 1, 0), (0, 0, 1), (d, 0, 0)),
            "B": ((-1, 0, 0), (0, -1, 0), (0, 0, 1), (-d, 0, 0))}


def build_assembly(sw, parts, path=None, extras=()):
    """Body, pinion, 2 racks, fingers + thumb (+ `extras`: fixed parts, e.g. covers), driven
    through the whole opening range; interference-checked at each step; saved fully open."""
    for p_ in parts.values():
        if not sw.GetOpenDocumentByName(str(p_)):
            sw.OpenDoc(str(p_), 1)
    doc = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    order = ["body", "pinion", "rack", "rack", "fingers", "thumb", *extras]
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
        jp = jaw_poses(x_e)
        put(comps[1], *jp["pinion"])
        for k in (2, 4):                     # rack A + fingers, rack B + thumb (turned 180 deg)
            put(comps[k], *jp["A"])
            put(comps[k + 1], *jp["B"])
        for k in [0] + list(range(6, len(comps))):
            put(comps[k], (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0))
        doc.ForceRebuild3(False)

    results = []
    for x_e in OPENINGS:
        set_opening(x_e)
        results.append((opening_mm(x_e), check_interference(sw_tlb, doc, quiet=True)))
    set_opening(X_OPEN)                       # save it at rest: fully open
    doc.ShowNamedView2("*Isometric", 7)
    doc.ViewZoomtofit2()
    path = path or GRIPPER_DIR / "Gripper.SLDASM"
    doc.SaveAs(str(path))
    return path, results


def check_interference(sw_tlb, doc, quiet=False):
    """Overlapping parts (touching faces are allowed), as [(names, mm3)]."""
    idm = sw_tlb.IAssemblyDoc(doc._oleobj_).InterferenceDetectionManager
    idm.TreatCoincidenceAsInterference = False
    found = []
    for r in idm.GetInterferences() or []:
        r = sw_tlb.IInterference(r._oleobj_)
        found.append((sorted(sw_tlb.IComponent2(c._oleobj_).Name2 for c in r.Components),
                      round(r.Volume * 1e9, 2)))
    idm.Done()
    if not quiet:
        print(f"interference check: {len(found)} overlap(s) {found}")
    return found


def build_all(sw, cover=True):
    """Every gripper part, saved into GRIPPER_DIR (a caller may point that elsewhere). cover=False
    leaves out the Gripper Cover (Arm Human has its own); the body's posts are always there."""
    top, right = probe_plane(sw, "Top Plane"), probe_plane(sw, "Right Plane")
    built = {}
    steps = [("pinion", lambda: build_pinion(sw)), ("rack", lambda: build_rack(sw)),
             ("fingers", lambda: build_finger(sw, top, right, thumb=False)),
             ("thumb", lambda: build_finger(sw, top, right, thumb=True)),
             ("body", lambda: build_body(sw))]
    if cover:
        steps.append(("cover", lambda: build_cover(sw)))
    for key, fn in steps:
        path, vol = fn()
        built[key] = path
        print(f"{path.stem:16s} {vol * 1.24:5.1f} g solid PLA")
    return built


def main():
    sw = w.Dispatch("SldWorks.Application")
    sw.Visible = True
    names = ("Gripper Body", "Gripper Pinion", "Gripper Rack", "Gripper Fingers",
             "Gripper Thumb", "Gripper Jaw", "Gripper Cover")
    ours = {str(f / f"{n}.SLDPRT").lower() for n in names for f in (OUT, GRIPPER_DIR)}
    ours |= {str(f / "Gripper.SLDASM").lower() for f in (OUT, GRIPPER_DIR)}
    d, titles = sw.GetFirstDocument, []
    while d:                                   # close only OUR files, never other open work
        if (d.GetPathName or "").lower() in ours:
            titles.append(d.GetTitle)
        d = d.GetNext
    for t in titles:
        sw.CloseDoc(t)
    built = build_all(sw)
    asm, results = build_assembly(sw, built, extras=("cover",))
    for opening, found in results:
        print(f"opening {opening:4.1f} mm  interferences: {len(found)} {found}")
    print("assembly:", asm)


if __name__ == "__main__":
    sys.exit(main())
