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

The **180° MG996Rs arrived 2026-11-12** and all four were tested on 2026-11-13 (s5). Bench work
before that date used the **360° continuous-rotation** units, which is why those earlier results
looked wrong; see the note at the end of s5.

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
| Firmware hard limit | `arm_controller.ino`, `PULSE_MIN[]` / `PULSE_MAX[]` | **450-2500 us**, all five joints |
| Laptop working range | `config/calibration.yaml`, `min_us` / `max_us` | **500-2450 us**, all five joints |

PROTOCOL.md s9 wants the firmware limits **wider** than the laptop's, so they only trip on a bug.
50 us of margin each side.

### Measured travel

**MEASURED** 2026-11-13 at Velocity, **every servo** (four MG996R 180° and both MG90S):

- **450-2500 us** for a full 180°
- **11.4 us/°**
- **mid-travel 1475 us**

Uniform across every unit, which is why the limits are uniform rather than per servo type.

### Centres are not 1500

The measured mid-travel is **1475 us**, not the conventional 1500. `config/arm.yaml`'s assembly
note says to fit horns at 1500, which would leave every joint 25 us (about 2°) off centre and
eat into the travel at one end. `calibration.yaml` on `calib/provisional` uses 1475.
**Settle the horn-fitting pulse before assembly on Nov 19.**

### The 1200 us "midpoint" was a 360° servo

On 2026-11-10 two MG996Rs appeared to centre near 1200 us with no holding torque. Those were the
**360° continuous-rotation** units: pulse width sets **speed**, not angle, so 1200 was that unit's
stop point and "no resistance" was correct behaviour. Confirmed by D16's Nov 8 entry, which used a
360° unit as a load. **Do not carry 1200 into `calibration.yaml`.**

## 6. Bench tools

| File | What it is |
| --- | --- |
| `tools/roboarm_bench.py` | Drives the v0 firmware over USB: waits for the banner, arms, streams `C` frames at 30 Hz so the watchdog never fires. `--centre` and `--span` set a safe band. |
| `firmware/two_servo_test/` | No protocol, no watchdog. Type a pulse and watch one servo. `w` sweeps, `e` widens the range to 500-2500. This is the tool for finding real end stops. |

## 7. Still open

- LM2596 output read with a multimeter during a stall (the Nov 1 task is still in review).
- Stall torque for the MG996Rs, which decides 13/12 vs 15/14 at the Nov 15 review call.
- Whether horns are fitted at 1475 (measured centre) or 1500 (arm.yaml's assembly note).
  Needed before assembly on Nov 19.
- Whether the PD trigger stays at 9 V or goes to 15 V, and D16 updated either way.
- Kill switch and 2200 uF capacitor installed.
