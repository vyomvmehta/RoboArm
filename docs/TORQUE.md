# Shoulder torque check (worst case)

**By:** Vyom, 2026-11-01. **Checked by:** Siddharth (pending; use the measurement sheet where it has better numbers).

**Worst case:** the arm stretched out flat and horizontal, carrying a 30 g block. Torque about the shoulder axis = Σ (mass × horizontal distance from the shoulder). Servo ratings use kg·cm, so mass in kg × distance in cm gives kg·cm directly.

**Assumed lengths:** upper arm 11 cm, forearm 10 cm, wrist → gripper tip 7 cm (≈ 28 cm reach).

| Item | Mass (g) | Distance (cm) | Torque (kg·cm) |
| --- | ---: | ---: | ---: |
| Upper arm (printed, estimate) | 30 | 5.5 | 0.165 |
| Elbow motor MG996R (spec sheet) | 55 | 11 | 0.605 |
| Forearm (printed, estimate) | 20 | 16 | 0.320 |
| Wrist motor MG90S (spec sheet) | 13.4 | 21 | 0.281 |
| Gripper parts (est.) + gripper motor MG90S | 33.4 | 24.5 | 0.818 |
| Block (payload) | 30 | 28 | 0.840 |
| Fasteners, motor arms, cables (allowance, spread along the arm) | 15 | ~14 | 0.210 |
| **Total** | | | **3.24** |

**Result:** 3.24 / 9.4 kg·cm (MG996R stall at 4.8 V) = **34 % of stall**, within the ≤ 50 % rule. (Without the hardware allowance: 3.03 kg·cm, 32 %.)

**Static only:** this is the torque to *hold* the arm still. Accelerating or decelerating the arm adds torque on top, which is one reason for the 50 % margin. The firmware motion limiter keeps accelerations gentle. At 6 V the rated stall is higher (~11 kg·cm), giving more margin.

**Why ≤ 50 %:** stall is the motor's maximum; holding near it overheats the motor. Moving the arm (not just holding it) needs extra torque. Clone servos are often below spec. Printed-part masses are still estimates.

**Biggest contributors:** the block (0.84) and the gripper (0.82). They're furthest from the shoulder, so a gram at the tip costs about 5× a gram near the shoulder. **Keep the gripper light.**

## Elbow check (same worst case)

About the elbow axis: forearm 20 g × 5 cm + wrist motor 13.4 g × 10 cm + gripper 33.4 g × 13.5 cm + block 30 g × 17 cm = 0.100 + 0.134 + 0.451 + 0.510 = **1.20 kg·cm**, i.e. **13 % of MG996R stall**. No concern.

**Recommendation for the arm-size call (Mon Nov 2):** keep ~11 + 10 + 7 cm. Torque isn't the limit; check that ~28 cm reaches the demo's pick and place spots.

**Re-check:** with measured motor masses (if available) and with SolidWorks mass properties at the Nov 8 design review.

## Wrist check (MG90S, same worst case), added 2026-11-04

About the wrist axis: gripper parts + gripper motor 33.4 g × 3.5 cm + block 30 g × 7 cm = 0.117 + 0.210 = **0.33 kg·cm**, i.e. **18 % of MG90S stall** (1.8 kg·cm at 4.8 V). No concern. The base (J0) carries no weight (608 bearings), only friction and the arm's inertia when turning.

## Clone servos (margin check)

Cheap MG996R clones often reach only 60–70 % of the rated 9.4 kg·cm. Worst plausible case: 3.24 / (0.7 × 9.4) = **49 %**, still at or under the 50 % rule. At 6 V (rated ~11 kg·cm) the margin is better. Confirm with the Nov 8 SolidWorks masses.

## What it means for current (rough; measure on Nov 18)

A servo's current rises roughly with the torque it holds. With an MG996R stall current of about 2.5 A: shoulder at ~34 % ≈ 0.9 A, elbow ≈ 0.35 A, the two MG90S and the base ≈ 0.1–0.2 A each. **Holding the stretched-out arm: about 1.5–2 A in total.** Moving adds short peaks. Against the chain: charger 45 W at 15 V (≈ 3 A at 15 V, more than 6 A worth at 6 V) has lots of margin; the **LM2596 (about 2 A continuous) is the part closest to its limit**, which is why it gets a heatsink and the stall test (D16), and why the motion limiter keeps speeds gentle.
