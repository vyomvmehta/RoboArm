# Design Decisions

Format: **Decision**, then why, the alternatives considered, the date and who decided.

---

## D0: Project choice: gesture-controlled robot arm (2026-10-09, Vyom)

**Decision:** Build a 5-servo 3D-printed desktop arm controlled by hand gestures (see CLAUDE.md).

**Why:** The ball-balancing plate came to ~$90–215, which was over budget. The arm fits ~$80–95 total and reuses Vyom's MediaPipe gesture controller.

**Alternatives considered:**
- Ball-balancing plate: over budget.
- VEX IQ ball-and-beam (free hardware): only made sense as MTE coursework, and this is a personal project.

_Open decisions from the 2026-10-09 review: ownership balance, CAD tool (SolidWorks vs Fusion 360), joint support (idler bearings), DISARMED semantics, direct-drive vs four-bar._

---

## D1: Team of 3; Vyom owns software + firmware (2026-10-16, Vyom). Supersedes the 2-person split in CLAUDE.md.

- **Vyom:** software (vision, gestures, filter, mapping, IK, sim, modes, logging) **and firmware**; the protocol; the calibration code and file format.
- **Ishaan (Tron):** mechanical CAD, printing, assembly.
- **Siddharth (EE):** power electronics, wiring, KiCad board, physical calibration measurements, bench-test sketches.
- Torque analysis: all three do it, then compare. Open: who designs one SolidWorks part (depends on D3).
- **Risk:** Vyom has the heaviest software load plus midterms (Oct 21–27) and finals (Dec 10–22). Pressure valve: Siddharth writes the throwaway bench-test sketches and reviews the firmware.

## D2: Servo shortfall: MG996R "360°" are probably continuous-rotation (2026-10-16)

