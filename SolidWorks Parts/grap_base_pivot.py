"""GRAP - rotating enclosure on a fixed base, 360 degree version (v3).

Run:  pip install cadquery   then   python grap_base_pivot.py
Makes STEP files (SolidWorks: File > Open > STEP):
  grap_base.step          fixed: plate + track + collar, M8 bolt head captured underneath
  grap_sun_gear.step      fixed: 16T gear clamped on the M8 pivot bolt, also stops the box lifting
  grap_planet_gear.step   on the servo horn: 36T gear that walks around the sun gear
  grap_servo_bridge.step  in the box: holds the MG996R shaft-down, off-centre
  grap_wheel_fork.step    in the box: one per slot, carries a 608 bearing
  grap_electronics_tier.step  tray that stacks on the box rim: the boards live here, above the wheels
  grap_lid.step           screws onto the tier; the arm's Shoulder Bracket bolts to it
  grap_lid_in_box_frame.step  the lid already positioned on the box (insert at the assembly origin)
  grap_mechanism.step     all of it in the Enclosure's own SolidWorks frame (insert the box at the origin)
  grap_assembly.step      the same plus a stand-in box
All dimensions in mm. Edit the numbers below and re-run.

How it turns: the sun gear is fixed to the base. The servo sits in the box with the planet gear
on its horn. Turning the servo walks the planet round the sun and carries the box with it.
Box angle = servo angle x (SUN_T / PLANET_T), so 160 deg of servo gives 360 deg of box.
"""
import math
import cadquery as cq

# ---- Measured from Enclosure.SLDPRT (Nov 10) ----
BOX_SIDE, BOX_WALL, BOX_FLOOR, BOX_H = 170.0, 5.0, 5.0, 65.0
BOSS_SIDE, BOSS_H = 50.0, 5.0
SLOT_R_IN, SLOT_R_OUT = 65.0, 75.0     # arc slots (read off the top view - CHECK)
SLOT_ANGLES = [0, 90, 180, 270]        # four 608 wheels; the box needs a 4th slot at 180 deg
BOX_HOLE_D = 22.2                      # centre hole MUST be opened up from 20 to this for the 608

# ---- Hardware ----
BRG_OD, BRG_W, BRG_ID = 22.0, 7.0, 8.0            # 608 bearing
BOLT_D, BOLT_HEAD_AF, BOLT_HEAD_H, BOLT_LEN = 8.0, 13.0, 5.3, 25.0   # M8 x 25 hex bolt
NUT_H = 6.5                                        # M8 nut
SERVO_L, SERVO_W, SERVO_CASE_H = 40.6, 19.9, 37.0  # MG996R
SERVO_SHAFT_OFFSET = 10.0              # shaft axis to the near end of the body
SERVO_TAB_FACE = 10.5                  # shaft-side case top down to the tab face - MEASURE
TAB_HOLES_L, TAB_HOLES_W = 49.0, 10.0
# Aluminium horn: 35 x 6 is from the sheet, the rest are GUESSES - MEASURE
HORN_LEN, HORN_T, HORN_W, HORN_HUB_D = 35.0, 6.0, 8.0, 13.0
HORN_SCREWS = [10.0, 20.0]             # screw positions along the arm - GUESS
HORN_TO_CASE = 1.5

# ---- Gears ----
MODULE, SUN_T, PLANET_T = 1.25, 16, 36
BACKLASH = 0.2
SERVO_DIR = 180.0                      # which side of the box the servo sits on, degrees
FIT = 0.3

# ---- Base ----
PLATE_D, PLATE_T = 200.0, 6.0
TRACK_R_IN, TRACK_R_OUT, TRACK_H = 60.0, 80.0, 3.0
WHEEL_GAP = 1.5
COLLAR_D = 20.0
MOUNT_HOLE_D, MOUNT_HOLE_R = 4.5, 92.0

