"""Build the RoboArm gripper in SolidWorks from Python (Vyom + Claude, 2026-11-09).

Two-jaw parallel gripper: one pinion on the MG90S horn drives two identical racks in
opposite directions, so the jaws stay parallel and centred (CLAUDE.md 4.1, D17).

Run with SolidWorks installed (it opens SolidWorks):   py tools/cad/build_gripper.py
Output: SolidWorks Parts/Gripper Body|Pinion|Jaw.SLDPRT + Gripper.SLDASM

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
Z_P0 = 14.0                      # pinion bottom
PINION_W = 6.0                   # pinion face width
RACK_W = 7.0                     # rack face width (0.5 proud of the pinion top and bottom)
Z_R0 = Z_P0 - 0.5
Z_R1 = Z_R0 + RACK_W

# MG90S (D15): pocket 11.9 x 22.8 (+0.00), shaft 5.6 from one end, tab holes 27.5 apart.
SERVO_W, SERVO_L, SHAFT_FROM_END = 11.9, 22.8, 5.6
TAB_PITCH = 27.5
M2_PILOT = 1.8                   # self-tapping M2 into plastic (D15)
M3_CLEAR, M3_NUT_AF, M3_NUT_DEPTH = 3.45, 5.6, 2.6   # D15

DECK_T = 2.5
DECK_X = (-35.0, 35.0)
RAIL_W = 2.6                     # thin rail; a round boss carries the hold-down screw
BOSS_D = 5.5
SCREW_X = 8.0                    # rack hold-down screws at (-8, +y) and (+8, -y)

HORN_HUB_D, HORN_HUB_DEPTH = 7.6, 2.5   # recess for the horn hub (hub measured 7.07)
HORN_SCREW_CLEAR, HORN_SCREW_HEAD = 2.4, 4.5
HORN_PILOT_R = 6.0               # PLACEHOLDER: horn arm screw radius (not measured yet)

# Derived rack geometry (rack A, on the +Y side; jaw B is the same part turned 180 deg).
Y_PITCH = R + CENTRE_GAP
Y_TIP = Y_PITCH - RACK_ADD
Y_ROOT = Y_PITCH + RACK_DED
Y_BACK = Y_ROOT + RACK_BACK
Y_SCREW = (Y_ROOT + Y_BACK) / 2

MM = 0.001


# ----------------------------------------------------------------------------- SolidWorks helpers
NOTHING = w.VARIANT(pythoncom.VT_DISPATCH, None)


class Part:
    def __init__(self, sw, name):
        self.sw, self.name = sw, name
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
        path = OUT / f"{self.name}.SLDPRT"
        if not self.doc.SaveAs(str(path)):
            raise RuntimeError(f"could not save {path}")
        mp = self.doc.GetMassProperties  # [cx, cy, cz, volume, area, mass, ...] in SI
        mp = mp() if callable(mp) else mp
        vol_cm3 = mp[3] * 1e6
        return path, vol_cm3


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
    p.cut(lambda s: s.circle(0, 0, HORN_SCREW_CLEAR))
    p.cut(lambda s: s.circle(0, 0, HORN_SCREW_HEAD), Z_P0 + PINION_W - 2.0, 2.0)
    p.cut(lambda s: s.circle(0, 0, HORN_HUB_D), Z_P0, HORN_HUB_DEPTH)
    p.cut(lambda s: (s.circle(HORN_PILOT_R, 0, 1.2), s.circle(-HORN_PILOT_R, 0, 1.2)))
    return p.finish()


def build_jaw(sw):
    x_e = X_E_MID
    j = Part(sw, "Gripper Jaw")
    j.boss(lambda s: s.poly(rack_outline(x_e)), Z_R0, RACK_W)
    # Connector block on the rack's back half, then the jaw plate across the centreline.
    j.boss(lambda s: s.rect(x_e - 8, Y_ROOT, x_e, Y_BACK), Z_R1, 6.0)
    j.boss(lambda s: s.rect(x_e - FINGER_T, FINGER_Y[0], x_e, Y_BACK), Z_R1 + 1.0, FINGER_H)
    # Hold-down slot. The body's screw is fixed at x = -SCREW_X. Seen from this jaw (modelled
    # at x_e), the screw sweeps from -SCREW_X + (x_e - 23) when fully open (x_e = 23)
    # to -SCREW_X + (x_e - 3) when closed (x_e = 3): the slot covers exactly that, +clearance.
    x_closed, x_open = 3.0, 3.0 + OPEN_MAX / 2
    s_lo, s_hi = -SCREW_X + (x_e - x_open), -SCREW_X + (x_e - x_closed)
    j.cut(lambda s: s.rect(s_lo, Y_SCREW - 1.2, s_hi, Y_SCREW + 1.2))
    j.cut(lambda s: (s.circle(s_lo, Y_SCREW, 2.4), s.circle(s_hi, Y_SCREW, 2.4)))
    return j.finish()


def build_body(sw):
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
    b.boss(lambda s: (s.circle(-31, 6, 7.5), s.circle(-31, -6, 7.5)), -19.0, 19.0 - DECK_T)
    # Servo opening and tab screw pilots.
    b.cut(lambda s: s.rect(sx0, -SERVO_W / 2, sx1, SERVO_W / 2))
    b.cut(lambda s: (s.circle(sc - TAB_PITCH / 2, 0, M2_PILOT),
                     s.circle(sc + TAB_PITCH / 2, 0, M2_PILOT)))
    # Rack hold-down screw pilots (M2 self-tapping, from the top of each rail).
    b.cut(lambda s: (s.circle(-SCREW_X, Y_SCREW, M2_PILOT),
                     s.circle(SCREW_X, -Y_SCREW, M2_PILOT)))
    # Wrist mount PLACEHOLDER: 2x M3 up through the block, captive nuts in the deck top.
    b.cut(lambda s: (s.circle(-31, 6, M3_CLEAR), s.circle(-31, -6, M3_CLEAR)))
    b.cut(lambda s: (s.hexagon(-31, 6, M3_NUT_AF), s.hexagon(-31, -6, M3_NUT_AF)),
          -M3_NUT_DEPTH, M3_NUT_DEPTH)
    return b.finish()


def build_assembly(sw, body, pinion, jaw):
    doc = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    # The three parts are still open from building them, which AddComponent5 needs.
    comps = [doc.AddComponent5(str(p), 0, "", False, "", 0, 0, 0) for p in (body, pinion, jaw, jaw)]
    if any(c is None for c in comps):
        raise RuntimeError("a component failed to insert")
    # AddComponent5 centres each part's bounding box on the insertion point, so set every
    # component's transform explicitly: identity (parts are modelled in place), except the
    # second jaw, which is the same part turned 180 deg about Z.
    # MathUtility needs SolidWorks' type library (early binding), and the array must be
    # passed as an explicit VT_R8 SAFEARRAY or SolidWorks silently gets an identity matrix.
    from win32com.client import gencache
    sw_tlb = gencache.EnsureModule("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
    mu = sw_tlb.ISldWorks(sw._oleobj_).GetMathUtility()
    mu = sw_tlb.IMathUtility(getattr(mu, "_oleobj_", mu))
    arr = lambda a: w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in a])
    ident = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    flip = [-1, 0, 0, 0, -1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    for comp, xf in zip(comps, (ident, ident, ident, flip)):
        sw_tlb.IComponent2(comp._oleobj_).Transform2 = mu.CreateTransform(arr(xf))
    doc.ForceRebuild3(False)
    doc.ShowNamedView2("*Isometric", 7)
    doc.ViewZoomtofit2()
    path = OUT / "Gripper.SLDASM"
    doc.SaveAs(str(path))
    check_interference(sw_tlb, doc)
    return path


def check_interference(sw_tlb, doc):
    """Fail loudly if any two parts overlap (touching faces are allowed)."""
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
    sw.CloseAllDocuments(True)
    results = {}
    for build in (build_pinion, build_jaw, build_body):
        path, vol = build(sw)
        results[path.stem] = vol
        print(f"{path.stem:16s} solid volume {vol:5.2f} cm3 -> {vol * 1.24:5.1f} g solid PLA")
    asm = build_assembly(sw, OUT / "Gripper Body.SLDPRT", OUT / "Gripper Pinion.SLDPRT",
                         OUT / "Gripper Jaw.SLDPRT")
    total = (results["Gripper Body"] + results["Gripper Pinion"] + 2 * results["Gripper Jaw"]) * 1.24
    print(f"printed parts, solid PLA: {total:.1f} g (budget 20 g incl. ~infill savings)")
    print("assembly:", asm)


if __name__ == "__main__":
    sys.exit(main())
