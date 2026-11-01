# Timeline v4 (2026-10-31): V1 finished in November

The plain-language version is the team plan page: https://claude.ai/artifact/FYa2ohKX7dTyKSVxJqvHiQ. Keep the two in sync.

**Why v4:**
- Finals run from about Dec 7 to Dec 20, then everyone travels.
- From January, Ishaan and Siddharth are on co-op away from Waterloo; Vyom has a study term.
- So all team work ends **Sun Dec 6**. V1 (web-page control, D10) has to work by **Sun Nov 22** and be demoed by **Sun Nov 29**.
- After Dec 6 the arm stays with Vyom. January = Vyom solo: write-up + V2 (gestures).
- **Hours needed in November:** Vyom ~8–10 h/week, Ishaan and Siddharth ~6–8 h/week each.

## Dated deliverables

| Date | Owner | Deliverable |
| --- | --- | --- |
| Sun Nov 1 | Vyom | GitHub project ✓ |
| Sun Nov 1 | Siddharth | Measurement sheet (sizes + masses); converter set to 6.0 V |
| Sun Nov 1 | Ishaan | Motor test: do the MG996Rs hold an angle? |
| Sun Nov 1 | All | Torque estimates (independent) |
| Mon Nov 2 | All | **Order from Amazon.ca:** 3 (+1) MG996R 180°, 9 V PD trigger, fuse holder + 3–4 A fuse, servo extensions, M3/M2 screws |
| Mon Nov 2 | Siddharth (call) | Arm size agreed |
| Mon Nov 2 → Tue Nov 3 | Vyom | Test coupon printed (Batch A) and measured |
| Wed Nov 4 | Vyom | `config/arm.yaml`: lengths, joint limits, park/home poses |
| Thu Nov 5 | Siddharth | Power board working (Ishaan checks) |
| Fri Nov 6 | Siddharth | Gripper CAD (Vyom checks) |
| Fri Nov 6 | Ishaan | Pin map + firmware v0 tested on an MG90S (Vyom checks) |
| Fri Nov 6 | All | Cable + board plan |
| Sat Nov 7 | Vyom | Links + base CAD |
| **Sun Nov 8** | Vyom + all | **Full assembly model, design review call, STL export** |
| Mon–Thu Nov 9–12 | Vyom | **Batch B: print the whole arm** |
| Fri Nov 13 | Ishaan | Servo cables/harness; new MG996Rs confirmed in hand |
| Sun Nov 15 | Vyom | Control web page (sliders + point-and-go + arm drawing; laptop + phone) |
| Sun Nov 15 | Ishaan | Laptop↔Arduino comms + motion limiter |
| Sat–Sun Nov 14–15 | All (Siddharth leads) | Build weekend: assembly starts |
| Tue Nov 17 | Siddharth | Arm assembled + powered; misfit list → Vyom |
| Wed Nov 18 | Ishaan / Siddharth | Arm wired / peak current measured |
| Fri Nov 20 | Vyom | Batch C reprints (≤ $5, only if needed) |
| Sat Nov 21 | Ishaan | Calibration done; every joint moves from the laptop |
| **Sun Nov 22** | All | **V1 works: the page drives the real arm** |
| **Sun Nov 29** | All | **Demo video (pick-and-place), repeatability test, photos/renders, write-up notes** |
| Nov 30 – Sun Dec 6 | All | Spare week; hard stop. The arm goes home with Vyom. |
| ~Dec 7 – 20 | | Finals; then travel |
| January | Vyom | README/write-up with measurements; V2 gesture control |

## Critical path

Measurement sheet (Nov 1) → test print (Nov 3) → links/base CAD (Nov 7) → model + review + STLs (Nov 8) → print (Nov 9–12) → assembly (Nov 17) → calibration (Nov 21) → V1 works (Nov 22) → demo (Nov 29).

Second chain: motor test → Amazon.ca order (Nov 2) → parts arrive (~Nov 6) → power board + assembly.

## If we fall behind, cut in this order

1. Phone support (laptop browser only)
2. Point-and-go (sliders only)
3. A simpler gripper (one moving jaw)
