# Gesture-Controlled Robot Arm

A 5-servo desktop robot arm, designed in SolidWorks and 3D printed, that copies your hand. A laptop webcam tracks your hand with MediaPipe: move your hand and the arm moves; pinch your fingers and the gripper closes.

**Status (Nov 2026):** in progress. The plan, the laptop↔Arduino protocol and the arm's kinematics (with tests) are done. CAD, printing and electronics are next. Target: live gesture control in December 2026, then a pick-and-place demo and write-up in January 2027.

**Team:** Vyom Mehta, Ishaan, Siddharth (University of Waterloo).

## How it works

```
Webcam → Laptop (Python)                                    → Arduino Nano → PCA9685 → 5 servos
         hand landmarks → smoothing → target point → IK          (USB serial)    (I²C)
```

| Joint | Servo | Job |
| --- | --- | --- |
| J0 base | MG996R | Turns the arm left/right |
| J1 shoulder | MG996R | Raises/lowers the upper arm |
| J2 elbow | MG996R | Bends the forearm |
| J3 wrist | MG90S | Sets the gripper's angle |
| J4 gripper | MG90S | Opens/closes the two-jaw gripper |

## Repository

```
arm/kinematics/   forward + inverse kinematics
tests/            unit tests (run: python -m pytest)
docs/             PROTOCOL (laptop↔Arduino messages), TIMELINE, DECISIONS, CHECKLIST
```

More folders (CAD, firmware, vision, config) arrive as each part is built.

## Run the tests

```
pip install pytest
python -m pytest -q
```

## How we built this

We use Claude Code (an AI assistant) as a tutor and pair programmer. It explains concepts before we build them and writes some of the code and docs. For example, the inverse kinematics was derived by hand first, then coded with Claude's help. A full account of who did what will be here with the final write-up.
