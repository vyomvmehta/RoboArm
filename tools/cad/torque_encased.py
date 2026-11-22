"""Static servo torque for the arm with and without the shells (Vyom asked 2026-11-13).

Reads SolidWorks Parts/Arm Encased/mass_properties.json (written by build_arm_encased.py:
volume + centre of mass of every moving part in its own frame), adds the things that are not
in the CAD (servos, bolt, bearing, screws, cables, the 30 g block), and finds the worst pose
over the whole joint range. No SolidWorks needed:   py tools/cad/torque_encased.py            (Arm Encased, D20)
                        py tools/cad/torque_encased.py "Arm Human" (human-looking skins, D21)

How the four-bar shares the load (D14/D19): the shoulder servo turns the upper arm (theta1);
the elbow servo turns the crank, which through the parallelogram sets the forearm's angle to
the TABLE (phi = theta1 + theta2). So, by virtual work, with V = g * sum(m * height):
    shoulder torque = dV/d(theta1) holding phi still
    elbow torque    = dV/d(phi)    holding theta1 still
    wrist torque    = dV/d(theta3)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = sys.argv[1] if len(sys.argv) > 1 else "Arm Encased"
PROPS = json.loads((ROOT / "SolidWorks Parts" / FOLDER / "mass_properties.json").read_text())
PLA, LW_PLA = 1.24, 0.75          # g/cm3: solid PLA (SolidWorks volume x this), printed LW-PLA
L1, L2, CRANK, L3 = 130.0, 120.0, 30.0, 84.0   # arm.yaml (l3 84: flat jaws, D21)
GRIP_ORIGIN = 39.0                 # wrist axis -> gripper frame origin (build_arm.GRIPPER_ORIGIN)

# MG996R stall (rated): 9.4 kg.cm @ 4.8 V, 11 @ 6 V. MG90S: 1.8 @ 4.8 V, 2.2 @ 6 V.
# Rule (TORQUE.md): hold at <= 50 % of stall; clones may give only ~70 % of the rating.
STALL = {"shoulder": 11.0, "elbow": 11.0, "wrist": 2.2}

# Covers (they can be printed in LW-PLA). An entry with "part_of" is already inside that
# assembly's volume (the cuff + palm cover are in Hand.SLDASM); it only changes the density.
SHELLS = {"Upper Arm Shell", "Forearm Shell", "Hand Shell", "Upper Arm Skin", "Forearm Skin",
          "Palm", "Wrist Cuff", "Palm Cover"}

# Not in the CAD: (grams, frame, local point mm). Frames as in build_arm.pose_transforms.
EXTRAS = [
    (13.4, "Forearm", (114.0, 0.0, -3.0), "wrist MG90S"),
    (13.4, "Gripper", (5.8, 0.0, -6.0), "gripper MG90S"),
    (17.0, "Forearm", (0.0, 0.0, 0.0), "M8 bolt + nut + washer at the elbow"),
    (12.0, "Upper Arm", (L1, 0.0, 6.0), "608 bearing"),
    (6.0, "Upper Arm", (65.0, 0.0, 0.0), "screws, nylocks, inserts (upper arm)"),
    (6.0, "Forearm", (60.0, 0.0, 0.0), "screws (forearm, gripper posts)"),
    (4.0, "Forearm", (40.0, 0.0, -15.0), "2 servo leads along the arm (~4 g/m)"),
    (30.0, "Grasp", (0.0, 0.0, 0.0), "payload block"),
]


def rot(deg, x, y):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return c * x - s * y, s * x + c * y


def heights(theta1, phi, theta3, shells: bool, shell_density: float):
    """Sum of m*y (g.mm) for the given pose; y = height above the shoulder axis."""
    psi = phi + 180.0
    E = rot(theta1, L1, 0)
    C = rot(psi, CRANK, 0)
    W = (E[0] + rot(phi, L2, 0)[0], E[1] + rot(phi, L2, 0)[1])
    d = rot(phi + theta3, 1, 0)

    def world(frame, p):
        x, y, _ = p
        if frame == "Upper Arm":
            return rot(theta1, x, y)
        if frame == "Crank":
            return rot(psi, x, y)
        if frame == "Rod":
            q = rot(theta1, x, y)
            return C[0] + q[0], C[1] + q[1]
        if frame in ("Forearm", "Elbow Spacer"):
            q = rot(phi, x, y)
            return E[0] + q[0], E[1] + q[1]
        if frame == "Wrist Bracket":
            q = rot(phi + theta3, x, y)
            return W[0] + q[0], W[1] + q[1]
        if frame == "Gripper":           # gripper X = d turned +90, Z = d, Y = shoulder axis
            gx, _, gz = p
            o = (W[0] + GRIP_ORIGIN * d[0], W[1] + GRIP_ORIGIN * d[1])
            return o[0] + gx * -d[1] + gz * d[0], o[1] + gx * d[0] + gz * d[1]
        if frame == "Grasp":
            return W[0] + L3 * d[0], W[1] + L3 * d[1]
        raise KeyError(frame)

    total = 0.0
    for name, v in PROPS.items():
        if name in SHELLS and not shells:
            continue
        if v.get("part_of"):
            m = v["vol_cm3"] * (shell_density - PLA)        # density correction only
            total += m * world(v["frame"], v["com_mm"])[1]
            continue
        rho = shell_density if name in SHELLS else PLA
        m = v["vol_cm3"] * rho
        if name == "Crank" and not shells:   # original crank: no drum (D19: 3.1 g, near O)
            m, com = 3.1, (12.0, 0.0, -6.5)
        else:
            com = v["com_mm"]
        total += m * world(v["frame"], com)[1]
    for m, frame, p, _ in EXTRAS:
        total += m * world(frame, p)[1]
    return total


def torques(theta1, phi, theta3, shells=True, rho=PLA):
    h = 0.01                                           # degrees
    f = lambda *q: heights(*q, shells, rho)
    k = 1 / (1000 * 10) / math.radians(h) / 2          # g.mm/rad -> kg.cm
    return {"shoulder": (f(theta1 + h, phi, theta3) - f(theta1 - h, phi, theta3)) * k,
            "elbow": (f(theta1, phi + h, theta3) - f(theta1, phi - h, theta3)) * k,
            "wrist": (f(theta1, phi, theta3 + h) - f(theta1, phi, theta3 - h)) * k}


def worst(shells, rho, elbow_min, wrist_min):
    best = {j: (0.0, None) for j in STALL}
    for t1 in range(-20, 141, 5):
        for t2 in range(elbow_min, 1, 5):
            for t3 in range(wrist_min, 51, 5):
                tq = torques(t1, t1 + t2, t3, shells, rho)
                for j, v in tq.items():
                    if abs(v) > abs(best[j][0]):
                        best[j] = (v, (t1, t2, t3))
    return best


def moving_mass(shells, rho):
    m = sum(v["vol_cm3"] * ((rho - PLA) if v.get("part_of") else rho if n in SHELLS else PLA)
            for n, v in PROPS.items() if shells or n not in SHELLS)
    if not shells:
        m += 3.1 - PROPS["Crank"]["vol_cm3"] * PLA
    return m + sum(e[0] for e in EXTRAS)


def main():
    cases = [("original arm (no shells)", False, PLA, -140, -95),
             ("encased, shells in PLA", True, PLA, -135, -90),
             ("encased, shells in LW-PLA", True, LW_PLA, -135, -90)]
    print("Flat-out pose (theta1 0, elbow straight, wrist straight), kg.cm:")
    for label, sh, rho, _, _ in cases:
        tq = torques(0, 0, 0, sh, rho)
        print(f"  {label:28s} " + "  ".join(f"{j} {v:5.2f}" for j, v in tq.items()))
    print("\nWorst pose over the whole joint range (shoulder -20..140, elbow limit..0, wrist limit..50):")
    for label, sh, rho, e_min, w_min in cases:
        b = worst(sh, rho, e_min, w_min)
        print(f"  {label:28s} moving mass incl. block {moving_mass(sh, rho):5.0f} g")
        for j, (v, pose) in b.items():
            pct = abs(v) / STALL[j] * 100
            print(f"     {j:8s} {abs(v):5.2f} kg.cm = {pct:4.0f} % of {STALL[j]} (6 V), "
                  f"{abs(v) / (0.7 * STALL[j]) * 100:4.0f} % of a 70 % clone   at {pose}")


if __name__ == "__main__":
    main()
