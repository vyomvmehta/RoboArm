# Pin map: which wire goes where

Owner: Ishaan (D8, "signals"). Checker: Siddharth.
Covers the signal side only. The power chain up to the servo rail is Siddharth's (D16).

Everything marked **MEASURED** was checked on the bench. Everything marked **ASSUMED** has not
been, and is the next thing to verify.

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

## 3. Servo channels

| PCA9685 channel | Joint | Servo |
| --- | --- | --- |
| 0 | J0 base | MG996R |
| 1 | J1 shoulder | MG996R |
| 2 | J2 elbow | MG996R |
| 3 | J3 wrist | MG90S |
| 4 | J4 gripper | MG90S |

This ordering is what `firmware/arm_controller/arm_controller.ino` writes (`CHANNEL[] = {0,1,2,3,4}`)
and what a `C` frame's five fields mean, in order (PROTOCOL.md s3). Changing it means changing
both.

Each 3-pin output header is, from the board edge inwards: **GND (brown/black), V+ (red),
signal (orange/yellow)**. A plug on backwards does nothing at best and cooks an MG996R at worst.

Bench state on 2026-11-10: servos on channels 0 and 1 only.

## 4. Power to the servo rail

Siddharth's chain (D16), ending at the PCA9685:

```
Apple 96 W USB-C charger
  -> USB-C PD trigger, set to 15 V      (CHECK with a multimeter: a bad cable drops it to 9 or 5)
  -> LM2596 buck converter, set to 6.0 V (set it with NOTHING connected to the output)
  -> 8 A glass fuse
  -> rocker kill switch
  -> 2200 uF / >=10 V capacitor across the rail
  -> PCA9685 V+ and GND screw terminals
```

- **The V+ on the 6-pin header and the V+ on the screw terminal are the same net.** Feeding
  either one powers the servo rail; the other needs nothing connected. (This cost an hour on
  2026-11-10.)
- The LM2596's **OUT-** must go to the PCA9685's GND screw terminal. Without that return path the
  rail sits at 6 V relative to nothing and no current flows, while the driver still acknowledges
  every write over I2C. The protocol cannot detect this, so it looks exactly like working
  firmware driving dead servos.
- All grounds are one net: Nano GND, PCA9685 header GND, PCA9685 terminal GND, LM2596 OUT-.

## 5. Pulse limits

| Layer | Where | Current value |
| --- | --- | --- |
| Firmware hard limit | `arm_controller.ino`, `PULSE_MIN` / `PULSE_MAX` | 1000-2000 us, **ASSUMED** |
| Laptop working range | `config/calibration.yaml`, `min_us` / `max_us` | 1000-2000 us, **ASSUMED** |

PROTOCOL.md s9 wants the firmware limits slightly **wider** than the laptop's, so they only trip
on a real bug. They are currently identical, so firmware error 3 cannot do its job. Both numbers
are also probably wrong:

- **MEASURED** (Vyom, MG90S, 2026-11-10): 180 degrees spans roughly **650 to 2600 us**, about
  10.8 us/deg. Not the 5.6 that a 1000 us span would imply.
- **MEASURED** (Ishaan, MG996R, 2026-11-10): the midpoint of the two bench servos is near
  **1200 us**, not 1500. `config/arm.yaml`'s assembly note assumes 1500 is the window centre, so
  either the horns go on differently or that note needs revisiting.
- **NOT YET MEASURED:** the MG996R's own travel. Until that exists, do not widen either limit.

Order of operations when the numbers arrive: **widen the firmware limits first, then
`calibration.yaml`.** The other way round makes the laptop send pulses the Nano rejects with
error 3. `FakeNano` in `arm/comms/link.py` hardcodes 1000-2000 as well and has to follow.

## 6. Still open

- MG996R travel and us_per_deg, measured (`firmware/two_servo_test`, `w` then `e`).
- LM2596 output confirmed at 6.0 V under load, which is the Nov 1 task still in review.
- Whether the midpoint is 1200 because of the servo or because of the horn.
