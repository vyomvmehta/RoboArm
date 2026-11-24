# Base assembly — the rotating enclosure

Created 2026-11-24 by Claude for Vyom. Covers the turntable base only: base plate, pivot, sun and
planet gears, servo bridge, four wheel forks, lid. The arm above it is D19 and D21; the handoff
between them is step 8.

Every height here is computed from `SolidWorks Parts/Base/grap_base_pivot.py`, measured from the
**top of the base plate**. Fastener sizes and counts are in [HARDWARE.md](HARDWARE.md) — buy
before starting. Three things are still open; each appears at the step where it bites, marked
**OPEN**.

**How it turns.** The sun gear is bolted to the base and never moves. The servo rides inside the
box with the 36T planet gear on its horn, so turning the servo walks the planet around the fixed
16T sun and carries the whole box with it. Ratio 2.25, so **160° of servo gives 360° of box**.

## Parts

From **Plate 11**: base plate, servo bridge, planet gear, 1 wheel fork.
From **Plate 12**: lid, 3 wheel forks, sun gear.
Already printed: Siddharth's `Enclosure` (the box itself).
Bought: 1 MG996R, 6 × 608ZZ, M8 × 25 bolt + nut, 4 wheel axles, the screws in HARDWARE.md §3–4.

> `Base box.SLDPRT` in `Full Assembly` is the script's simplified stand-in, **not** Siddharth's
> real Enclosure. Do not take any dimension off it. The suppression step in `rebuild_base.py`
> looks for a component named `box_*` while the STEP exports `box.step`, so it has been silently
> skipping — a known bug, not something to fix mid-assembly.

## 1. Prepare the box

- [ ] **Open the centre hole from 20 to Ø22.2.** The 608's outer race seats in it and 20 will not
      take it. 22.2 is the UltiMaker fit measured Nov 20 — 22.0 was too tight, 22.4 dropped out.
- [ ] Check there are **four wheel slots**, at 0°, 90°, 180° and 270°, each spanning radius
      65–75. Early versions had three; the fourth was added for the 180° position.
- [ ] Check the **12 floor pilots**: 2.5 mm Ø, 4.5 deep, blind. Eight for the wheel forks at
      radius 55.5, ±13.5 either side of each slot centreline; four for the servo bridge.
- [ ] **OPEN — the bridge's four pilots may be 2 mm out.** `SERVO_SHAFT_OFFSET` changed from 10.0
      to 8.0 on Nov 22 and carried the bridge with it. Offer the bridge up dry before trusting
      them; if they miss, drill fresh ones and ignore the originals. The fork pilots are
      unaffected.
- [ ] Confirm the pilots are **blind**. Nothing may poke through the 5 mm floor — the underside
      runs on the track.

## 2. Pivot: bolt, bearing, sun gear

This is the load path that holds the box down and lets it turn. Build it in this order, or the
bearing ends up clamped on both races.

- [ ] **M8 × 25 bolt up through the base plate from underneath**, head into the hex pocket in the
      plate's underside. The head seat is at −0.5; the bolt's far end lands flush with the top of
      the sun gear.
- [ ] **608 over the bolt**, resting on the Ø11.6 pad on top of the Ø20 collar (z 4.4 to 11.4).
      It touches the **inner race only** — that is what the pad is for.
- [ ] **Lower the box onto the bearing** so its Ø22.2 centre boss captures the **outer** race, and
      its four slots sit over the track at radius 60–80.
- [ ] **Sun gear down over the bolt.** Its hub reaches down to 11.4 and presses the inner race;
      its Ø30 flange sits at 15.0, half a millimetre above the box's inner boss at 14.5. That
      0.5 mm is the lift stop — the sun gear is what stops the box climbing off the base.
- [ ] **M8 nut into the pocket inside the sun gear** and tighten.
- [ ] **Check:** the box turns by hand, smoothly, all the way round, with no more than about
      0.5 mm of vertical play. If it binds, something is clamping both races — check that the box
      boss is on the outer race and nothing else touches it.

## 3. Wheels and forks

The wheels carry the box's weight; the pivot only centres it and holds it down. **The forks must
be screwed down** — the box stands on them.

- [ ] Assemble each fork: 608 between the rails, axle pushed in **from the inside**. The wheel
      centre ends up 4.5 above the inside floor.
- [ ] **OPEN — the axle is not in the CAD.** The fork is bored 8.2 through both rails and the
      assembly shows a bare bearing with nothing through it. The bore is blind 1.5 mm short of the
      outer face, so no nut can go on: it takes a 19 mm plain 8 mm dowel from the inside, or an
      M8 × 20 with its head on the inner rail and nothing retaining the far end. Decide before
      fitting all four — a dowel beats a thread running in the race.
- [ ] Screw all four forks down, **2 × M3 × 8 each**, through the side tabs at radius 55.5.
- [ ] **Check:** every wheel touches the track and turns. Spin the box — it should coast slightly,
      not grind. One fork sitting proud puts the whole load on three wheels.

## 4. Servo bridge and the MG996R

