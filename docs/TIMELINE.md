# Timeline v3 (2026-10-31): 3-person plan

> **Owners changed later on Oct 31 (D8):** Vyom = laptop software + links/base CAD + printing; Ishaan = Arduino software + signal wiring + calibration; Siddharth = power + measurements/arm size + gripper CAD + assembly. The plan page has the per-date owners; the dates below are unchanged.

The shareable version (with the owner cards and handoffs) is the team plan page: https://claude.ai/artifact/FYa2ohKX7dTyKSVxJqvHiQ
Keep this file and that page in sync.

**What changed from v2:**
- All SolidWorks.
- Vyom is at ~5–8 h/week (updated Oct 31) and keeps firmware. Siddharth takes the laptop side of the protocol as a fallback.
- Vyom's SolidWorks part is the base turntable.
- Ishaan's and Siddharth's ~5–8 h/week is an assumption to confirm.

## Key dates

- **Tue Nov 3:** replacement MG996R (180°) ordered; link lengths agreed (torque check by all three)
- **Wed Nov 4:** `config/arm.yaml` v0 (link lengths, joint limits, park + home poses), from Ishaan
- **Sun Nov 8:** pin map and power-on order from Siddharth; firmware v0 to Siddharth for review
- **Thu Nov 12:** Vyom's base turntable part; power board/switch mounting + cable routing agreed (Ishaan ↔ Siddharth)
- **Fri Nov 13:** design review (all three) → STL export by Sun Nov 15
- **Mon–Fri Nov 16–20:** print Batch B (the whole arm)
- **Sat Nov 28:** calibration measurements from Siddharth
- **Wed Dec 9:** live gesture control (mimic mode)
- **Dec 10–22:** finals, paused
- **~Sat Jan 10:** pick-and-place demo, video, README, resume bullets

## Week by week

| Dates | Vyom | Ishaan | Siddharth | Done by the end |
| --- | --- | --- | --- | --- |
| Oct 31 – Nov 1 | Torque check; create the repo, push docs | Install SolidWorks; measure all parts; torque check | Servo test; LM2596 to 6.0 V; torque check | Servos approved, measurement sheet, repo shared |
| Nov 2 – 8 | Firmware v0 (bench, MG90S); simulator | Coupon CAD + **Batch A** (Mon–Wed); layout → `arm.yaml`; start the assembly | Power board; one servo through the full chain; pin map | Servos ordered (Nov 3), clearances recorded, firmware passes the test lines |
| Nov 9 – 15 | Base turntable (Thu); hand → simulated arm; laptop side of the protocol | Full assembly; collision/range checks; mass properties → torque re-check | Peak current; wiring paths; firmware review | **Design review Fri Nov 13**, STLs by Sun |
| Nov 16 – 20 | Motion limiter; calibration code | **Batch B**: whole arm | Wiring harness | All parts printed |
| Nov 21 – 29 | Every joint moves from the laptop (low speed) | Assemble; list misfits | Wire the arm; power-on order test; calibration measurements | Arm assembled, wired, calibrated |
| Nov 30 – Dec 9 | Real-arm IK; mimic mode | **Batch C** (failed parts only, ≤ $5) | First repeatability test | Live gesture control |
| Dec 10 – 22 | Finals | | | |
| Dec 23 – ~Jan 10 | Command gestures, record/replay, README | CAD renders, photos | Schematic, metrics | Demo + write-up |

## Printing (D5)

- **A:** coupon, ~$1, Nov 2–4.
- **B:** whole arm, ≤ 300 g, ~$15–20, Nov 16–20.
- **C:** failed parts only, ≤ $5, Nov 30 – Dec 2.
