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

## D15: Print clearances from the test print (2026-11-03, Vyom; provisional until the two checks below)

Batch A (screw strip + bearing block), printed at the RPC. Measured with calipers by Vyom + Siddharth. **Valid for this printer and these settings only**: ask for the same printer for batch B.

| Feature | Drawn (mm) | Measured (mm) | Fit | Use |
| --- | --- | --- | --- | --- |
| M3 hole | 3.0 / 3.2 / 3.4 | 2.79 / 2.90 / 3.2–3.4 (oval) | screw test still to do | **Draw 3.45** (Vyom: 3.4 came out 3.2 × 3.4, nearly enough; more risks a loose fit) |
| M3 nut pocket (across flats) | 5.6 / 5.8 / 6.0 | 5.54 / 5.80 / 5.97 | 5.6: drops in, doesn't spin (falls out); 5.8 spins slightly; 6.0 spins | **Draw 5.6** |
| M3 nut pocket depth | 2.6 | 2.6–2.7 | nut sticks up in all three | **Nut thickness + 0.3** (measure the nut) |
| 608 seat | 22.0 / 22.2 / 22.4 | 21.97 / 22.07 / 22.32 | 22.0: firm press, hard to remove; 22.2: stays in, easy to remove; 22.4: drops through. Bearing spins freely in both | **22.0** where the bearing stays in for good; **22.2** where it must come out |

- **Lesson:** shrinkage depends on size. Small holes lost 0.2–0.3 mm; the 22 mm seats and the hexagons lost only about 0.03–0.1 mm. One global "add 0.2 mm" rule would have been wrong for both. (Before printing, Claude predicted 22.2 would be the press fit; it was 22.0.)
- **Still to check:** (1) push a real M3 screw through the 3.4 hole (borrowed from RidgidWare); if it slides, 3.45 has a little margin; (2) measure the nut's thickness to set the pocket depth.
- Motor pockets and the motor-arm recess are still untested (frames pending the caliper numbers).
