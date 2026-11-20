<!-- Owner: Ishaan. Source of truth: docs/PINS.md. Text above the split marker renders before the wiring diagram. -->

The laptop does the thinking and the Nano does the guarding. A Python program solves the inverse kinematics and streams pulse widths over USB serial. The Arduino Nano checks each frame and passes it over I2C to a PCA9685, which generates the five 50 Hz servo signals. Servo power never touches the Nano: it arrives on a separate 6.0 V rail.

<!-- split -->

## Signal path

- **Laptop to Nano:** USB serial at 115200 baud, 8N1, one ASCII line per message. Opening the port pulls DTR and resets the Nano. That is by design: it reboots disarmed with the outputs off.
- **Nano to PCA9685:** A4 is SDA, A5 is SCL, address `0x40`. The firmware probes the address at boot and enters FAULT if the driver does not answer.
- **Nano 5V to PCA9685 VCC** powers the driver's logic only. The Nano's regulator supplies a few hundred milliamps; one MG996R can pull 2.5 A stalled. The Nano's 5V must never feed V+.
- **Output headers**, from the board edge inwards: GND, V+, signal. A plug on backwards does nothing at best and cooks an MG996R at worst.

## Power path

Charger, USB-C PD trigger, LM2596 buck converter at 6.0 V, then the PCA9685's V+ and GND screw terminals. The fuse, kill switch and 2200 µF capacitor are designed in but not installed yet.

The trigger currently sits at 9 V, not the 15 V the design decision specified. At 9 V the charger offers 27 W, roughly 3.8 A at 6 V after conversion. A one-motor stall test passed at 9 V. Several MG996Rs starting together has not been tested, and that is the case the 15 V choice was meant to cover.

## The ground return that software cannot see

The LM2596's OUT− has to reach the PCA9685's GND screw terminal. Without it the servo rail sits at 6 V relative to nothing and no current flows.

The trap is that everything still looks healthy. The driver's logic runs from the Nano's 5 V, so it acknowledges every I2C write. The firmware sends `K`, the laptop sees a working link, and the servos do not move. The protocol cannot detect this. It looks exactly like working firmware driving dead servos, so it goes on the wiring checklist, not in the code.

All grounds are one net: Nano GND, PCA9685 header GND, PCA9685 terminal GND and LM2596 OUT−.

## Measured servo travel

Every servo was swept on the bench on 13 November, alone, with no arm attached. All four MG996Rs and both MG90S gave the same result:

| Quantity | Measured |
| --- | --- |
| Full 180° of travel | 450 to 2500 µs |
| Slope | 11.3889 µs per degree |
| Mid-travel | 1475 µs, not the conventional 1500 |

Two layers of limits come out of that. The firmware's hard limits sit at the measured travel. The laptop's working range sits 50 µs inside them on each side, so the firmware only ever trips on a bug.

The slope is kept at 11.3889 and not rounded to 11.4, because the rounded figure puts the ends of a 180° window at 449 and 2501 µs, just outside the firmware's limits.

## Still open

- LM2596 output read with a multimeter during a stall.
- Whether the PD trigger stays at 9 V or moves to 15 V.
- Kill switch and capacitor installed.
- Every calibration number re-measured on the assembled arm.
