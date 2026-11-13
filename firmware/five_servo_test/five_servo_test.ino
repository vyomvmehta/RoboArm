/*
  five_servo_test.ino  --  bench test for the finished arm's layout, channels 0-4.

  Supersedes two_servo_test for the full five-servo wiring. Still a throwaway test tool,
  not the arm firmware: no protocol, no checksums, no watchdog. Type a pulse, watch a servo.

  CHANNEL MAP (same as arm_controller.ino and docs/PINS.md)
      ch0 = J0 base      MG996R 180
      ch1 = J1 shoulder  MG996R 180
      ch2 = J2 elbow     MG996R 180
      ch3 = J3 wrist     MG90S
      ch4 = J4 gripper   MG90S

  MEASURED TRAVEL
      MG996R (all four units, 2026-11-13): 400-2450 us for 180 deg, 11.4 us/deg
      MG90S  (both units,     2026-11-10): 650-2600 us for 180 deg, 10.8 us/deg,
                                           hard end stop near 500

  WIRING  (upload with servo power OFF)
      Nano 5V -> PCA VCC (logic only)      Nano GND -> PCA GND
      Nano A4 -> PCA SDA                   Nano A5  -> PCA SCL
      LM2596 OUT+/OUT- -> PCA screw terminal V+/GND
      Each servo: brown = GND (board edge), red = V+, orange = PWM
      NEVER connect the Nano's 5V to V+.

  SERIAL MONITOR: 115200 baud, line ending "Newline".

  COMMANDS
      3 1600     channel 3 to 1600 us
      c          every channel to ITS OWN centre, one at a time (staggered on purpose)
      d          all channels limp. This is the panic button.
      w          slow sweep of the last channel used. Any key stops it.
      s          show each channel's pulse and allowed range
      e          widen every channel to 400-2600 for hunting end stops

  SAFETY
      Boots limp. Moves ease in 20 us steps rather than jumping. 'c' deliberately moves one
      servo at a time: five MG996Rs starting together is the current spike D16 warns about
      and it has never been tested on the LM2596 at 9 V.
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca(0x40);

const uint8_t  NCH = 5;
const uint8_t  CH[NCH] = {0, 1, 2, 3, 4};

// Per channel, 50 us inside the measured travel. 'e' replaces these with 400/2600.
uint16_t lo_limit[NCH] = { 450,  450,  450,  700,  700};
uint16_t hi_limit[NCH] = {2400, 2400, 2400, 2550, 2550};

// Each servo's own mid-travel, not a blanket 1500.
const uint16_t CENTRE[NCH] = {1425, 1425, 1425, 1625, 1625};

const char *LABEL[NCH] = {"J0 base", "J1 shoulder", "J2 elbow", "J3 wrist", "J4 gripper"};

const uint8_t STEP_US = 20;      // move this much per step
const uint8_t STEP_MS = 20;      // wait this long between steps

int     current[NCH];            // -1 = limp, else the pulse in us
uint8_t last_ch = 0;
bool    pca_ok = false;

char    line[32];
uint8_t len = 0;

// ---------------------------------------------------------------- helpers

void limp_all() {
  for (uint8_t i = 0; i < NCH; i++) {
    if (pca_ok) pca.setPWM(CH[i], 0, 0);
    current[i] = -1;
  }
  Serial.println(F("all channels limp"));
}

void move_to(uint8_t i, uint16_t target) {
  if (!pca_ok) { Serial.println(F("no PCA9685")); return; }
  if (target < lo_limit[i] || target > hi_limit[i]) {
    Serial.print(F("refused: ")); Serial.print(target);
    Serial.print(F(" us outside ")); Serial.print(lo_limit[i]);
    Serial.print(F("-")); Serial.print(hi_limit[i]);
    Serial.println(F(" (press e to widen)"));
    return;
  }
  if (current[i] < 0) {                   // limp: no idea where it is, go straight there
    pca.writeMicroseconds(CH[i], target);
  } else {
    int from = current[i];
    int dir  = (target > from) ? STEP_US : -(int)STEP_US;
    while (abs(target - from) > STEP_US) {
      from += dir;
      pca.writeMicroseconds(CH[i], (uint16_t)from);
      delay(STEP_MS);
      if (Serial.available()) break;      // any keypress aborts the move
    }
    pca.writeMicroseconds(CH[i], target);
  }
  current[i] = target;
  last_ch = i;
  Serial.print(F("ch")); Serial.print(CH[i]);
  Serial.print(F(" (")); Serial.print(LABEL[i]);
  Serial.print(F(") -> ")); Serial.print(target); Serial.println(F(" us"));
}

void centre_all() {
  // One at a time, with a gap: five servos starting together is the untested current case.
  for (uint8_t i = 0; i < NCH; i++) {
    move_to(i, CENTRE[i]);
    delay(250);
  }
}

void sweep(uint8_t i) {
  Serial.print(F("sweeping ch")); Serial.print(CH[i]);
  Serial.println(F(" slowly. Send any character to stop."));
  for (uint16_t p = lo_limit[i]; p <= hi_limit[i]; p += STEP_US) {
    pca.writeMicroseconds(CH[i], p);
    current[i] = p;
    Serial.print(p); Serial.println(F(" us"));
    delay(120);
    if (Serial.available()) { while (Serial.available()) Serial.read(); break; }
  }
  Serial.println(F("sweep done (still holding: press d to go limp)"));
}

void status() {
  for (uint8_t i = 0; i < NCH; i++) {
    Serial.print(F("ch")); Serial.print(CH[i]);
    Serial.print(F(" ")); Serial.print(LABEL[i]); Serial.print(F(": "));
    if (current[i] < 0) Serial.print(F("limp"));
    else { Serial.print(current[i]); Serial.print(F(" us")); }
    Serial.print(F("   range ")); Serial.print(lo_limit[i]);
    Serial.print(F("-")); Serial.println(hi_limit[i]);
  }
}

// ---------------------------------------------------------------- commands

void handle(char *s) {
  if (s[0] == '\0') return;

  if (s[0] == 'd' && s[1] == '\0') { limp_all();  return; }
  if (s[0] == 's' && s[1] == '\0') { status();    return; }
  if (s[0] == 'w' && s[1] == '\0') { sweep(last_ch); return; }
  if (s[0] == 'c' && s[1] == '\0') { centre_all(); return; }
  if (s[0] == 'e' && s[1] == '\0') {
    for (uint8_t i = 0; i < NCH; i++) { lo_limit[i] = 400; hi_limit[i] = 2600; }
    Serial.println(F("range widened to 400-2600 on every channel."));
    Serial.println(F("Small steps, and press d the moment a servo buzzes."));
    return;
  }

  // "<channel> <microseconds>", e.g. "3 1600"
  if (s[0] >= '0' && s[0] <= '4' && s[1] == ' ') {
    uint8_t i = s[0] - '0';
    long us = atol(s + 2);
    if (us <= 0) { Serial.println(F("give a pulse width, e.g. 3 1600")); return; }
    move_to(i, (uint16_t)us);
    return;
  }

  Serial.println(F("commands: '<0-4> <us>', c, d, w, s, e"));
}

// ---------------------------------------------------------------- setup / loop

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < NCH; i++) current[i] = -1;

  Wire.begin();
  Wire.setWireTimeout(25000, true);
  Wire.beginTransmission(0x40);
  pca_ok = (Wire.endTransmission() == 0);

  if (pca_ok) {
    pca.begin();
    pca.setOscillatorFrequency(27000000);   // nominal; corrected at calibration
    pca.setPWMFreq(50);
    limp_all();
    Serial.println(F("PCA9685 found at 0x40."));
  } else {
    Serial.println(F("No PCA9685 at 0x40. Check VCC->5V, GND, SDA->A4, SCL->A5."));
  }

  Serial.println(F("five_servo_test: channels 0-4. Boots limp."));
  Serial.println(F("commands: '<0-4> <us>', c = centre each, d = limp, w = sweep, s = status, e = widen"));
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { line[len] = '\0'; handle(line); len = 0; continue; }
    if (len < sizeof(line) - 1) line[len++] = c;
  }
}