# ---- Lid (carries the arm's Shoulder Bracket) ----
LID_T, LID_LIP_H, LID_LIP_W = 4.0, 3.0, 2.0
BOX_CORNER_R = 10.0                    # outer corner radius of the box
ARM_HOLES_X, ARM_HOLES_Y, ARM_HOLE_D = 40.0, 60.0, 3.4   # Shoulder Bracket: 4 holes, 40 x 60 (hole size ASSUMED M3)
LID_SCREW_D = 3.4                      # 4 x M3 down into the box wall corners (pilot holes needed in the box)
CABLE_HOLE_D, CABLE_HOLE_POS = 12.0, (0.0, 55.0)         # arm wiring down into the box

# ---- Electronics floor: a tray that stacks on the box rim, under the lid ----
TIER_H, TIER_DECK_T, TIER_WALL = 40.0, 3.0, 5.0
STANDOFF_H = 6.0
# Boards: name, centre (x, y) from the rotation axis, size (along x, along y), height above the
# standoffs incl. parts, mounting holes relative to the centre, pilot hole diameter.
# Hole patterns are typical module values - MEASURE yours and edit.
BOARDS = [
    ("pca9685",   (41.0, -38.0), (62.5, 25.4), 14.0, [(sx * 28.0, sy * 9.5) for sx in (1, -1) for sy in (1, -1)], 2.2),
    ("perfboard", (42.0, 30.0),  (70.0, 50.0), 25.0, [(sx * 33.0, sy * 23.0) for sx in (1, -1) for sy in (1, -1)], 1.8),
    ("lm2596",    (-50.0, -58.0), (43.2, 21.0), 14.0, [(-15.0, 7.5), (15.0, -7.5)], 2.6),
    ("nano",      (-56.0, 44.0), (43.2, 17.7), 8.0, [(sx * 20.3, sy * 7.6) for sx in (1, -1) for sy in (1, -1)], 1.6),
]
# Wall openings in the back wall (-x side), as (y centre, z centre above the tier bottom, width, height, round?)
BACK_OPENINGS = [(44.0, 13.0, 12.0, 8.0, False),    # Nano USB
                 (10.0, 13.0, 12.0, 7.0, False),    # USB-C power in (PD trigger)
                 (-20.0, 24.0, 20.0, 20.0, True)]   # rocker switch, about 19.4 mm body

# ---- Heights (z = 0 is the top of the base plate) ----
z_box_bottom = TRACK_H + WHEEL_GAP
z_floor_in = z_box_bottom + BOX_FLOOR
z_boss_top = z_floor_in + BOSS_H
z_collar = z_box_bottom - 0.5                  # bearing sits on this
z_brg_top = z_collar + BRG_W
z_sun_flange = z_boss_top + 0.5                # 0.5 mm lift stop above the boss
SUN_FLANGE_T, SUN_FACE = 1.5, 8.0
z_sun_top = z_sun_flange + SUN_FLANGE_T + SUN_FACE
z_head_seat = z_sun_top - BOLT_LEN             # bolt end flush with the sun gear top
z_planet = z_sun_flange + SUN_FLANGE_T + 0.5
PLANET_FACE, PLANET_PLATE, POCKET = SUN_FACE - 0.5, 4.5, 3.0
z_horn_bottom = z_planet + PLANET_FACE + 0.5 + PLANET_PLATE - POCKET
z_case_top = z_horn_bottom + HORN_T + HORN_TO_CASE
z_tab_face = z_case_top + SERVO_TAB_FACE
axle_h = BRG_OD / 2 - WHEEL_GAP - BOX_FLOOR
centre_dist = MODULE * (SUN_T + PLANET_T) / 2
servo_cx = -centre_dist + SERVO_L / 2 - SERVO_SHAFT_OFFSET   # body centre, servo on the -x side


