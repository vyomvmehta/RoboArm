# Waiting on the team: buy / check when everyone is together

Created 2026-10-16. Shared team checklist: tick items off as they're done.

## Decide together (needs Ishaan)

- [x] **CAD tool:** all SolidWorks (D7)
- [ ] **Replacement servos:** approve 3× MG996R 180° (about C$20–30, split 3 ways) (D2)
- [x] **Role split:** half of two areas each (D8)
- [ ] Each person writes their goals and background in `CLAUDE.md` §2
- [x] Credit for AI help: README section only (D9)

## To buy (about C$25–35 total, plus printing)

- [ ] 3× MG996R **180°** servos (check the variant says 180°, not 360°)
- [ ] **USB-C PD trigger module, 9 V** (for the Apple 96 W charger)
- [ ] **Fuse holder** for the 3.6×10 mm glass fuses, and a **3–4 A fuse** (the 8 A one in the order is too big)
- [ ] **Servo extension cables** (~30 cm) for the wrist and gripper
- [ ] **M3 and M2 screws**, if the order lacks them (only M3 nuts were visible)
- [ ] Printing at the Rapid Prototyping Centre (E5-2002): ~C$25 PLA/TPU
- [ ] *Fallback only:* certified 6 V ≥ 5 A supply (~C$20, Amazon.ca), if the LM2596 peak current measures above ~2.5 A

## To check

- [ ] **When the AliExpress parts arrive (Oct 20–27): do NOT tap "Confirm received" until the servo test is done.**
- [ ] **Servo test:** power one MG996R at ~5 V and write 0° → 90° → 180°. It must stop at each angle. If it keeps spinning, it is continuous-rotation (D2).
- [ ] **LM2596:** set the output to **6.0 V with a multimeter BEFORE connecting any servo.**
- [ ] **Apple 96 W charger:** read the label for its USB-C PD voltages (expected 5/9/15/20 V) before buying the trigger.
- [ ] **PCA9685 board:** check how much current its V+ path can carry (Siddharth).
- [ ] **Measure peak current** on a bench supply with a current display (UWFE or an EE lab) with the arm moving (D4).
- [ ] **Power wiring:** use thick wire (~18–20 AWG) for the servo trunk. The 22 AWG cable is for signals and short runs.
- [ ] **Torque calculation:** each of the three does it independently, then compare.
- [ ] **Protocol:** Ishaan + Siddharth read `docs/PROTOCOL.md` draft v1 and agree, especially the park-pose requirement
- [x] **Repo (2026-10-31):** public `vyomvmehta/RoboArm`, `main` protected (PR + 1 approval, no force-push). Ishaan + Siddharth invited.
- [ ] Parts arrived? Confirm that every ordered item arrived and nothing was left out.

## Deadlines

- **Nov 3:** if the replacement servos haven't arrived, buy them on Amazon.ca.
- **Oct 21–27:** midterms for all three (Vyom, Ishaan, Siddharth). **Dec 10–22:** finals.

## Next session (was Sat Oct 17, done Oct 31)

- [x] **Protocol (2026-10-31):** went through Claude's 4 choices in `docs/PROTOCOL.md` (checksum, DISARMED = limp + park pose, boot banner, reject out-of-range frames)
- [x] **IK walkthrough (done 2026-10-31):** Steps 1–3 (FK, elbow via law of cosines, shoulder via atan2), test target r = 180, z = 60 with L1 = L2 = 120 mm
- [ ] Ask WATiMake whether printing is cheaper/free for MME students
