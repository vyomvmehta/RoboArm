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

- **Public** GitHub repo `gesture-robot-arm` (vyomvmehta). Branch protection on `main` (PR + 1 approval, no force-push). Collaborators: Ishaan, Siddharth.
- **Not pushed (stays on Vyom's laptop):** `CLAUDE.md` and `docs/PROGRESS.md`. Pushed: README, PROTOCOL, TIMELINE, DECISIONS, CHECKLIST, code, tests.
- **Credit for Claude:** a "How we built this" section in the README only; **no Co-Authored-By lines** on commits.
- *Alternatives:* private until the demo (needs GitHub Pro for branch protection); sharing CLAUDE.md too.