def gear(teeth, face):
    """Spur gear, 20 deg involute, centred on the origin, tooth 0 on +x."""
    pa = math.radians(20)
    rp = MODULE * teeth / 2
    rb, ra, rf = rp * math.cos(pa), rp + MODULE, rp - 1.25 * MODULE
    half = math.pi / (2 * teeth) - BACKLASH / (4 * rp) + (math.tan(pa) - pa)
    t0 = math.sqrt(max((rf / rb) ** 2 - 1, 0))
    t1 = math.sqrt((ra / rb) ** 2 - 1)
    flank = []
    for k in range(9):
        t = t0 + (t1 - t0) * k / 8
        flank.append((rb * math.sqrt(1 + t * t), t - math.atan(t)))
    pts = []
    for i in range(teeth):
        c = 2 * math.pi * i / teeth
        side_a = [(r, c - half + a) for r, a in flank]
        side_b = [(r, c + half - a) for r, a in reversed(flank)]
        for r, a in [(rf, c - half)] + side_a + side_b + [(rf, c + half)]:
            pts.append((r * math.cos(a), r * math.sin(a)))
    return cq.Workplane("XY").polyline(pts).close().extrude(face), ra, rf


def horn_solid(grow, h):
    arm_end = HORN_LEN - HORN_HUB_D / 2
    return (cq.Workplane("XY").circle(HORN_HUB_D / 2 + grow).extrude(h)
            .union(cq.Workplane("XY").center(arm_end / 2, 0).rect(arm_end, HORN_W + 2 * grow).extrude(h))
            .union(cq.Workplane("XY").center(arm_end, 0).circle(HORN_W / 2 + grow).extrude(h)))


def base_part():
    b = cq.Workplane("XY").circle(PLATE_D / 2).extrude(-PLATE_T)
    b = b.union(cq.Workplane("XY").circle(TRACK_R_OUT).circle(TRACK_R_IN).extrude(TRACK_H))
    b = b.union(cq.Workplane("XY").circle(COLLAR_D / 2).extrude(z_collar))
    b = b.union(cq.Workplane("XY").workplane(offset=z_collar).circle(5.8).extrude(0.4))  # inner-race seat
    b = b.cut(cq.Workplane("XY").workplane(offset=-PLATE_T).circle(BOLT_D / 2 + 0.1).extrude(PLATE_T + z_collar + 1))
    b = b.cut(cq.Workplane("XY").workplane(offset=-PLATE_T)
              .polygon(6, (BOLT_HEAD_AF + 0.2) / math.cos(math.radians(30))).extrude(PLATE_T + z_head_seat))
    b = b.cut(cq.Workplane("XY").workplane(offset=-PLATE_T)
              .polarArray(MOUNT_HOLE_R, 45, 360, 4).circle(MOUNT_HOLE_D / 2).extrude(PLATE_T))
    return b


def sun_part():
    """Local z = 0 at the underside of the flange."""
    g, ra, rf = gear(SUN_T, SUN_FACE)
    s = cq.Workplane("XY").circle(15).extrude(SUN_FLANGE_T).union(g.translate((0, 0, SUN_FLANGE_T)))
    hub = z_sun_flange - (z_brg_top + 0.4)
    s = s.union(cq.Workplane("XY").circle(5.8).extrude(-hub))          # touches the inner race only
    s = s.cut(cq.Workplane("XY").workplane(offset=-hub).circle(BOLT_D / 2 + 0.1).extrude(hub + SUN_FLANGE_T + SUN_FACE))
    s = s.cut(cq.Workplane("XY").workplane(offset=SUN_FLANGE_T + SUN_FACE - NUT_H)
              .polygon(6, (BOLT_HEAD_AF + 0.2) / math.cos(math.radians(30))).extrude(NUT_H))
    return s


def planet_part():
    """Local z = 0 at the bottom of the teeth; servo shaft axis on the origin."""
    g, ra, rf = gear(PLANET_T, PLANET_FACE)
    p = g.union(cq.Workplane("XY").circle(rf).extrude(PLANET_FACE + 0.5))
    p = p.union(cq.Workplane("XY").workplane(offset=PLANET_FACE + 0.5).circle(ra).extrude(PLANET_PLATE))
    top = PLANET_FACE + 0.5 + PLANET_PLATE
    p = p.cut(horn_solid(FIT, POCKET).translate((0, 0, top - POCKET)))
    p = p.cut(cq.Workplane("XY").circle(3.3).extrude(top))             # access to the horn's centre screw
    p = p.cut(cq.Workplane("XY").pushPoints([(x, 0) for x in HORN_SCREWS]).circle(1.2).extrude(top))
    return p, ra


