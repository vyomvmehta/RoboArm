"""Human-looking arm: the same four-bar arm in organic skins, with a hand (Vyom asked 2026-11-13;
Claude built by script). Output: SolidWorks Parts/Arm Human/

Run with SolidWorks free:   py tools/cad/build_arm_human.py

Same mechanism, IK and calibration as Arm/ (D19) and the same hidden cable path as the
encased option (D20). What's different from Arm Encased:
  Upper Arm Skin   smooth spline loft: rounded shoulder end, a bicep bulge mid-arm, a rounded
                   elbow knob behind the joint (where the four-bar rod has to live anyway)
  Forearm Skin     thick near the elbow, tapering to a narrow wrist
  Wrist Bracket    rounded (one teardrop flange) + Wrist Cap: a round cap over the horn screws
  Wrist Cuff       wraps the bracket plate and the gripper servo, wrist to deck
  Palm Cover       rounded box over the deck, gears and racks; only the jaw stems come through
  Gripper parts    flat straight fingers + thumb (D21, build_gripper) saved here
  Hand.SLDASM      gripper + cuff + palm cover
Shoulder caps, crank drum, bracket cable hole and insert holes come from build_arm_encased.py.

Skins are 1.2 mm thin-wall lofts through superellipse sections (a superellipse is between an
ellipse and a rounded box: it needs to be squarish where the rod sweeps a flat band). Where a
skin has to stay out of another layer (near the shoulder axis and the elbow) it is clipped
flat and left open on that side, like the encased version.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pythoncom
import win32com.client as w

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_arm as a  # noqa: E402
import build_arm_encased as e  # noqa: E402
import build_gripper as g  # noqa: E402

HUMAN_DIR = g.OUT / "Arm Human"
T = 1.2
MM = g.MM


def var(vals):
    return w.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in vals])


def superellipse(cx, cy, a_, b_, n, k=32):
    pts = []
    for i in range(k):
        t = 2 * math.pi * i / k
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + a_ * math.copysign(abs(c) ** (2 / n), c),
                    cy + b_ * math.copysign(abs(s) ** (2 / n), s)))
    return pts


# ----------------------------------------------------------------------------- feature helpers
def plane_at(p, base, pm, dist):
    """Reference plane parallel to `base`, at model coordinate `dist` along its normal."""
    p.doc.ClearSelection2(True)
    p.doc.Extension.SelectByID2(base, "PLANE", 0, 0, 0, False, 0, g.NOTHING, 0)
    if abs(dist) < 1e-9:
        return None
    along = dist * pm.normal_sign
    f = p.fm.InsertRefPlane(8 | (256 if along < 0 else 0), abs(along) * MM, 0, 0, 0, 0)
    if f is None:
        raise RuntimeError(f"{p.name}: plane at {dist} failed")
    return f


def spline_sketch(p, base, pm, dist, pts):
    """Closed spline through `pts` (in the plane's two model axes) on a plane at `dist`."""
    f = plane_at(p, base, pm, dist)
    p.doc.ClearSelection2(True)
    if f is None:
        p.doc.Extension.SelectByID2(base, "PLANE", 0, 0, 0, False, 0, g.NOTHING, 0)
    else:
        f.Select2(False, 0)
    p.skm.InsertSketch(True)
    p.skm.AddToDB = True
    flat = []
    for u, v in pts + pts[:1]:
        su, sv = pm.uv(u, v)
        flat += [su * MM, sv * MM, 0.0]
    if p.skm.CreateSpline2(var(flat), True) is None:
        raise RuntimeError(f"{p.name}: spline failed")
    p.skm.AddToDB = False
    p.skm.InsertSketch(True)
    return p.doc.FeatureByPositionReverse(0).Name


def thin_loft(p, sketches, t=T):
    """sketches: [(name, (x, y, z) of the spline's start point in mm)]. Picking every section
    AT its start point puts the loft's connectors there; picked anywhere else SolidWorks lines
    the sections up at different points and the skin twists and folds into the part."""
    p.doc.ClearSelection2(True)
    for nm, (x, y, z) in sketches:
        if not p.doc.Extension.SelectByID2(nm, "SKETCH", x * MM, y * MM, z * MM, True, 1, g.NOTHING, 0):
            raise RuntimeError(f"{p.name}: could not pick {nm}")
    f = p.fm.InsertProtrusionBlend2(False, True, False, 1, 0, 0, 1, 1, True, True,
                                    True, t * MM, 0, 2, True, True, True, 0)
    if f is None:
        raise RuntimeError(f"{p.name}: loft failed")


def skin(p, base, pm, sections):
    """sections: [(station, (centre_u, centre_v, half_u, half_v, n)), ...] along the plane normal."""
    picks = []
    for st, sec in sections:
        pts = superellipse(*sec)
        model = dict(zip(pm.axes, pts[0]))
        model[pm.normal] = st
        picks.append((spline_sketch(p, base, pm, st, pts), (model["x"], model["y"], model["z"])))
    thin_loft(p, picks)


def up_to_next(p, draw, z0, down):
    """Boss from z0 (Front Plane offset) up (or down) to the next face: standoffs to a skin."""
    p.sketch(draw)
    f = p.fm.FeatureExtrusion3(True, False, down, 2, 0, 0, 0, False, False, False, False, 0, 0,
                               False, False, False, False, True, True, True,
                               3 if z0 else 0, abs(z0) * MM, z0 < 0)
    if f is None:
        raise RuntimeError(f"{p.name}: standoff failed")


# ----------------------------------------------------------------------------- upper arm
# Upper-arm frame (x along the arm, y in the plane of motion, z along the shoulder axis).
# The rod sweeps y -6.5..36.5 at z -3..2, so the +y side is the "back" of the arm (triceps,
# elbow point) and the forearm folds to the -y side (bicep side), like a real arm.
UA_SECTIONS = [  # x: (yc, zc, half-y, half-z, n). Near the axis z must stay in -3..21.
    (10.0, (15.0, 3.0, 29.0, 17.6, 2.4)),
    (30.0, (15.0, 3.0, 29.0, 17.6, 2.4)),
    (55.0, (14.0, 4.0, 28.0, 19.5, 2.2)),
    (80.0, (14.0, 5.0, 29.0, 21.0, 2.2)),      # bicep
    (105.0, (14.0, 6.0, 28.5, 19.0, 2.2)),
    (130.0, (14.0, 9.0, 31.0, 18.0, 2.3)),     # elbow: E boss, rod's L end, bolt head
    (150.0, (17.0, 7.0, 25.0, 17.0, 2.2)),
    (160.0, (18.0, 7.0, 19.0, 15.0, 2.2)),     # round the rod's L end (reaches x ~158)
    (166.0, (18.5, 7.0, 12.0, 10.0, 2.2)),     # rounded elbow knob (Nov 15: no peak)
    (170.5, (19.0, 7.0, 4.0, 3.5, 2.0)),       # smallest end the 1.2 mm wall lofts to; capped below
]
UA_INSERTS = e.UA_INSERTS


def build_upper_arm_skin(sw, right):
    p = g.Part(sw, "Upper Arm Skin", folder=HUMAN_DIR)
    skin(p, "Right Plane", right, [(x, sec) for x, sec in UA_SECTIONS])
    # Cap the knob's small end so the elbow has no hole at its tip
    x_end, (yc, zc, hy, hz, _) = UA_SECTIONS[-1]
    cap = spline_sketch(p, "Right Plane", right, x_end, superellipse(yc, zc, hy + 0.6, hz + 0.6, 2.0))
    p.doc.ClearSelection2(True)
    p.doc.Extension.SelectByID2(cap, "SKETCH", 0, 0, 0, False, 0, g.NOTHING, 0)
    if p.fm.FeatureExtrusion3(True, False, False, 0, 0, T * MM, 0, False, False, False, False, 0, 0,
                              False, False, False, False, True, True, True, 0, 0, False) is None:
        raise RuntimeError("elbow cap failed")
    # Shoulder drum (turns with the arm, hides the shoulder servo), as in the encased version
    p.boss(lambda s: (s.circle(0, 0, 2 * e.DRUM_R), s.circle(0, 0, 2 * (e.DRUM_R - T))), -3.0, 24.0)
    # Clear the layers below: crank + drum near the axis, forearm near the elbow
    p.cut(lambda s: s.circle(0, 0, 92.0), -40.0, 37.0)
    p.cut(lambda s: s.rect(78.0, -80.0, 200.0, 80.0), -40.0, 37.0)     # elbow straight: lever end tucks under
    p.cut(lambda s: s.circle(0, 0, 2 * (e.DRUM_R - T)))
    # Open the drum ring where the rod and the upper arm link pass (the skin covers the gap)
    p.cut(lambda s: s.poly([(0.0, 0.0)] + [(43.5 * math.cos(math.radians(d)), 43.5 * math.sin(math.radians(d)))
                                          for d in range(-12, 76, 4)]), -3.1, 22.2)
    # Standoffs from the link's top face up to the skin; M3 into the link's heat-set inserts
    up_to_next(p, lambda s: [s.circle(x, 0, 7.0) for x in UA_INSERTS], a.UA_Z[1], down=False)
    p.cut(lambda s: [s.circle(x, 0, g.M3_CLEAR) for x in UA_INSERTS], a.UA_Z[1], 40.0)
    return p.finish()


# ----------------------------------------------------------------------------- forearm
FA_SECTIONS = [  # x: (yc, zc, half-y, half-z, n). Nov 15: fullest a third of the way down,
    #                                           then one smooth taper to an oval wrist
    (-45.0, (0.0, -10.0, 3.0, 3.0, 2.0)),       # 2x2 is too small for the 1.2 mm wall to loft
    (-38.0, (0.0, -9.0, 8.5, 10.0, 2.2)),       # the lever's round end reaches x -36.5
    (-30.0, (0.0, -9.0, 11.0, 12.0, 2.2)),      # lever + rod pin nut
    (0.0, (0.0, -9.0, 18.0, 14.0, 2.2)),        # elbow: M8 nut, hollow bolt's cable exit
    (30.0, (0.0, -6.0, 19.0, 16.0, 2.2)),       # fullest (forearm muscle)
    (60.0, (0.0, -5.0, 16.0, 15.0, 2.2)),
    (88.0, (0.0, -4.5, 13.0, 14.0, 2.2)),
    (110.0, (0.0, -3.5, 11.0, 13.0, 2.2)),      # wrist MG90S body (y +-6.1, up to z +7)
    (124.0, (0.0, -3.0, 9.5, 12.5, 2.2)),       # wrist
    (129.0, (0.0, -3.5, 7.5, 10.0, 2.2)),       # round the forearm link's tip (x 130.4)
    (134.0, (0.0, -4.0, 3.0, 3.5, 2.0)),        # inside r 16 of the wrist axis
]
FA_CABLE_X = 104.0                              # gripper lead leaves the forearm here (grommet)
FA_INSERTS = e.FA_INSERTS


def build_forearm_skin(sw, right, top):
    p = g.Part(sw, "Forearm Skin", folder=HUMAN_DIR)
    skin(p, "Right Plane", right, FA_SECTIONS)
    # Inner elbow: open on top under the rod / upper arm (z > -3.6) up to x 40, then a gradual
    # scoop up to the full forearm by x 72 (it was a flat cut with a hard step)
    crease = [(-50.0, -3.6), (40.0, -3.6), (52.0, -1.0), (62.0, 4.0), (72.0, 12.0),
              (72.0, 40.0), (-50.0, 40.0)]
    e.side_cut_poly(p, top, crease, 0.0, 100.0)
    p.cut(lambda s: s.rect(100.0, -7.5, 129.0, 7.5), -40.0, 26.0)           # servo gear + shaft (disc below)
    p.cut(lambda s: s.circle(FA_CABLE_X, 0, 7.0), 4.0, 20.0)               # gripper lead out (grommet)
    up_to_next(p, lambda s: [s.circle(x, 0, 7.0) for x in FA_INSERTS], a.LOW_Z[0], down=True)
    p.cut(lambda s: [s.circle(x, 0, g.M3_CLEAR) for x in FA_INSERTS], -40.0, 40.0 + a.LOW_Z[0])
    return p.finish()


# ----------------------------------------------------------------------------- wrist + hand
# Nov 15-16 (team): the hand is the gripper's FLAT, STRAIGHT fingers + thumb (D21; built by
# build_gripper, saved into Arm Human/). Around them:
#   Wrist Bracket  rounded: the flange is one smooth teardrop from the horn disc to the plate
#   Wrist Cap      a round cap over the horn screws (the visible wrist "bone"); held by a dab of
#                  glue or a double-sided tape pad, prised off to reach the horn screws
#   Wrist Cuff     wraps the bracket plate + gripper servo, wrist to deck (as Nov 15)
#   Palm Cover     a rounded box over the deck, pinion and racks, with a lid; only the jaw
#                  stems come through (two slots), the fingers slide just above the lid
# Gripper frame: Z = approach, X = jaw travel, Y = across the jaws = the wrist axis.
# Bracket plate: x -40..9, y -26..12, z -22..-19.
CUFF_SECTIONS = [  # z: (xc, yc, half-x, half-y, n)
    (-24.0, (-15.5, -7.0, 30.0, 24.0, 6.0)),    # wrist: just round the bracket plate
    (-12.0, (-6.0, -3.0, 33.0, 22.0, 5.0)),     # servo body + the plate's two posts
    (-2.6, (0.0, 0.0, 40.0, 24.0, 10.0)),       # under the deck; same section as the palm cover
]
PALM_SECTIONS = [
    (-2.6, (0.0, 0.0, 40.0, 24.0, 10.0)),       # deck corners (35, 20) clear by ~1 mm
    (19.0, (0.0, 0.0, 40.0, 24.0, 10.0)),
    (24.4, (0.0, 0.0, 38.0, 22.0, 10.0)),       # rounded shoulder into the lid
]
LID = (g.COVER_LID_Z, 1.2)                      # z 22.6..23.8, just under the jaws (z 25)


def build_wrist_cuff(sw, top, front):
    p = g.Part(sw, "Wrist Cuff", folder=HUMAN_DIR)
    skin(p, "Front Plane", front, CUFF_SECTIONS)
    p.cut(lambda s: s.rect(-70.0, -70.0, 70.0, 70.0), -40.0, 40.0 - 22.3)   # flush with the plate's back
    p.cut(lambda s: s.rect(-70.0, -70.0, 70.0, 70.0), -2.7, 40.0)           # stop under the deck
    x0, y0, x1, y1 = e.PLATE
    back = superellipse(-12.3, -5.7, 29.3, 21.6, 5.5)      # the cuff's section at z -20, less a wall
    p.boss(lambda s: s.poly(back), -19.0 - T, T)
    p.cut(lambda s: s.rect(x0 - 0.4, y0 - 0.4, x1 + 0.4, y1 + 0.4), -19.0 - T - 0.1, T + 0.2)
    p.cut(lambda s: s.rect(-42.5, -28.5, -36.5, -22.5), -22.4, 3.5)          # plate + flange corner (1 mm margin)
    p.boss(lambda s: s.rect(-44.5, -11.0, -25.0, 11.0), -23.4, T)            # ears under the M3 heads
    p.cut(lambda s: [s.circle(-31.0, sy, g.M3_CLEAR) for sy in (6.0, -6.0)])
    p.side_cut(top, [("circle", -8.0, -14.0, 7.0)], mid=22.0, depth=14.0)    # gripper lead grommet
    return p.finish()


def build_palm_cover(sw, front):
    p = g.Part(sw, "Palm Cover", folder=HUMAN_DIR)
    skin(p, "Front Plane", front, PALM_SECTIONS)
    p.cut(lambda s: s.rect(-70.0, -70.0, 70.0, 70.0), LID[0] + LID[1], 40.0)
    lid = superellipse(0.0, 0.0, 38.4, 22.4, 10.0)
    p.boss(lambda s: s.poly(lid), LID[0], LID[1])
    # Slots for the two jaw stems over their whole travel (0.5 clearance all round)
    p.cut(lambda s: [s.rect(*sl) for sl in g.lid_slots()], LID[0] - 0.1, LID[1] + 0.2)
    p.cut(lambda s: [s.circle(x, y, g.M2_CLEAR) for x, y in g.COVER_POSTS], LID[0] - 0.1, LID[1] + 0.2)
    return p.finish()


# Wrist bracket frame (build_arm): W at the origin, z along the wrist axis; flange z -26..-23
# under the wrist servo's horn, plate x 17..20 (gripper z -22..-19), y -40..9 (gripper x).
def build_wrist_bracket(sw, side):
    p = g.Part(sw, "Wrist Bracket", folder=HUMAN_DIR)
    z_top = a.WRIST_HORN_TOP                           # -23
    z_bot = z_top - 3.0
    px, py = a.GRIPPER_POSTS
    x0, x1 = a.BRACKET_REACH - 3.0, a.BRACKET_REACH
    # One smooth teardrop flange: the horn disc + rounded corners at the plate's two ends
    flange = e.hull([(0.0, 0.0, 20.0), (x1 - 2.5, px - 9 + 2.5, 2.5), (x1 - 2.5, 9 - 2.5, 2.5)])
    p.boss(lambda s: s.poly(flange), z_bot, 3.0)
    p.boss(lambda s: s.rect(x0, px - 9, x1, 9), z_bot, (py + 6) - z_bot)
    p.cut(lambda s: [s.circle(0, 0, 5.5)] +
          [s.circle(0, sgn * r, 1.6) for r in a.HORN_PILOT_R for sgn in (1, -1)])
    side(p, [(px, +py), (px, -py)], a.M3)
    return p.finish()


def build_wrist_cap(sw):
    """Round cap on the flange's outer face over the horn screws: Ø42, 1.0 + a 0.8 step (a
    rounded look), clipped at x 16 so it stays out of the cuff."""
    p = g.Part(sw, "Wrist Cap", folder=HUMAN_DIR)
    z_out = a.WRIST_HORN_TOP - 3.0                     # flange's outer face, -26
    p.boss(lambda s: s.circle(0, 0, 42.0), z_out - 1.0, 1.0)
    p.boss(lambda s: s.circle(0, 0, 38.0), z_out - 1.8, 0.8)
    p.cut(lambda s: s.rect(16.0, -30.0, 30.0, 30.0))
    return p.finish()


def build_hand(sw, top, front):
    """Gripper parts (into Arm Human/, with the cover posts) + cuff + palm cover -> Hand.SLDASM,
    driven through the whole opening range and interference-checked."""
    keep = g.GRIPPER_DIR
    g.GRIPPER_DIR = HUMAN_DIR
    try:
        parts = g.build_all(sw, cover=False)       # the Palm Cover replaces the Gripper Cover
    finally:
        g.GRIPPER_DIR = keep
    built = {"Wrist Cuff": build_wrist_cuff(sw, top, front), "Palm Cover": build_palm_cover(sw, front)}
    parts["cuff"], parts["palm"] = built["Wrist Cuff"][0], built["Palm Cover"][0]
    hand, report = g.build_assembly(sw, parts, path=HUMAN_DIR / "Hand.SLDASM", extras=("cuff", "palm"))
    for opening, found in report:
        print(f"hand at {opening:4.1f} mm: {len(found)} interference(s) {found}")
    return hand, built


def close_ours(sw):
    d, titles = sw.GetFirstDocument, []
    while d:
        if str(g.OUT).lower() in (d.GetPathName or "").lower() or d.GetTitle.startswith("_probe"):
            titles.append(d.GetTitle)
        d = d.GetNext
    for t in titles:
        sw.QuitDoc(t)


# ----------------------------------------------------------------------------- main
def main():
    sw = w.Dispatch("SldWorks.Application")
    sw.Visible = True
    HUMAN_DIR.mkdir(parents=True, exist_ok=True)
    close_ours(sw)

    e.ENC_DIR = HUMAN_DIR                       # the shared pieces save into Arm Human/
    extras = {"Upper Arm": e.extra_upper_arm, "Crank": e.extra_crank, "Forearm": e.extra_forearm}

    def part_with_extras(sw_, name):
        p = g.Part(sw_, name, folder=HUMAN_DIR)
        orig = p.finish

        def finish():
            extras[name](p)
            return orig()
        p.finish = finish
        return p
    a.Part = part_with_extras

    top = g.probe_plane(sw, "Top Plane")
    right = g.probe_plane(sw, "Right Plane")
    front = g.probe_plane(sw, "Front Plane")
    hand, hand_parts = build_hand(sw, top, front)
    if "--hand" in sys.argv:                    # hand only: gripper + covers + Hand.SLDASM
        close_ours(sw)
        return
    side = a.make_side_holes(a.probe_right_plane(sw))
    built = {
        "Shoulder Bracket": e.copy_shoulder_bracket(sw),
        "Upper Arm": a.build_upper_arm(sw),
        "Crank": a.build_crank(sw),
        "Forearm": a.build_forearm(sw),
        "Shoulder Cap": e.build_shoulder_cap(sw),
        "Upper Arm Skin": build_upper_arm_skin(sw, right),
        "Forearm Skin": build_forearm_skin(sw, right, top),
        "Wrist Bracket": build_wrist_bracket(sw, side),
        "Wrist Cap": build_wrist_cap(sw),
        **hand_parts,
    }
    for n, (pth, vol) in built.items():
        print(f"{n:18s} {vol * 1.24:6.1f} g PLA   {vol:6.2f} cm3")

    P = lambda n: HUMAN_DIR / f"{n}.SLDPRT"
    O = lambda n: a.ARM_DIR / f"{n}.SLDPRT"
    spec = [
        ("Shoulder Bracket", P("Shoulder Bracket"), None),
        ("Shoulder Cap +z", P("Shoulder Cap"), None),
        ("Shoulder Cap -z", P("Shoulder Cap"), None),
        ("Upper Arm", P("Upper Arm"), "Upper Arm"),
        ("Upper Arm Skin", P("Upper Arm Skin"), "Upper Arm"),
        ("Crank", P("Crank"), "Crank"),
        ("Rod", O("Rod"), "Rod"),
        ("Forearm", P("Forearm"), "Forearm"),
        ("Forearm Skin", P("Forearm Skin"), "Forearm"),
        ("Elbow Spacer", O("Elbow Spacer"), "Elbow Spacer"),
        ("Wrist Bracket", P("Wrist Bracket"), "Wrist Bracket"),
        ("Wrist Cap", P("Wrist Cap"), "Wrist Bracket"),
        ("Gripper", hand, "Gripper"),          # Hand.SLDASM: gripper + jaws + cuff + palm cover
    ]
    asm, report = e.build_assembly(sw, spec, e.extra_poses(), name="Arm Human")
    bad = 0
    for label, ang, found in report:
        bad += bool(found)
        print(f"pose {label:30s} {tuple(round(v) for v in ang)}: {len(found)} interference(s) {found}")
    print("assembly:", asm, "| poses with interference:", bad)

    props = {}
    for key, path, follows in spec:
        if key in props or key.startswith("Shoulder"):
            continue
        props[key] = {**e.mass_props(sw, path), "frame": follows}
    for n in ("Wrist Cuff", "Palm Cover"):     # inside Hand.SLDASM already: density only
        props[n] = {**e.mass_props(sw, built[n][0]), "frame": "Gripper", "part_of": "Gripper"}
    (HUMAN_DIR / "mass_properties.json").write_text(json.dumps(props, indent=2))
    close_ours(sw)


if __name__ == "__main__":
    sys.exit(main())
