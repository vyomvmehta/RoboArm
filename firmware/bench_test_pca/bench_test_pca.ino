// Bench test through the PCA9685 (Parts test day, Nov 2026). A throwaway test tool, not the arm firmware.
// Needs the "Adafruit PWM Servo Driver Library" (Arduino IDE: Tools > Manage Libraries).
//
// Wiring (no soldering):
//   Nano 5V  -> PCA9685 VCC   (logic power only)      Nano GND -> PCA9685 GND
//   Nano A4  -> PCA9685 SDA                           Nano A5  -> PCA9685 SCL
//   LM2596 OUT+ (6.0 V) -> PCA9685 blue screw terminal V+
//   LM2596 OUT-         -> PCA9685 blue screw terminal GND
//   Servo plugs onto output header 0: brown wire on GND, red on V+, orange on PWM.
//   Never connect the Nano's 5V to the PCA9685's V+ pin or terminal.
//
// On start-up it scans every I2C address (1-126), lists what answers, and uses the PCA9685 it finds
// (0x40 by default; 0x70 is the chip's "all call" address and is skipped).
//
// Serial Monitor at 115200 baud, line ending "Newline". Type:
//   1500      -> current channel moves to that pulse width in microseconds (allowed 600-2400)
//   c3        -> switch to channel 3 (0-15)
//   d         -> stop pulses on the current channel (servo goes limp)
//   s         -> scan the I2C bus again
//   r         -> read back the chip's registers (is it awake? is the pulse really set?)
//   w         -> walk channels 0-15, 10 s each (5 s at 1000 us, 5 s at 2000 us); any key stops
//   ?         -> show address, channel and pulse

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

const int MIN_US = 600;
const int MAX_US = 2400;
const uint8_t ALL_CALL = 0x70;

Adafruit_PWMServoDriver *pca = nullptr;
uint8_t pca_addr = 0;
int channel = 0;
int current_us = -1;  // -1 = limp

// Scan addresses 1-126. Returns the first PCA9685-range address that answers (0x40-0x7F, not 0x70), or 0.
uint8_t scan_i2c() {
  uint8_t found_pca = 0;
  int count = 0;
  Serial.println(F("Scanning I2C addresses 1-126..."));
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte err = Wire.endTransmission();
    if (err == 0) {
      count++;
      Serial.print(F("  Device answered at 0x"));
      if (addr < 16) Serial.print('0');
      Serial.print(addr, HEX);
      if (addr == ALL_CALL) Serial.print(F("  (PCA9685 all-call address, ignored)"));
      Serial.println();
      if (found_pca == 0 && addr >= 0x40 && addr <= 0x7F && addr != ALL_CALL) found_pca = addr;
    } else if (err == 5) {
      Serial.println(F("  I2C timed out: SDA/SCL held low. Check the wiring and PCA9685 VCC."));
      return 0;
    }
  }
  Serial.print(F("Scan done: "));
  Serial.print(count);
  Serial.println(F(" device(s) found."));
  return found_pca;
}