def bridge_part():
    """Local z = 0 at the box inside floor. Servo drops in from above, shaft down."""
    top = z_tab_face - z_floor_in
    x0, x1 = servo_cx - 32, servo_cx + 32
    y_in, y_out = 36.0, 40.0
    xm, lx = (x0 + x1) / 2, x1 - x0
    br = cq.Workplane("XY").workplane(offset=top - 4).center(xm, 0).rect(lx, 2 * y_out).extrude(4)
    for s in (1, -1):
        br = br.union(cq.Workplane("XY").center(xm, s * (y_in + y_out) / 2).rect(lx, y_out - y_in).extrude(top - 4))
        br = br.union(cq.Workplane("XY").center(xm, s * (y_out + 5)).rect(lx, 10).extrude(3))
        br = br.cut(cq.Workplane("XY").pushPoints([(x0 + 8, s * (y_out + 5)), (x1 - 8, s * (y_out + 5))])
                    .circle(1.7).extrude(3))
    br = br.cut(cq.Workplane("XY").workplane(offset=top - 4).center(servo_cx, 0)
                .rect(SERVO_L + 0.4, SERVO_W + 0.4).extrude(4))
    holes = [(servo_cx + sx * TAB_HOLES_L / 2, sy * TAB_HOLES_W / 2) for sx in (1, -1) for sy in (1, -1)]
    br = br.cut(cq.Workplane("XY").workplane(offset=top - 4).pushPoints(holes).circle(1.4).extrude(4))
    return br


def fork_part():
    """Local: wheel centre on the z axis, x = radial (outward), z = 0 at the inside floor."""
    h = axle_h + BRG_ID / 2 + 3
    r_mid = (SLOT_R_IN + SLOT_R_OUT) / 2
    in0, in1 = SLOT_R_IN - 6 - r_mid, SLOT_R_IN - r_mid
    out0, out1 = SLOT_R_OUT - r_mid, BOX_SIDE / 2 - BOX_WALL - 0.5 - r_mid
    f = cq.Workplane("XY").center((in0 + in1) / 2, 0).rect(in1 - in0, 30).extrude(h)
    f = f.union(cq.Workplane("XY").center((out0 + out1) / 2, 0).rect(out1 - out0, 30).extrude(h))
    for s in (1, -1):
        f = f.union(cq.Workplane("XY").center((in0 + out1) / 2, s * 13.5).rect(out1 - in0, 3).extrude(3))
    gap = (SLOT_R_OUT - SLOT_R_IN - BRG_W) / 2 - 0.2
    for x, d in ((in1, 1), (out0, -1)):
        f = f.union(cq.Workplane("YZ").workplane(offset=x).center(0, axle_h).circle(5.8).extrude(d * gap))
    f = f.cut(cq.Workplane("YZ").workplane(offset=in0 - 1).center(0, axle_h)
              .circle(BRG_ID / 2 + 0.1).extrude(out0 + 3 - in0 + 1))
    return f


