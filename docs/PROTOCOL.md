# Serial Protocol: DRAFT v1 (2026-10-16; Vyom's design choices confirmed 2026-10-31)

> Drafted by Vyom + Claude. **Vyom confirmed on 2026-10-31:** XOR checksum, DISARMED = limp + park pose, boot banner + wait, reject out-of-range frames. It becomes **v1 (agreed)** once Ishaan and Siddharth have read it. After that, changes need all three of us.
> Designed by Vyom (D6). Implemented by Ishaan (firmware + laptop comms, D8). Hardware: laptop ⇄ USB ⇄ Arduino Nano (CH340) ⇄ I²C ⇄ PCA9685 ⇄ 5 servos.

## 1. Transport

- USB serial, **115200 baud, 8N1**. ASCII text, one message per line, ending in `\n`.
- **Budget check:** a `C` frame is ~40 bytes, so at 50 Hz that's ~2 kB/s against ~11.5 kB/s available at 115200 baud (~17 % used). Plenty of room for the acknowledgements.

## 2. Message format (both directions)

```
<TYPE>,<seq>[,<field>...]*<CS>\n
```

- `TYPE`: one capital letter (tables below).
- `seq`: 0–65535, wrapping. The laptop increments it for every message it sends. Replies echo the seq of the message they answer.
- `CS`: checksum, **XOR of every byte before the `*`**, as 2 upper-case hex digits (the same scheme as NMEA GPS sentences).
- Any line that fails parsing or the checksum is **ignored** and answered with an `E` (section 5). Ignoring is safe because the watchdog covers missing frames.

### Test vectors (unit tests on both ends must reproduce these)

| Line | Meaning |
| --- | --- |
| `C,1,1500,1500,1500,1500,1500*76` | All joints at 1500 µs |
| `C,2,1100,1620,1480,1500,2000*7F` | A typical pose |
| `A,3*5E` | Arm |
| `D,4*5C` | Disarm |
| `H,5*51` | Home |
| `K,2,ARMED*26` | Acknowledgement of seq 2 |
| `E,9,3*4F` | Error code 3 for seq 9 |
| `R,0,fw0.1,DISARMED*71` | Boot banner |

## 3. Laptop → Arduino

| Type | Fields | Meaning |
| --- | --- | --- |
| `C` | `p0,p1,p2,p3,p4` | Target pulse widths in **µs** for J0 base … J4 gripper. Integers. Sent at 30–50 Hz while ARMED. |
| `A` | — | Arm (only from DISARMED, and the arm must be resting in the park pose). |
| `D` | — | Disarm: move to the park pose through the motion limiter, then stop the pulses. |
| `H` | — | Move to the home pose through the motion limiter. Later `C` frames take over again. |
| `P` | — | Ping (for measuring round-trip time without moving anything). |

## 4. Arduino → laptop

| Type | Fields | Meaning |
| --- | --- | --- |
| `R` | `fw_version,state` | **Boot banner**, sent once after reset (seq = 0). |
| `K` | `state` | Acknowledges a valid message. state ∈ `DISARMED`, `ARMED`, `HOLD`, `FAULT`. |
| `E` | `code` | Error (section 5). |

## 5. Error codes

| Code | Meaning | Firmware action |
| --- | --- | --- |
| 1 | Bad checksum | Ignore the line |
| 2 | Malformed (wrong field count, non-number, line > 64 chars) | Ignore the line |
| 3 | A pulse is outside that joint's **hard firmware limit** | Reject the **whole** frame; keep the previous target |
| 4 | `C` received while not ARMED | Ignore |
| 5 | Unknown type | Ignore |
| 6 | Watchdog fired: no valid `C` for 300 ms | Enter HOLD (sent once) |
| 7 | `A` refused (not in DISARMED) | Ignore |
| 8 | PCA9685 not found on I²C at boot | Enter FAULT, outputs stay off |

## 6. States

```
power-on / reset ──► DISARMED ──A──► ARMED ──(no C for 300 ms)──► HOLD
                        ▲              │  ▲                          │
                        └──D (via park)┘  └──────── valid C ─────────┘
           any state ──(PCA9685 missing / internal error)──► FAULT (needs reset)
```

- **DISARMED:** no pulses (servos limp). The arm must be designed to **rest safely in its park pose when limp** (a mechanical requirement for Ishaan, so a limp arm doesn't fall and hit anything).
- **ARMED:** firmware assumes the arm starts at the park pose (there's no position feedback). It ramps every joint towards the latest `C` target through the **motion limiter** (°/s cap per joint).
- **HOLD:** keeps sending the last *current* pulses. A valid `C` returns to ARMED, and the limiter makes that resume smooth.
- **FAULT:** outputs off until the board is reset.

## 7. Connection and auto-reset

Opening the serial port resets the Nano (the DTR line). This is safe by design, because the board reboots into DISARMED. The laptop must:

1. Open the port, then **wait up to 3 s for the `R` banner** before sending anything.
2. Only send `A` after seeing `R ... DISARMED`.

A reset mid-run (cable pulled) leaves the arm limp, so the park-pose requirement in section 6 matters.

## 8. Pulses → PCA9685

- 50 Hz frame = 20 000 µs ÷ 4096 counts = **4.88 µs per count**. 1500 µs → 307.2 → **307 counts (= 1499.0 µs)**.
- If 500–2500 µs maps to 180°, one count is about **0.44°**. That's comparable to the servo's own deadband, so it's fine.
- The PCA9685's internal oscillator is only approximately 25 MHz. **Measure the real pulse width once** (scope, or tune until 1500 µs centres a servo) and set the oscillator frequency in firmware. This belongs in the calibration notes.

## 9. Limits (two layers)

- **Firmware hard limits** per joint (in the sketch, a safety floor): slightly *wider* than the laptop's limits, so they only trip on a real bug.
- **Laptop limits** in `config/calibration.yaml`: the real working range.

## Still to decide

- Park and home pose angles (after the CAD exists).
- Per-joint speed caps (°/s) for the motion limiter. **Implemented by Ishaan** (firmware owner since D8); values tuned during calibration (Nov 21).
- Whether the laptop should be able to change speed caps at run time (probably not in v1).
