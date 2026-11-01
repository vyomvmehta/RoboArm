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
| **Total** | | | **3.03** |

**Result:** 3.03 / 9.4 kg·cm (MG996R stall at 4.8 V) = **32 % of stall**, within the ≤ 50 % rule. At 6 V the rated stall is higher (~11 kg·cm), giving more margin.

**Why ≤ 50 %:** stall is the motor's maximum; holding near it overheats the motor. Moving the arm (not just holding it) needs extra torque. Clone servos are often below spec. Printed-part masses are still estimates.

**Biggest contributors:** the block (0.84) and the gripper (0.82). They're furthest from the shoulder, so a gram at the tip costs about 5× a gram near the shoulder. **Keep the gripper light.**

**Recommendation for the arm-size call (Mon Nov 2):** keep ~11 + 10 + 7 cm. Torque isn't the limit; check that ~28 cm reaches the demo's pick and place spots.

**Re-check:** with measured motor masses (if available) and with SolidWorks mass properties at the Nov 8 design review.