def lid_part():
    """Local z = 0 at the lid underside (the box rim). Arm reaches along x."""
    inner = BOX_SIDE - 2 * BOX_WALL
    lid = (cq.Workplane("XY").rect(BOX_SIDE, BOX_SIDE).extrude(LID_T)
           .edges("|Z").fillet(BOX_CORNER_R))
    lip_out = (cq.Workplane("XY").rect(inner - 0.8, inner - 0.8).extrude(-LID_LIP_H)
               .edges("|Z").fillet(BOX_CORNER_R - BOX_WALL + 1))
    lip_in = cq.Workplane("XY").rect(inner - 0.8 - 2 * LID_LIP_W, inner - 0.8 - 2 * LID_LIP_W).extrude(-LID_LIP_H)
    lid = lid.union(lip_out.cut(lip_in))
    over = z_case_top + SERVO_CASE_H - (z_box_bottom + BOX_H)      # how far the servo pokes above the rim
    if over > -0.5 and TIER_H == 0:                               # relief pocket over the servo
        a = math.radians(SERVO_DIR - 180)
        pocket = (cq.Workplane("XY").center(servo_cx, 0).rect(SERVO_L + 3, SERVO_W + 3)
                  .extrude(min(over + 0.7, LID_T - 1.2)).rotate((0, 0, 0), (0, 0, 1), SERVO_DIR - 180))
        lid = lid.cut(pocket)
    pts = [(sx * ARM_HOLES_X / 2, sy * ARM_HOLES_Y / 2) for sx in (1, -1) for sy in (1, -1)]
    lid = lid.cut(cq.Workplane("XY").pushPoints(pts).circle(ARM_HOLE_D / 2).extrude(LID_T))
    c = BOX_SIDE / 2 - BOX_CORNER_R + (BOX_CORNER_R - BOX_WALL / 2) * math.cos(math.radians(45))
    lid = lid.cut(cq.Workplane("XY").pushPoints([(sx * c, sy * c) for sx in (1, -1) for sy in (1, -1)])
                  .circle(LID_SCREW_D / 2).extrude(LID_T))
    lid = lid.cut(cq.Workplane("XY").workplane(offset=-LID_LIP_H).center(*CABLE_HOLE_POS)
                  .circle(CABLE_HOLE_D / 2).extrude(LID_T + LID_LIP_H))
    return lid


def corner_points():
    c = BOX_SIDE / 2 - BOX_CORNER_R + (BOX_CORNER_R - BOX_WALL / 2) * math.cos(math.radians(45))
    return [(sx * c, sy * c) for sx in (1, -1) for sy in (1, -1)]


def tier_part():
    """Electronics tray. Local z = 0 at the box rim. Long M3 bolts go lid > tray > box corners."""
    inner = BOX_SIDE - 2 * TIER_WALL
    t = (cq.Workplane("XY").rect(BOX_SIDE, BOX_SIDE).extrude(TIER_H).edges("|Z").fillet(BOX_CORNER_R))
    t = t.cut(cq.Workplane("XY").workplane(offset=TIER_DECK_T).rect(inner, inner).extrude(TIER_H))
    lip_out = (cq.Workplane("XY").rect(BOX_SIDE - 2 * BOX_WALL - 0.8, BOX_SIDE - 2 * BOX_WALL - 0.8).extrude(-LID_LIP_H)
               .edges("|Z").fillet(BOX_CORNER_R - BOX_WALL + 1))
    lip_in = cq.Workplane("XY").rect(BOX_SIDE - 2 * BOX_WALL - 4.8, BOX_SIDE - 2 * BOX_WALL - 4.8).extrude(-LID_LIP_H)
    t = t.union(lip_out.cut(lip_in))
    t = t.union(cq.Workplane("XY").pushPoints(corner_points()).circle(4.5).extrude(TIER_H - LID_LIP_H - 0.3))
    t = t.cut(cq.Workplane("XY").workplane(offset=-LID_LIP_H).pushPoints(corner_points())
              .circle(LID_SCREW_D / 2).extrude(TIER_H + LID_LIP_H))
    # opening over the servo: its top and its cable come up through here
    t = t.cut(cq.Workplane("XY").workplane(offset=-LID_LIP_H).center(servo_cx, 0)
              .rect(SERVO_L + 6, SERVO_W + 6).extrude(TIER_DECK_T + LID_LIP_H)
              .rotate((0, 0, 0), (0, 0, 1), SERVO_DIR - 180))
    for name, (cx, cy), (lx, ly), h, holes, pilot in BOARDS:
        pts = [(cx + hx, cy + hy) for hx, hy in holes]
        so = cq.Workplane("XY").workplane(offset=TIER_DECK_T).pushPoints(pts).circle(3.0).extrude(STANDOFF_H)
        so = so.cut(cq.Workplane("XY").workplane(offset=TIER_DECK_T).pushPoints(pts).circle(pilot / 2).extrude(STANDOFF_H))
        t = t.union(so)
    hexes = [(x, TIER_DECK_T + (TIER_H - TIER_DECK_T) / 2) for x in (-44, -22, 0, 22, 44)]
    for side in (1, -1):        # hex vents on the two side walls
        v = (cq.Workplane("XZ").workplane(offset=-side * BOX_SIDE / 2 - side)
             .pushPoints(hexes).polygon(6, 18).extrude(side * (TIER_WALL + 2)))
        t = t.cut(v)
    for y, z, w, h, rnd in BACK_OPENINGS:
        wp = cq.Workplane("YZ").workplane(offset=-BOX_SIDE / 2 - 1).center(y, z)
        cut = wp.circle(w / 2) if rnd else wp.rect(w, h)
        t = t.cut(cut.extrude(TIER_WALL + 2))
    return t