uint8_t read_reg(uint8_t reg) {
  Wire.beginTransmission(pca_addr);
  Wire.write(reg);
  Wire.endTransmission();
  Wire.requestFrom(pca_addr, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0xFF;
}

void show_registers() {
  if (!pca) { Serial.println(F("No PCA9685 connected.")); return; }
  uint8_t mode1 = read_reg(0x00);
  uint8_t prescale = read_reg(0xFE);
  uint8_t base = 0x06 + 4 * channel;  // LEDn_ON_L, ON_H, OFF_L, OFF_H
  uint16_t on = read_reg(base) | (read_reg(base + 1) << 8);
  uint16_t off = read_reg(base + 2) | (read_reg(base + 3) << 8);
  Serial.print(F("MODE1 = 0x")); Serial.print(mode1, HEX);
  Serial.println((mode1 & 0x10) ? F("  -> ASLEEP: outputs stopped") : F("  -> awake"));
  Serial.print(F("PRESCALE = ")); Serial.print(prescale);
  Serial.println(F("  (about 121 for 50 Hz)"));
  Serial.print(F("Channel ")); Serial.print(channel);
  Serial.print(F(": ON = ")); Serial.print(on & 0x0FFF);
  Serial.print(F(", OFF = ")); Serial.print(off & 0x0FFF);
  if (off & 0x1000) Serial.print(F("  (full OFF bit set: no pulses)"));
  Serial.println(F("  (1500 us is about OFF = 307)"));
}

void connect_pca(uint8_t addr) {
  delete pca;
  pca = new Adafruit_PWMServoDriver(addr);
  pca_addr = addr;
  pca->begin();
  pca->setOscillatorFrequency(27000000);  // typical; calibration corrects the exact timing later
  pca->setPWMFreq(50);                      // standard servo frame: 20 ms
  for (int ch = 0; ch < 16; ch++) pca->setPWM(ch, 0, 0);  // all outputs off = limp
  current_us = -1;
  Serial.print(F("Using PCA9685 at 0x")); Serial.println(addr, HEX);
}

void setup() {
  Serial.begin(115200);
  Serial.println(F("Booting..."));
  Wire.begin();
  Wire.setWireTimeout(25000, true);  // don't hang forever if SDA/SCL are miswired
  uint8_t addr = scan_i2c();
  if (addr) connect_pca(addr);
  else Serial.println(F("No PCA9685 found. Check VCC->5V, GND, SDA->A4, SCL->A5, then type s to rescan."));
  Serial.println(F("Ready. Pulse in us (600-2400), cN = channel, d = limp, s = scan, r = registers, ? = status."));
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "s") {
    uint8_t addr = scan_i2c();
    if (addr) connect_pca(addr);
    return;
  }
  if (line == "r") { show_registers(); return; }
  if (line == "w") {  // walk: each channel 0-15 gets 10 s: 5 s at 1000 us, 5 s at 2000 us. Any key stops.
    if (!pca) { Serial.println(F("No PCA9685 connected: type s to scan.")); return; }
    Serial.println(F("Walking channels 0-15, 10 s each. Send any key to stop."));
    for (int ch = 0; ch < 16; ch++) {
      Serial.print(F("Channel ")); Serial.print(ch); Serial.println(F(": 1000 us, then 2000 us"));
      const int pulses[2] = {1000, 2000};
      for (int k = 0; k < 2; k++) {
        pca->writeMicroseconds(ch, pulses[k]);
        unsigned long t0 = millis();
        while (millis() - t0 < 5000) {
          if (Serial.available()) {
            while (Serial.available()) Serial.read();
            pca->setPWM(ch, 0, 0);
            Serial.println(F("Stopped."));
            return;
          }
        }
      }
      pca->setPWM(ch, 0, 0);  // limp before moving on
    }
    Serial.println(F("Walk done."));
    return;
  }
  if (line == "?") {
    Serial.print(F("PCA9685 at 0x")); Serial.print(pca_addr, HEX);
    Serial.print(F(", channel ")); Serial.print(channel);
    if (current_us < 0) Serial.println(F(": limp"));
    else { Serial.print(F(": ")); Serial.print(current_us); Serial.println(F(" us")); }
    return;
  }
  if (line.charAt(0) == 'c') {
    int ch = line.substring(1).toInt();
    if (ch < 0 || ch > 15 || line.length() < 2) { Serial.println(F("Use c0 to c15.")); return; }
    channel = ch;
    current_us = -1;
    Serial.print(F("Now on channel ")); Serial.println(channel);
    return;
  }
  if (!pca) { Serial.println(F("No PCA9685 connected: type s to scan.")); return; }
  if (line == "d") {
    pca->setPWM(channel, 0, 0);
    current_us = -1;
    Serial.print(F("Channel ")); Serial.print(channel); Serial.println(F(" limp."));
    return;
  }
  long us = line.toInt();
  if (us < MIN_US || us > MAX_US) {
    Serial.print(F("Rejected '")); Serial.print(line); Serial.println(F("': use 600-2400, cN, d, s, r or ?"));
    return;
  }
  pca->writeMicroseconds(channel, (uint16_t)us);
  current_us = (int)us;
  Serial.print(F("Channel ")); Serial.print(channel); Serial.print(F(" -> ")); Serial.print(current_us); Serial.println(F(" us"));
}
