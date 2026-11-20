<!-- Owner: Ishaan. Sources of truth: docs/PROTOCOL.md and firmware/arm_controller/arm_controller.ino. -->

## One line per message

Every message, in both directions, is one line of ASCII:

```
<TYPE>,<seq>[,<field>...]*<CS>\n
```

`TYPE` is one capital letter. `seq` counts from 0 to 65535 and wraps; replies echo the seq they answer. `CS` is the XOR of every byte before the `*`, written as two upper-case hex digits, the same scheme as NMEA GPS sentences. XOR was chosen over CRC-8 because it can be checked by hand at the bench.

A `C` frame carries five pulse widths in microseconds, J0 to J4. It is about 40 bytes, so 50 frames a second uses roughly 17 % of the link at 115200 baud.

## Why the firmware rejects instead of clamping

A pulse outside a joint's hard limit rejects the whole frame with `E,<seq>,3` and keeps the previous target. The laptop already clamps to the workspace, so this error only fires on a bug, and a bug should be loud. Clamping would hide it: the arm would quietly go somewhere other than asked.

The same rule holds on the laptop side. `joint_to_pulse()` raises instead of clamping.

## Four states, and a watchdog

Hobby servos give the Nano no position feedback. After a reset it cannot know where the arm is, and any pulse would snap a joint to that angle at full speed. So the firmware boots **DISARMED** with no pulses at all, and the arm is designed to rest safely in its park pose when limp.

While **ARMED**, a valid `C` frame must arrive at least every {{watchdogMs}} ms. If the stream stops, the firmware enters **HOLD** and keeps the last pulses on the outputs. The laptop sends at {{heartbeatHz}} Hz, one frame every 33 ms, so about nine frames can be lost before the watchdog fires. A missing PCA9685 at boot is a **FAULT**: outputs stay off until the board is reset.

One question is still open. If the laptop program dies without sending `D`, HOLD keeps every servo powered forever. A timeout from HOLD to DISARMED would fix that, at the cost of dropping the arm if it is far from park.

## Motion limiter

`{{fwVersion}}` on `main` writes each `C` frame straight to the outputs. The motion limiter, which ramps every joint toward its target under a per-joint speed cap, is written and in review as pull request #12, together with a host test harness that compiles the real sketch against Arduino stubs. Until it merges, `D` goes limp immediately and `H` is acknowledged but does not move.

## Tests

The Python side has {{testFunctions}} test functions across {{testFiles}} files on `main`, covering the protocol, kinematics, calibration, motion and the serial link. The protocol's test vectors are checked on both ends: the firmware and the laptop must produce exactly the same bytes.

One test enforces an ordering between two files owned by different people: the calibration range must sit inside the firmware's limits, so a change to either that breaks the margin fails the build.
