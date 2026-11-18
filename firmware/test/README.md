# Firmware tests (host)

Compiles the **real** `firmware/arm_controller/arm_controller.ino` on your laptop, against
stub `Arduino.h` / `Wire.h` / `Adafruit_PWMServoDriver.h`, and drives it through a fake serial
port. The sketch is `#include`d, not copied, so these tests cannot drift away from the firmware
that goes on the board.

```
./run.sh                 # builds, then runs
```

Or directly:

```
g++ -std=c++11 -O1 -I. -Istub -o fwtest main.cpp && ./fwtest
```

On Windows this needs a host C++ compiler: Git Bash with MinGW, MSYS2, or WSL. The `avr-g++`
that ships inside the Arduino IDE builds for the AVR, not for the laptop, so it will not do.

## What it covers

**27 protocol checks** against `docs/PROTOCOL.md`: the boot banner, every test line in section 2,
all eight error codes, checksum rejection, the state machine, and the 300 ms watchdog.

**26 motion-limiter checks**: the achieved deg/s on each of the five joints over a full
450-2500 sweep (45.0 / 45.0 / 45.0 / 90.0 / 90.0), the cap on every individual tick rather than
just the average, the first `C` after arming landing at once while every later one ramps, HOLD
freezing the ramp and a valid `C` resuming it without a jump, a 200 ms loop stall producing one
step instead of the ten it "owed", a rejected frame leaving the previous target standing, and
that no pulse outside 450-2500 us ever reaches the PCA9685.

The limiter tests send a `C` frame every 33 ms, the way `arm/control.py` does. Without that the
watchdog correctly drops the firmware into HOLD after 300 ms and the ramp freezes, which is the
designed behaviour and makes the timing assertions meaningless.

## The AVR build

`./run.sh` builds for the laptop, so it says nothing about flash, RAM, or the fact that `int` is
16 bits on an AVR and 32 on a PC. `./avr_build.sh` closes that gap: same compiler and same target
as the IDE, cross-compiled for the ATmega328P at 16 MHz.

```
./avr_build.sh           # needs avr-gcc + avr-libc; clones the Arduino core and
                         # the Adafruit libraries into avr-build/ on first run
```

Measured 2026-11-18, with the motion limiter in:

```
Program:   11856 bytes (36.2% Full)     of 32 KB flash
Data:        679 bytes (33.2% Full)     of 2 KB RAM, leaving ~1.3 KB for stack and heap
```

No warnings under `-Wall -Wextra` on the AVR target. The 16-bit-int trap is worth knowing about:
`45 deg/s * 11389` is 512505, which does not fit in 16 bits, so `STEP_MILLI` casts to `uint32_t`
before multiplying. Reading the linked binary back confirms `STEP_MILLI_US` holds 10250 and 20500
and not the 1075 that late promotion would have produced.

## What neither build proves

- **There are no servos.** The stub records what was written to each channel; it does not know
  whether a real MG996R gets there, draws too much current, or hits a mechanical stop.
- **The IDE is still the thing you flash with.** Same compiler, different build system: verify
  there (Ctrl+R) before uploading.

Green here means the logic is right. The bench is still the thing that decides.