def board_blocks():
    out = {}
    for name, (cx, cy), (lx, ly), h, holes, pilot in BOARDS:
        out[name] = (cq.Workplane("XY").workplane(offset=TIER_DECK_T + STANDOFF_H).center(cx, cy)
                     .rect(lx, ly).extrude(h))
    return out


def box_standin():
    b = cq.Workplane("XY").rect(BOX_SIDE, BOX_SIDE).extrude(BOX_H)
    b = b.cut(cq.Workplane("XY").workplane(offset=BOX_FLOOR)
              .rect(BOX_SIDE - 2 * BOX_WALL, BOX_SIDE - 2 * BOX_WALL).extrude(BOX_H))
    b = b.union(cq.Workplane("XY").workplane(offset=BOX_FLOOR).rect(BOSS_SIDE, BOSS_SIDE).extrude(BOSS_H))
    b = b.cut(cq.Workplane("XY").circle(BOX_HOLE_D / 2).extrude(BOX_FLOOR + BOSS_H))
    ring = cq.Workplane("XY").circle(SLOT_R_OUT).circle(SLOT_R_IN).extrude(BOX_FLOOR)
    tan30 = math.tan(math.radians(30))
    wedge = cq.Workplane("XY").polyline([(0, 0), (200, -200 * tan30), (200, 200 * tan30)]).close().extrude(BOX_FLOOR)
    slot = ring.intersect(wedge)
    for a in SLOT_ANGLES:
        b = b.cut(slot.rotate((0, 0, 0), (0, 0, 1), a))
    return b


