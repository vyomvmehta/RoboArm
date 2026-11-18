#!/bin/sh
# Real AVR build of arm_controller.ino, for the flash and RAM numbers that the host
# tests in this directory cannot give. Verify in the Arduino IDE too; this is the
# same compiler and target, not the same build system.
#
#   ./avr_build.sh            builds into ./avr-build/ and prints the size
#
# Needs: avr-gcc + avr-libc  (Debian/Ubuntu: apt install gcc-avr avr-libc)
# and three sources, cloned on first run into ./avr-build/lib/:
#   arduino/ArduinoCore-avr, adafruit/Adafruit-PWM-Servo-Driver-Library, adafruit/Adafruit_BusIO
set -e
cd "$(dirname "$0")"
B=avr-build
command -v avr-g++ >/dev/null || { echo "avr-g++ not found: apt install gcc-avr avr-libc"; exit 1; }
mkdir -p $B/lib $B/obj
[ -d $B/lib/core ]  || git clone -q --depth 1 https://github.com/arduino/ArduinoCore-avr $B/lib/core
[ -d $B/lib/pwm ]   || git clone -q --depth 1 https://github.com/adafruit/Adafruit-PWM-Servo-Driver-Library $B/lib/pwm
[ -d $B/lib/busio ] || git clone -q --depth 1 https://github.com/adafruit/Adafruit_BusIO $B/lib/busio

MCU="-mmcu=atmega328p -DF_CPU=16000000L -DARDUINO=10819 -DARDUINO_AVR_NANO -DARDUINO_ARCH_AVR"
INC="-I$B/lib/core/cores/arduino -I$B/lib/core/variants/eightanaloginputs -I$B/lib/core/libraries/Wire/src -I$B/lib/pwm -I$B/lib/busio"
OPT="-Os -ffunction-sections -fdata-sections -flto -fno-exceptions -fno-threadsafe-statics -fpermissive"

# the IDE prepends Arduino.h to a .ino and compiles it as C++; do the same
{ echo '#include <Arduino.h>'; cat ../arm_controller/arm_controller.ino; } > $B/sketch.cpp

echo "== sketch (warnings on) =="
avr-g++ -c $MCU $INC $OPT -std=gnu++11 -Wall -Wextra $B/sketch.cpp -o $B/obj/sketch.o

for f in $B/lib/core/cores/arduino/*.c $B/lib/core/libraries/Wire/src/utility/twi.c; do
  avr-gcc -c $MCU $INC $OPT -w -std=gnu11 "$f" -o "$B/obj/c_$(basename "$f" .c).o" 2>/dev/null || true
done
for f in $B/lib/core/cores/arduino/*.cpp $B/lib/core/libraries/Wire/src/Wire.cpp $B/lib/pwm/*.cpp $B/lib/busio/*.cpp; do
  avr-g++ -c $MCU $INC $OPT -w -std=gnu++11 "$f" -o "$B/obj/x_$(basename "$f" .cpp).o" 2>/dev/null || true
done

avr-g++ $MCU -Os -flto -fuse-linker-plugin -Wl,--gc-sections -o $B/firmware.elf \
        $B/obj/sketch.o $B/obj/c_*.o $B/obj/x_*.o -lm
echo
avr-size --format=avr --mcu=atmega328p $B/firmware.elf