- **Status:** to be confirmed by a bench test when the parts arrive (Oct 20–27). Do **not** tap "Confirm received" before testing.
- **Plan:** order replacement positional (180°) MG996R now as insurance (Vyom's call, pending), decide by Nov 3 whether to buy from Amazon.ca if the order hasn't arrived.
- **Alternatives:** wait and test first (slower); rebuild the potentiometer in each servo (risky, for later); refund (not guaranteed, since the listing said 360°).

## D3: CAD tool: undecided (2026-10-16)

Waiting on Ishaan. Options: Fusion assembly + one SolidWorks part exported as STEP; all SolidWorks; all Fusion.

## D4: Servo power chain (2026-10-16, team plan; Claude's concerns recorded)

- **Chain:** Apple 96 W charger → USB-C PD trigger (9 V) → LM2596 set to 6.0 V → fuse → switch → PCA9685 V+ rail → servos.
- **Concerns:** LM2596 limited to about 3 A (2 A without a heatsink); four MG996R can exceed it. The 8 A fuse is too large. Must measure peak current before trusting it.
- **Fallback:** buy a certified 6 V ≥ 5 A supply (about C$20).

## D5: Minimal printing + shifted timeline (2026-10-16, Vyom)

- **Decision:** 3 print batches maximum: A (test coupon, ~$1), B (whole arm once, ≤ 300 g, ~$15–20), C (failed parts only, capped at ~$5). Measure real parts before designing. Design review by all three before Batch B. Laser-cut flat parts where possible, no TPU.
- **Why:** the budget is already exceeded (~C$130 on AliExpress). The team accepts a 1–2 week delay to save money. All three have midterms Oct 21–27.
- **Consequence:** demo-ready moves from early December to early January. See `docs/TIMELINE.md` v2.
- **Alternatives:** 5 iterative batches (v1 plan): faster learning, but costs ~2× in reprints.

## D6: Protocol design choices (2026-10-31, Vyom)

- **Checksum:** XOR of every byte before `*`, as 2 upper-case hex characters. *Alternatives:* CRC-8 (stronger, more code, hard to check by hand); none (in-range corrupted digits would get through).
- **DISARMED = limp** (no pulses) + a **park pose** the arm rests in safely when limp. Arming assumes the arm is at park; `D` moves to park through the limiter, then goes limp. *Why:* hobby servos give the Nano no position feedback, so after a reset it can't know the pose; any pulse would snap the joint at full speed. *Alternative:* hold on `D` (only works when the pose is known, never after a reset). **Mechanical requirement for Ishaan:** a stable limp park pose.
- **Auto-reset:** the Nano sends an `R` boot banner; the laptop waits up to 3 s for it before sending anything. *Alternative:* a 10 µF RESET capacitor (has to be removed for every upload).
- **Out-of-range pulse:** reject the whole frame, keep the previous target, reply `E,<seq>,3`. *Why:* the laptop already clamps to the workspace, so this only trips on bugs, which should show up loudly. *Alternative:* clamp (hides IK bugs).
- **Status:** v1 is agreed once Ishaan and Siddharth have read it.

## D7: 3-person plan details (2026-10-31, Vyom)

- **CAD tool: all SolidWorks** (resolves D3). Ishaan learns SolidWorks; Vyom's SolidWorks part is the **base turntable** (proposed, due Nov 12).
- **Servo replacement scope:** only the MG996R (J0–J2) need 180° replacements (3, plus 1 spare). The MG90S were ordered as 180° (fine). The SG90 aren't used, so no replacement.
- **Vyom's hours:** ~5–8 h/week (updated later on Oct 31; was 4–7). Vyom **keeps firmware** (D1). Fallback: Siddharth takes the laptop side of the protocol (`arm/comms`) if Vyom falls behind.
- **Kinematics code:** written by Claude at Vyom's request (`arm/kinematics/`, `tests/test_kinematics.py`, 10 tests), following Vyom's hand derivation. Credit for Claude goes in the README only (D9), not in commit lines.
- **Plan page:** https://claude.ai/artifact/FYa2ohKX7dTyKSVxJqvHiQ; `docs/TIMELINE.md` v3 mirrors it.
- **Assumption to confirm:** Ishaan and Siddharth at ~5–8 h/week each.

## D8: New split: everyone owns half of two areas (2026-10-31, agreed on a call by all three). Supersedes D1 and the role parts of D7.

| Area | First half | Second half |
| --- | --- | --- |
| Software | **Vyom:** laptop: vision/hand tracking, smoothing filter, mapping, IK (done), sim, gesture modes, logging/metrics | **Ishaan:** Arduino firmware (parser, states, watchdog, PCA9685, motion limiter), laptop↔Arduino comms (`arm/comms`), calibration code |
| Electronics | **Siddharth:** power chain (charger → PD trigger → LM2596 → fuse → switch → servo rail), power board, current measurement | **Ishaan:** signals: Nano ↔ PCA9685 hookup, pin map, servo cables/harness, servo test, calibration measurements |
| Mechanical | **Vyom:** SolidWorks of the arm links + base turntable, full assembly model, `config/arm.yaml`, test coupon + all printing | **Siddharth:** caliper measurement sheet, collects the torque estimates → arm size, gripper in SolidWorks, non-printed hardware, assembly + fit fixes |

- **Checks:** Vyom checks Ishaan's firmware and Siddharth's gripper. Ishaan checks Vyom's laptop code and Siddharth's power board. Siddharth checks Vyom's CAD before printing and Ishaan's signal wiring.
- **Why:** each person gets two areas (breadth for interviews) and every area has two people (no single point of failure).
- **Trade-offs:** Vyom gives up firmware (the embedded gap on the resume), but gains real SolidWorks + DFM + printing work. Ishaan implements the protocol Vyom designed (D6).
- Hours: all three ~5–8 h/week. Plan page: https://claude.ai/artifact/FYa2ohKX7dTyKSVxJqvHiQ (v3 has this split).
- **Update 2026-11-08 (swap):** Siddharth had already started the base (`SolidWorks Parts/Enclosure.SLDPRT`), so **Siddharth now owns the base enclosure + lid + turntable** and **Vyom owns the gripper**. Vyom keeps the arm links + shoulder bracket, the full assembly and printing. Checks swap with it: Vyom checks Siddharth's base, Siddharth checks Vyom's gripper and links.

## D9: Repository setup (2026-10-31, Vyom)

- **Public** GitHub repo `RoboArm` (vyomvmehta/RoboArm). Branch protection on `main` (PR + 1 approval, no force-push). Collaborators: Ishaan, Siddharth.
- **Not pushed (stays on Vyom's laptop):** `CLAUDE.md` and `docs/PROGRESS.md`. Pushed: README, PROTOCOL, TIMELINE, DECISIONS, CHECKLIST, code, tests.
- **Credit for Claude:** a "How we built this" section in the README only; **no Co-Authored-By lines** on commits.
- *Alternatives:* private until the demo (needs GitHub Pro for branch protection); sharing CLAUDE.md too.

## D10: V1 = interface control, V2 = gesture control (2026-10-31, team; Siddharth's idea)

- **V1 (the plan up to the January demo):** the arm is controlled from a **web page** served by the laptop. It opens in the laptop's browser or on a phone (over a hotspot, since UW eduroam often blocks phone→laptop connections). Two modes: **a slider per joint** (testing, calibration) and **point-and-go** (type a target x/y/z and the IK solves it). V1 demo: **live pick-and-place from the page** (no record/replay in V1).
- **V2 (later):** hand-gesture control (MediaPipe) as originally planned, swapping the web page for the camera as the input. Vyom starts V2 hand tracking early **only if V1 software is on track**.
- **Why:** removes the riskiest, least predictable part (single-camera depth, jitter, smoothing lag) from the critical path, so a working arm is far more likely by Dec 9. The laptop↔Arduino protocol, IK, calibration and firmware are identical in V1 and V2; only the input changes.
- **Alternatives:** gestures straight away (original plan; higher risk); a desktop-only window (simpler, but no phone control).
- **Trade-off:** "gesture-controlled" is only true once V2 ships. Until then the resume line is "web/phone-controlled 5-DOF arm with IK".

## D11: Finish V1 in November (2026-10-31, team)

- **Constraint:** finals run from about Dec 7 to Dec 20, then travel. From January, Ishaan and Siddharth are on co-op away from Waterloo; Vyom has a study term.
- **Decision:** compress V1 into November. V1 works by **Sun Nov 22**, demo video by **Sun Nov 29**, spare week to **Sun Dec 6** (hard stop). The arm stays with Vyom. January = Vyom solo: write-up + V2. See `docs/TIMELINE.md` v4.
- **What changes:** CAD in one week (review Sun Nov 8, was Nov 13). The whole arm printed Nov 9–12 (was Nov 16–20). Missing parts (incl. the MG996R replacements) bought on **Amazon.ca on Mon Nov 2** for speed instead of AliExpress. Build days Nov 14–15 and Nov 22. Hours: Vyom ~8–10, others ~6–8 h/week in November.
- **Cut order if behind:** phone support → point-and-go → a simpler gripper.
- **Alternative considered:** keep the Jan 10 target. Rejected: only Vyom will be in Waterloo after December.
- **Update 2026-11-05 (Vyom):** the demo video and write-up material move to **January** (Vyom, during the 1B term). The team's only goal before Dec 6 is a **working arm, as early as possible**; Nov 23 – Dec 6 becomes fix-and-harden time instead of demo time.

## D12: Torque estimate: one owner + one checker (2026-11-01, Vyom)

- **Decision:** Vyom does the shoulder-torque estimate (Claude checks the method and arithmetic); **Siddharth re-checks it against the real masses** from his measurement sheet. Replaces "all three do it independently".
- **Why:** saves two people ~30 min each in the busiest week. A check against measured masses still catches the riskiest errors (wrong inputs), which a method check alone wouldn't.
- **Alternative:** three independent estimates (stronger cross-check, more time).

## D13: Electronics inside the base (2026-11-01, Vyom; team to confirm on the Nov 2 call)

- **Decision:** the Nano, PCA9685, power board (LM2596, fuse, capacitor) and kill switch go **inside the arm's base**, which doubles as an enclosure. The links carry only the motors and their cables.
- **Why:** it's a portfolio piece, so it should look finished; a closed base also protects the boards and is easier to carry.
- **Requirements this creates** (for the cable and board plan and the base CAD):
  - **Access without taking the arm apart:** a bottom plate or side panel held by screws, so boards can be probed and re-plugged during the current measurement (Nov 18) and calibration (Nov 21).
  - **Openings:** kill switch on the front, within reach; USB-C to the Nano; the power cable in.
  - **Vent slots** beside the LM2596 (it gets warm under load).
  - **Cables** from the turntable into the base pass close to the rotation axis, with slack for the base's full rotation.
  - **Stability:** the stretched-out arm tries to tip the base, so give it a wide, heavy bottom (e.g. an MDF plate) that can be clamped or weighted.
- **Cost:** roughly 50–80 g of extra PLA (about $3–5) for the enclosure walls. Check against the ≤ 300 g batch B cap (D5) at the Nov 8 review; if it's over, make the bottom plate from MDF/plywood instead of printing it.
- **Alternatives:** boards on an open plate beside the base (cheaper, easiest to probe, no heat issue, but looks unfinished); boards on the arm (rejected: adds torque at the shoulder and wires flexing across joints).

## D14: Arm size 11 / 10 / 7 cm (2026-11-04, team)

> **ON HOLD (2026-11-05, team):** the team wants the arm as big as possible and is weighing (A) direct drive 11/10/7, (B) direct drive with a stronger shoulder servo, ~14/12/7, (C) a four-bar elbow, 13/12/7 to 17/16/7 depending on the measured MG996R stall torque (four-bar table in PROGRESS.md, Nov 5). Parts get tested first (servo stall torque, LM2596 stall test, PD trigger). The CAD waits for this decision; every day of waiting moves V1 by about a day.

- **Decision:** upper arm (shoulder → elbow axis) **110 mm**, forearm (elbow → wrist axis) **100 mm**, wrist axis → grasp point **70 mm**. Direct-drive elbow (no four-bar). `config/arm.yaml` uses these.
- **Why:** every joint holds the worst case (arm stretched flat, 30 g block) well inside the 50 % rule: shoulder 34 % of MG996R stall (49 % even if the clones are 30 % weak), elbow 13 %, wrist 18 % of MG90S stall ([TORQUE.md](TORQUE.md)). It picks a block straight down anywhere about 90–210 mm from the base axis, and the demo layout is flexible (we fit the block and target zone inside that ring later).
- **Alternatives:** 10 / 9 / 7 (≈ 32 % shoulder, reach ~205 mm: a bit more precise, less reach); 12 / 11 / 7 (≈ 37 %, reach ~245 mm: more sag and tip error, more plastic). Four-bar elbow (less shoulder torque, but more parts and IK changes; not needed at 34 %).
- **Re-check** with the SolidWorks masses at the Nov 8 review.

## D15: Print clearances from the test print (2026-11-03, Vyom; provisional until the two checks below)

Batch A (screw strip + bearing block), printed on a **Bambu Lab P2S, Bambu PLA Basic (black), default profile** (0.4 mm nozzle, 0.2 mm layers). Measured with calipers by Vyom + Siddharth. **Valid for this printer, filament and profile only**: print batch B the same way.

| Feature | Drawn (mm) | Measured (mm) | Fit | Use |
| --- | --- | --- | --- | --- |
| M3 hole | 3.0 / 3.2 / 3.4 | 2.79 / 2.90 / 3.2–3.4 (oval) | screw test still to do | **Draw 3.45** (Vyom: 3.4 came out 3.2 × 3.4, nearly enough; more risks a loose fit) |
| M3 nut pocket (across flats) | 5.6 / 5.8 / 6.0 | 5.54 / 5.80 / 5.97 | 5.6: drops in, doesn't spin (falls out); 5.8 spins slightly; 6.0 spins | **Draw 5.6** |
| M3 nut pocket depth | 2.6 | 2.6–2.7 | nut sticks up in all three | **Nut thickness + 0.3** (measure the nut) |
| 608 seat | 22.0 / 22.2 / 22.4 | 21.97 / 22.07 / 22.32 | 22.0: firm press, hard to remove; 22.2: stays in, easy to remove; 22.4: drops through. Bearing spins freely in both | **22.0** where the bearing stays in for good; **22.2** where it must come out |

- **Lesson:** shrinkage depends on size. Small holes lost 0.2–0.3 mm; the 22 mm seats and the hexagons lost only about 0.03–0.1 mm. One global "add 0.2 mm" rule would have been wrong for both. (Before printing, Claude predicted 22.2 would be the press fit; it was 22.0.)
- **Still to check:** (1) push a real M3 screw through the 3.4 hole (borrowed from RidgidWare); if it slides, 3.45 has a little margin; (2) measure the nut's thickness to set the pocket depth.
- **Motor pockets (frames, tested 2026-11-04 by feel, no calipers):** pocket = body + clearance, 5 mm plate, motor pushed in bottom-first until the tabs rest on the plate.

  | Motor (body) | +0.10 pocket | Use |
  | --- | --- | --- |
  | MG996R (19.8 × 40.5) | firm fit, no wiggle, stays in upside down | **Draw 19.9 × 40.6** (+0.10). Also confirms the 40.5 length (the sheet's 39.3 is another dimension). |
  | MG90S (11.9 × 22.8) | goes in, stays in upside down, some wiggle, pushes out easily | **Draw 11.9 × 22.8** (+0.00), untested; the tab screws hold it anyway |

  - **The cables jam.** The wires leave the bottom of one end face and have nowhere to go in a closed pocket. Every motor pocket gets a **cable slot** in the wall at the cable end, running the full depth of the pocket: about 6 mm wide for the MG996R and 4 mm for the MG90S (check with a ruler across the cable exit).
- **Servo mounting dimensions (Nov 8, team; match the published drawings; spot-check tab span + hole spacing on a real servo):**

  | | MG996R | MG90S |
  | --- | --- | --- |
  | Tab span, tip to tip | 54.0 | 32.2 |
  | Body bottom → underside of tabs | 26.8 | 16.0 |
  | Tab hole | 4.4 (no grommet/eyelet) | 2.0 |
  | Hole spacing along × across (centre-centre) | 49.0 × 10.0 (2 holes per tab) | 27.5 (1 hole per tab) |
  | Shaft centre → nearest body end | 10.5 | 5.6 |

  - MG996R: skip the rubber grommets and brass eyelets (rubber lets the motor wobble). M3 screws through the 4.4 tab holes into captive M3 nuts; printed holes 3.45. The pocket locates the motor; the screws only clamp it.
  - MG90S: M2 screws. Printed clearance hole about 2.4 mm (small holes print 0.2–0.3 mm undersize, D15), or 1.7–1.8 mm if using self-tapping M2 screws into the plastic.
- The motor-arm recess is still untested.

## D16: Servo power from the Apple 96 W charger at 15 V; try the LM2596 first (2026-11-03, Vyom + Siddharth). Updates D4.

- **Chain:** Apple 96 W USB-C charger → USB-C PD trigger (ZY12PDN) set to **15 V** → **LM2596** set to **6.0 V** → **5 A slow-blow fuse** → kill switch → motor rail (2200 µF / 16 V) → PCA9685 V+. Nano powered from the laptop's USB; all grounds tied.
- **Why 15 V:** at 9 V the charger offers only 3 A (27 W, roughly 3.8 A at 6 V); at 15 V it offers 45 W, plenty for the arm's realistic 3–5 A peaks at 6 V.
- **Why the LM2596 first:** we already own it. It's good for about 2 A continuous (3 A peak, with a heatsink), and the chip has its own current limit and thermal shutdown. **Test it** on the power board (one MG996R held stalled for 1–2 s) and at the Nov 18 current measurement. **If it sags, gets too hot or cuts out, switch to an XL4015 5 A CC/CV module** (about $5–8).
- **Fuse:** 5 A slow-blow, protecting the wiring against shorts (the LM2596 limits itself). The 8 A fuses we own are being returned.
- **Risk:** if the arm pulls more than the charger agreed to, a PD charger cuts power briefly (motors limp, then a jump when it returns). While the charger runs the arm, the laptop runs on battery.
- **Alternatives:** buy the XL4015 now (more margin, about $6, but delivery lead time); a 6 V ≥ 5 A barrel supply (simplest); the original 9 V trigger (marginal).

**Update 2026-11-04 (team, while ordering).** AliExpress shipping was too expensive, so the order moved to Amazon.ca (Prime):

- **PD trigger:** a DIP-switch USB-C PD trigger board (5/9/12/15/20 V, USB-C socket input) from Amazon.ca instead of the ZY12PDN, set to **15 V**. **Arrives by Nov 6.** Check 15 V with a multimeter before connecting anything; if it reads 9 V or 5 V, try another USB-C cable.
- **Fuse: use the 8 A fuses we already own** (3.6 × 10 mm, wire leads), soldered straight onto the power board between the converter and the kill switch. No holder, no 5 A fuses, no return. Why it's acceptable: the charger supplies at most 3 A at 15 V and the LM2596 limits itself at about 3 A, so even a 5 A fuse would almost never blow. The fuse is the last line of defence against a dead short in the wiring after the converter, and 8 A still blows before 18 AWG wire overheats. Revisit if we switch to a supply that can deliver 5 A or more (or set the XL4015's current-limit knob to about 4.5 A).
- **XL4015: not bought.** On Amazon.ca it arrived Nov 14–20 for about $15 with shipping: too slow to help and too expensive as an idle spare. Instead:
  1. **Test the LM2596 this week** on a bench supply (15 V, 2 A limit): set 6.0 V first, then hold one MG996R stalled 1–2 s. Pass = stays above about 5.5 V, warm but touchable, never cuts out.
  2. **If it sags:** run the motors gently (the motion limiter ramps speed; the web page can move one joint at a time). Normal motion draws about 0.2–0.5 A per motor holding and 0.5–1 A moving; peaks come from several MG996Rs starting together.
  3. **If it dies:** set the PD trigger to **5 V** and power the motor rail directly (no converter). Still capped at 3 A; the MG996R loses torque (about 9.4 instead of 11 kg·cm stall), so the shoulder runs at about 34 % of stall instead of 29 %, still under the 50 % rule.
  4. **For the demo:** a borrowed bench supply (6 V, 5 A limit) removes any doubt.
  5. Ask RidgidWare whether they sell a buck converter module; buy one only if it's a few dollars.
- **Heatsink** for the LM2596 from RidgidWare (cheapest way to raise its sustained current).

**Test result 2026-11-08 (no meter yet):** trigger at 9 V, LM2596 at 6.0 V; one MG996R (360° version, used as a load) stalled by hand for 1–2 s through the PCA9685: no cut-out, LM2596 not warm. Provisional **pass**; still to read the output voltage during a stall with a multimeter.