def build(box_angle=0.0):
    """Returns (parts, fixed, moving) with the box turned to box_angle degrees."""
    Z = ((0, 0, 0), (0, 0, 1))
    r_mid = (SLOT_R_IN + SLOT_R_OUT) / 2
    base, sun, bridge, fork = base_part(), sun_part(), bridge_part(), fork_part()
    planet, planet_ra = planet_part()
    bolt = (cq.Workplane("XY").workplane(offset=z_head_seat).circle(BOLT_D / 2).extrude(BOLT_LEN)
            .union(cq.Workplane("XY").workplane(offset=z_head_seat - BOLT_HEAD_H)
                   .polygon(6, BOLT_HEAD_AF / math.cos(math.radians(30))).extrude(BOLT_HEAD_H)))
    brg = cq.Workplane("XY").workplane(offset=z_collar + 0.4).circle(BRG_OD / 2).circle(BRG_ID / 2).extrude(BRG_W)
    # sun: a tooth gap faces the planet (planet sits on -x before SERVO_DIR is applied)
    fixed = {"base": base, "pivot_bolt": bolt,
             "sun_gear": sun.rotate(*Z, 180 + 180 / SUN_T).translate((0, 0, z_sun_flange))}
    spin = box_angle * SUN_T / PLANET_T       # planet's extra turn about its own axis
    pc = (-centre_dist, 0, 0)
    top = PLANET_FACE + 0.5 + PLANET_PLATE
    planet_w = planet.rotate(*Z, spin).translate((pc[0], 0, z_planet))
    horn = horn_solid(0, HORN_T).rotate(*Z, spin).translate((pc[0], 0, z_horn_bottom))
    servo = (cq.Workplane("XY").workplane(offset=z_case_top).center(servo_cx, 0).rect(SERVO_L, SERVO_W).extrude(SERVO_CASE_H)
             .union(cq.Workplane("XY").workplane(offset=z_tab_face).center(servo_cx, 0).rect(SERVO_L + 14, SERVO_W).extrude(2.5)))
    carried = {"planet_gear": planet_w, "horn": horn, "servo": servo,
               "servo_bridge": bridge.translate((0, 0, z_floor_in))}
    turn = SERVO_DIR - 180 + box_angle
    moving = {n: s.rotate(*Z, turn) for n, s in carried.items()}
    moving["pivot_bearing"] = brg
    moving["box"] = box_standin().translate((0, 0, z_box_bottom)).rotate(*Z, box_angle)
    wheel = (cq.Workplane("YZ").workplane(offset=-BRG_W / 2).circle(BRG_OD / 2).circle(BRG_ID / 2)
             .extrude(BRG_W).translate((r_mid, 0, z_floor_in + axle_h)))
    for i, a in enumerate(SLOT_ANGLES):
        moving[f"fork{i}"] = fork.translate((r_mid, 0, z_floor_in)).rotate(*Z, a + box_angle)
        moving[f"wheel{i}"] = wheel.rotate(*Z, a + box_angle)
    moving["tier"] = tier_part().translate((0, 0, z_box_bottom + BOX_H)).rotate(*Z, box_angle)
    for n, b in board_blocks().items():
        moving[f"board_{n}"] = b.translate((0, 0, z_box_bottom + BOX_H)).rotate(*Z, box_angle)
    moving["lid"] = lid_part().translate((0, 0, z_box_bottom + BOX_H + TIER_H)).rotate(*Z, box_angle)
    parts = {"electronics_tier": tier_part(), "lid": lid_part(), "base": base, "sun_gear": sun, "planet_gear": planet, "servo_bridge": bridge, "wheel_fork": fork}
    return parts, fixed, moving


if __name__ == "__main__":
    parts, fixed, moving = build()
    for name, s in parts.items():
        cq.exporters.export(s, f"grap_{name}.step")
        bb = s.val().BoundingBox()
        print(f"{name}: {s.val().Volume() / 1000:.1f} cm3, {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, valid={s.val().isValid()}")

    # Assembly files use the Enclosure's SolidWorks frame: Y up, box corner on the origin, box bottom at Y = 0
    def to_sw(s):
        return (s.translate((0, 0, -z_box_bottom)).rotate((0, 0, 0), (1, 0, 0), -90)
                .translate((BOX_SIDE / 2, 0, -BOX_SIDE / 2)))

    lid_sw = to_sw(moving["lid"])
    cq.exporters.export(lid_sw, "grap_lid_in_box_frame.step")
    print(f"arm origin goes to X {BOX_SIDE / 2:.1f}, Y {BOX_H + TIER_H + LID_T + 2.5:.1f}, Z {-BOX_SIDE / 2:.1f} mm in the box frame "
          f"(Shoulder Bracket plate is 5 thick, centred on its origin)")
    for fname, with_box in (("grap_assembly.step", True), ("grap_mechanism.step", False)):
        asm = cq.Assembly()
        for n, s in fixed.items():
            asm.add(to_sw(s), name=n, color=cq.Color(0.6, 0.65, 0.7))
        for n, s in moving.items():
            if n == "box" and not with_box:
                continue
            asm.add(to_sw(s), name=n, color=cq.Color(0.9, 0.5, 0.3))
        asm.save(fname)
    ratio = PLANET_T / SUN_T
    print(f"gear ratio {ratio:.2f}: 360 deg of box needs {360 / ratio:.0f} deg of servo | centre distance {centre_dist:.2f}")
    print(f"servo tab face {z_tab_face - z_floor_in:.1f} above inside floor | "
          f"servo top {z_case_top + SERVO_CASE_H - z_box_bottom:.1f} vs box height {BOX_H:.0f}")
