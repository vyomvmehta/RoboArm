# Pin map: which wire goes where

Owner: Ishaan (D8, "signals"). Checker: Siddharth.
Covers the signal side only. The power chain up to the servo rail is Siddharth's (D16).

Tags: **MEASURED** was checked on real hardware. **ASSUMED** has not been, and is the next
thing to verify. **PLANNED** is designed but not built or installed yet.

## 1. Laptop to Nano

| | |
| --- | --- |
| Cable | USB, laptop to Arduino Nano |
| Port | `COM5` on Ishaan's laptop (**MEASURED** 2026-11-09; changes with the USB socket) |
| Serial | 115200 baud, 8N1, line ending `\n` (PROTOCOL.md s1) |
| Nano power | From the laptop's USB. **Not** from the servo rail. |

Opening the port pulls DTR and resets the Nano. That is by design: it reboots DISARMED with the
outputs off (PROTOCOL.md s7). Only one program may hold the port at a time, so the Serial
Monitor, `tools/roboarm_bench.py` and an upload are mutually exclusive.

## 2. Nano to PCA9685 (I2C)

| Nano | PCA9685 | Carries |
| --- | --- | --- |
| 5V | VCC | Logic power for the driver chip only |
| GND | GND (header) | Logic ground, and the common ground for the whole system |
| A4 | SDA | I2C data |
| A5 | SCL | I2C clock |

- I2C address **0x40** (**MEASURED**: the firmware probes it at boot and reports `E,0,8` plus
  FAULT if it does not answer; it has answered on every boot so far).
- OE is left unconnected: the board pulls it low, so outputs are enabled.
- **Never connect the Nano's 5V to V+.** The Nano's regulator supplies a few hundred mA; one
  MG996R can pull 2.5 A stalled.
- Siddharth: please check the 6-pin header order against the silkscreen on our board.

## 3. Servo channels

| PCA9685 channel | Joint | Servo |
| --- | --- | --- |
| 0 | J0 base | MG996R 180° |
| 1 | J1 shoulder | MG996R 180° |
| 2 | J2 elbow | MG996R 180° |
| 3 | J3 wrist | MG90S |
| 4 | J4 gripper | MG90S |

This ordering is what `firmware/arm_controller/arm_controller.ino` writes (`CHANNEL[] = {0,1,2,3,4}`)
and what a `C` frame's five fields mean, in order (PROTOCOL.md s3). Changing it means changing
both.

Each 3-pin output header is, from the board edge inwards: **GND (brown/black), V+ (red),
signal (orange/yellow)**. A plug on backwards does nothing at best and cooks an MG996R at worst.

**The 180° MG996Rs had not arrived as of 2026-11-11** (the Amazon order task is still open), so
every bench test so far used the **360° continuous-rotation** units. See s5.

## 4. Power to the servo rail

Siddharth's chain (D16), ending at the PCA9685:

```
Apple 96 W USB-C charger
  -> USB-C PD trigger, at 9 V           MEASURED 2026-11-07. D16 planned 15 V; see note below
  -> LM2596 buck converter, at 6.0 V    MEASURED 2026-11-08 (no meter on the output under load yet)
  -> 8 A glass fuse                     PLANNED (D16 update, Nov 4: use the 8 A ones we own)
  -> rocker kill switch                 PLANNED, not installed (RidgidWare run pending)
  -> 2200 uF / >=10 V capacitor         PLANNED, not installed (same run)
  -> PCA9685 V+ and GND screw terminals
```

**The trigger is at 9 V, not the 15 V D16 specified.** That matters for headroom, not for
whether it works: D16 chose 15 V because the Apple charger offers 45 W there versus 27 W at 9 V,
which is roughly 3.8 A at 6 V after conversion. The Nov 8 stall test passed at 9 V with one
motor, but it has not been tested with several MG996Rs starting together, which is the case D16
was worried about. Either re-set the trigger to 15 V or record in DECISIONS.md why 9 V is
accepted.

- **The V+ on the 6-pin header and the V+ on the screw terminal are the same net.** Feeding
  either one powers the servo rail; the other needs nothing connected.
- The LM2596's **OUT-** must go to the PCA9685's GND screw terminal. Without that return path the
  rail sits at 6 V relative to nothing and no current flows, while the driver still acknowledges
  every write over I2C. The protocol cannot detect this, so it looks exactly like working
  firmware driving dead servos.
- All grounds are one net: Nano GND, PCA9685 header GND, PCA9685 terminal GND, LM2596 OUT-.

## 5. Pulse limits and the servo measurements

| Layer | Where | Value |
| --- | --- | --- |
| Firmware hard limit | `arm_controller.ino`, `PULSE_MIN[]` / `PULSE_MAX[]` | 500-2600 us |
| Laptop working range | `config/calibration.yaml`, `min_us` / `max_us` | 550-2550 us |

PROTOCOL.md s9 wants the firmware limits slightly **wider** than the laptop's, so they only trip
on a real bug. 500/2600 against 550/2550 gives 50 us of margin each side.

- **MEASURED** (Vyom, MG90S, 2026-11-10): 180 degrees spans roughly **650 to 2600 us**, about
  10.8 us/deg. End stop near 500, still moving at 2600. The firmware limits above come from this.
- **ASSUMED** for J0-J2: those are MG996Rs and have not been measured. 500/2600 is carried over
  from the MG90S. A 180° MG996R that stops at 2500 would stall if driven to 2600, so **measure
  them before driving either extreme**, and narrow `PULSE_MIN[0..2]` / `PULSE_MAX[0..2]` when the
  numbers exist. The arrays are per joint precisely so this is a one-line change.

### The 1200 us "midpoint" was a 360° servo, not a measurement

On 2026-11-10 two MG996Rs on channels 0 and 1 appeared to centre near **1200 us** and offered no
holding torque. Those were almost certainly the **360° continuous-rotation** units (D16's Nov 8
test used one as a load, and the 180° units had not arrived).

A continuous-rotation servo has no position control at all: the pulse width sets **speed**, not
angle, and about 1500 us means stop. So 1200 us was that unit's neutral point, not an angular
centre, and "no resistance when armed" is the correct behaviour rather than a fault. **Do not
carry 1200 into `calibration.yaml`.** `config/arm.yaml`'s assembly note (horn fitted at 1500 us)
still stands and has not been contradicted by anything measured.

## 6. Bench tools

| File | What it is |
| --- | --- |
| `tools/roboarm_bench.py` | Drives the v0 firmware over USB: waits for the banner, arms, streams `C` frames at 30 Hz so the watchdog never fires. `--centre` and `--span` set a safe band. |
| `firmware/two_servo_test/` | No protocol, no watchdog. Type a pulse and watch one servo. `w` sweeps, `e` widens the range to 500-2500. This is the tool for finding real end stops. |

## 7. Still open

- MG996R 180° travel and us_per_deg, measured, once the Amazon order arrives.
- LM2596 output read with a multimeter during a stall (the Nov 1 task still in review).
- Whether the PD trigger stays at 9 V or goes to 15 V, and D16 updated either way.
- Kill switch and capacitor installed.