- [ ] Screw the bridge to the floor, **4 × M3 × 6**. **Not 8** — the floor is 5 thick and the
      pilot 4.5 deep, so an 8 would jack the foot up or burst out underneath.
- [ ] **Centre the servo before it goes in:** power it and hold **1475 µs**. Fitting the horn at
      any other position throws the travel off centre, and you lose one end of the rotation.

> **1475, not 1500.** `config/arm.yaml` line 79 still says to fit horns at 1500 µs. It is stale:
> `config/calibration.yaml` sets `center_us: 1475` for every joint, `j0_base` included, and says
> so explicitly — 1475 is the servos' measured mid-travel. Use 1475.
- [ ] Drop the MG996R into the bridge pocket **shaft down**, 4 tab screws (its own, from the bag).
      The pocket locates it; the screws only clamp it.
- [ ] **Check:** the shaft-side case top sits at 35.0 and the tab face at 44.0. The bridge is
      34.5 tall — the tallest part on Plate 11.
- [ ] **Check:** the servo's top lands at 72.0 against a box rim at 74.5, so it clears by
      **2.5 mm**. If it stands proud, the height chain is wrong — stop and re-measure rather than
      forcing the lid on.

## 5. Planet gear onto the horn

- [ ] Drop the aluminium turntable horn into the pocket in the planet gear's top plate. Hub Ø14.0,
      blade 6.0 wide, pocket 2.0 deep.
- [ ] **OPEN — the pocket depth is a bound, not a measurement.** The blade thickness has never
      been measured; 2.0 is at or under every plausible blade, so the horn may stand slightly
      proud. That is fine — it only engages less. If the horn **rocks**, the pocket is too shallow
      for the blade: deepen it and reprint the planet gear alone, nothing else.
- [ ] **One M3 × 10 through the horn's inner hole** (20.0 from the hub centre) into the 2.4 mm tap
      hole in the plate.
- [ ] **OPEN — the outer horn screw has nothing under it.** The plate stops at radius 23.75 and
      that screw sits at 25.0. One screw plus the pocket's side faces is enough to test the
      turntable, but it is not the final answer. Growing the plate to about radius 27 fixes it and
      is a reprint of one small part; it would then sit over the sun gear with 0.5 mm clearance.
- [ ] **Horn onto the servo spline**, with the servo's own centre screw, driven through the Ø6.6
      access hole in the planet gear.
- [ ] **Check:** the planet's teeth start at 17.0 and the horn's underside at 27.5. Centre
      distance to the sun is 32.5 — the two gears should mesh with a trace of backlash, not bind.

## 6. First turn — before the lid goes on

- [ ] By hand, servo unpowered: push the box through a full turn. All 36 planet teeth and all 16
      sun teeth should pass without a tight spot.
- [ ] Under power: from 1475 µs, sweep slowly. **160° of servo = 360° of box.** An MG996R's 180°
      is more than a full turn of the box, so the firmware limiter has to hold it — do not go
      looking for the end stops by driving into them.
- [ ] **Check the cables.** USB and power come in through the back wall and have to wrap once
      fully around the base. Leave them slack there before anything is closed up.

## 7. Lid

The electronics tier is **not** printed (Plate 10 waits on the four board hole patterns), so the
lid goes straight onto the box rim.

- [ ] Lid down on the rim, **4 × M3 × 16** into the box's corner pilots, 5.43 mm in from each
      outer face on the diagonal.
- [ ] **Check:** the lid's lip drops inside the box walls without fouling the R10 inside corners.
- [ ] **Later, if the tier gets printed:** these become **4 × M3 × 50**, running
      lid → tray → box corner, and the lid rises 40 mm.

## 8. Arm interface

- [ ] Shoulder Bracket onto the lid: **4 × M3 × 16 + 4 M3 nuts**, on the 40 × 60 pattern.
- [ ] Thread both shoulder servo cables down through the two Ø12 holes in the lid, one per side,
      55 mm either side of the axis.
- [ ] **Check:** with no tier, the lid's top face is **74.0** above the box bottom and the arm's
      origin lands at **76.5**. With the tier those become 114.0 and 116.5.

> **Without the tier the shoulder sits 40 mm low. `arm.yaml` now says so — see D28.**
> It used to carry `shoulder_height: 174.5` and `plate_top_below_shoulder: 168.5`, both of which
> included the 40 mm tray. Corrected on Nov 24 to **134.5** and **128.5**, the build you are
> actually making. The cost is one pose: **"near"** (shoulder 24, forearm −80, wrist −10) was
> clear in the Nov 17 CAD check and is now refused, because the palm cover comes within about
> 2.5 mm of the fixed base plate. Fit a **40 mm spacer under the Shoulder Bracket** if you want
> that pose back — it restores exactly the geometry the CAD check validated. Do not widen the
> clearance margin.

## 9. What is not covered here

The arm, gripper and wrist are a separate build: shoulder servos and captive nuts into the
bracket, crank onto the elbow horn, the four-bar rod, the 608 elbow, the wrist MG90S and the
gripper. The order for those is in [DECISIONS.md](DECISIONS.md) under D19 and D21, and the
fasteners are in HARDWARE.md §2–4.
